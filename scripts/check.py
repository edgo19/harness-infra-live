"""Validate reviewed live configuration without cloud access or Terraform init."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
UNITS = ("identities", "storage", "messaging", "database", "scheduling", "secrets", "schedules")


class ConfigurationError(ValueError):
    pass


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("Duplicate JSON object key")
        result[key] = value
    return result


def load(path: Path):
    try:
        return json.loads(path.read_text(), object_pairs_hook=reject_duplicate_keys)
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"Cannot read valid JSON: {path}") from exc


def validate_document(root: Path, kind: str, document: dict):
    validator = Draft202012Validator(load(root / "schemas" / f"{kind}.schema.json"))
    errors = sorted(validator.iter_errors(document), key=lambda e: str(list(e.path)))
    if errors:
        # Do not echo goals, parameter values, credentials or log excerpts.
        where = "/".join(map(str, errors[0].path)) or "document"
        raise ConfigurationError(f"{kind}: schema violation at {where}")
    if kind == "task-request" and len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > 32768:
        raise ConfigurationError("Task request exceeds the 32 KiB pilot limit")
    if kind == "schedule-registry":
        seen = set()
        for schedule in document["schedules"]:
            if schedule["id"] in seen:
                raise ConfigurationError("Schedule IDs must be unique")
            seen.add(schedule["id"])
            validate_document(root, "task-request", {
                "schema": "TaskRequest/v1", "request_id": schedule["id"],
                **schedule["task_template"],
            })


def environment_errors(root: Path, env: str, *, ready=False):
    path = root / "environments" / env
    cfg = load(path / "environment.json")
    validate_document(root, "environment", cfg)
    errors = []
    if cfg["environment"] != env or cfg["state"]["prefix"] != f"harness/{env}":
        errors.append("Environment and state prefix must match their directory")
    buckets = [v for k, v in cfg["storage"].items() if k != "cmek_key_name"]
    if len(set(buckets)) != 5 or cfg["state"]["bucket"] in buckets:
        errors.append("State, requests, operations, configuration, evidence and reports need distinct buckets")
    db = cfg["database"]
    if db["disk_autoresize_limit_gb"] < db["disk_size_gb"]:
        errors.append("SQL autoresize cap is smaller than the initial disk")
    if env == "prod" and (db["availability_type"] != "REGIONAL" or db["tier"] != "db-custom-2-8192"):
        errors.append("Initial production database must retain the reviewed HA/size baseline")
    shared = cfg["shared_budget"]
    if shared["live_telemetry_enabled"] and not shared["validated"]:
        errors.append("Live telemetry requires validated shared query-budget coordination")
    registry = load(root / "schedules" / env / "registry.json")
    validate_document(root, "schedule-registry", registry)
    for unit in UNITS:
        if not (path / "region" / unit / "terragrunt.hcl").is_file():
            errors.append(f"Missing unit: {unit}")
    for category, kind, id_field in [
        ("requests", "task-request", "request_id"),
        ("operations", "control-request", "operation_id"),
    ]:
        for directory in sorted((path / "region" / category).iterdir()):
            if not directory.is_dir():
                if directory.name != ".gitkeep":
                    errors.append(f"Unexpected registration file in {category}")
                continue
            doc = load(directory / "manifest.json")
            validate_document(root, kind, doc)
            if doc[id_field] != directory.name:
                errors.append(f"{category}: directory must match immutable ID")
            if kind == "control-request" and doc["environment"] != env:
                errors.append("Control request environment mismatch")
            if not (directory / "terragrunt.hcl").is_file():
                errors.append(f"Missing registration unit in {category}")
    if ready:
        if not cfg["deployment_enabled"]:
            errors.append("deployment_enabled is false")
        if re.search(r"(?:mock-|example-|REPLACE|CHANGEME)", json.dumps(cfg), re.I):
            errors.append("Mock or example environment values remain")
        locks = load(root / "dependency-locks" / "modules.json")
        commit = locks["environments"][env]["commit"]
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit) or len(set(commit)) == 1:
            errors.append("A reviewed, full Terraform module commit hash is required")
        if not all(cfg["prerequisites"].values()):
            errors.append("Enterprise prerequisites are not confirmed")
        if not cfg["network"]["private_service_access_ready"]:
            errors.append("Existing private SQL routing/service access must be confirmed")
        if not cfg["models"]["approved_regional_models"]:
            errors.append("Approved regional Vertex model IDs are required")
        if shared["live_telemetry_enabled"]:
            clients = load(root / "shared" / "query-budget-clients.json")["service_accounts"]
            expected = f"harness-telemetry-{env}@{cfg['project_id']}.iam.gserviceaccount.com"
            if expected not in clients:
                errors.append("This environment's telemetry GSA must be explicitly registered as a shared budget client")
    return errors


def immutable_changes(root: Path, base_ref: str):
    """Reject edits/removal of committed registrations; require a new ID."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", base_ref, "--", "environments"],
        cwd=root, check=True, capture_output=True, text=True,
    )
    errors = []
    pattern = r"environments/(dev|prod)/region/(requests|operations)/[^/]+/manifest\.json"
    for name in result.stdout.splitlines():
        if not re.fullmatch(pattern, name):
            continue
        old = subprocess.run(["git", "show", f"{base_ref}:{name}"], cwd=root,
                             check=True, capture_output=True, text=True)
        current = root / name
        if not current.is_file() or json.loads(old.stdout) != load(current):
            errors.append(f"Committed registration is immutable: {name}; use a new ID")
    return errors


def check(root: Path, environments=("dev", "prod"), *, ready=False, base_ref=None):
    errors = []
    locks = load(root / "dependency-locks" / "modules.json")
    if locks.get("repository") != "https://github.com/edgo19/harness-terraform-modules.git":
        errors.append("Module repository must be the reviewed dedicated module repository")
    if set(locks.get("environments", {})) != {"dev", "prod"}:
        errors.append("Module locks must name dev and prod")
    else:
        for item in locks["environments"].values():
            commit = item.get("commit")
            if commit is not None and (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit) or len(set(commit)) == 1):
                errors.append("Module revision must be null (undeployable) or a full commit hash")
    clients = load(root / "shared" / "query-budget-clients.json")
    members = clients.get("service_accounts")
    if set(clients) != {"service_accounts"} or not isinstance(members, list) or any(
        not isinstance(x, str) or not re.fullmatch(r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", x)
        for x in (members or [])
    ) or len(set(members or [])) != len(members or []):
        errors.append("Budget clients must be an explicit unique GSA email list")
    configs = [load(root / "environments" / e / "environment.json") for e in ("dev", "prod")]
    if configs[0]["state"]["bucket"] == configs[1]["state"]["bucket"] and configs[0]["state"]["prefix"] == configs[1]["state"]["prefix"]:
        errors.append("Dev and prod state prefixes must not collide")
    bucket_names = [cfg["storage"][key] for cfg in configs for key in ("requests", "configuration", "operations", "evidence", "reports")]
    if len(set(bucket_names)) != 10:
        errors.append("All dev/prod application buckets must be distinct across purposes")
    if configs[0]["shared_budget"]["instance_connection_name"] != configs[1]["shared_budget"]["instance_connection_name"]:
        errors.append("Both environments must reference the same shared-backend budget instance")
    for cfg in configs:
        if cfg["shared_budget"]["project_id"] != configs[1]["project_id"] or cfg["shared_budget"]["instance_connection_name"] != f"{configs[1]['project_id']}:us-east4:harness-prod":
            errors.append("Shared budget must reference the declared production SQL instance")
    for env in environments:
        errors.extend(f"{env}: {error}" for error in environment_errors(root, env, ready=ready))
    for kind in ("task-request", "control-request", "schedule-registry"):
        validate_document(root, kind, load(root / "examples" / f"{kind}.json"))
    if base_ref:
        errors.extend(immutable_changes(root, base_ref))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("dev", "prod"))
    parser.add_argument("--ready", action="store_true", help="Require real deployment inputs")
    parser.add_argument("--base-ref", help="Reject changed/removed registrations compared with this Git ref")
    args = parser.parse_args()
    if args.ready and not args.environment:
        parser.error("--ready requires --environment")
    try:
        errors = check(ROOT, (args.environment,) if args.environment else ("dev", "prod"),
                       ready=args.ready, base_ref=args.base_ref)
    except (ConfigurationError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {type(exc).__name__}: configuration could not be validated")
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: configuration contracts" + (" and deployment prerequisites" if args.ready else " (offline; deployment readiness not asserted)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
