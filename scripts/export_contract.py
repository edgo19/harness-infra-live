"""Whitelist nonsecret Terraform outputs for reviewed GitOps promotion."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from check import ROOT, ConfigurationError, check, load, validate_document


def output(directory: Path, unit: str, name: str):
    entry = load(directory / f"{unit}.json")[name]
    if entry.get("sensitive") is not False:
        raise ConfigurationError("Refusing a sensitive or unclassified Terraform output")
    return entry["value"]


def build_contract(root: Path, env: str, directory: Path):
    cfg = load(root / "environments" / env / "environment.json")
    locks = load(root / "dependency-locks" / "modules.json")
    workloads = output(directory, "identities", "workload_configuration")
    # Construct nested values explicitly so unexpected fields never propagate.
    selected = {name: {key: workloads[name][key] for key in ("ksa_namespace", "ksa_name", "gsa_email", "gsa_subject")}
                for name in ("worker", "gateway", "dispatcher", "telemetry", "migration")}
    spaces = {"worker": "workers", "telemetry": "tools", "gateway": "control", "dispatcher": "control", "migration": "control"}
    for name, item in selected.items():
        if item["ksa_namespace"] != f"harness-{spaces[name]}-{env}" or item["ksa_name"] != f"harness-{name}":
            raise ConfigurationError("KSA identity does not match the environment contract")
        if item["gsa_email"] != f"harness-{name}-{env}@{cfg['project_id']}.iam.gserviceaccount.com":
            raise ConfigurationError("Unexpected GSA identity")
    buckets = output(directory, "storage", "bucket_names")
    selected_buckets = {name: buckets[name] for name in ("requests", "configuration", "operations", "evidence", "reports")}
    if any(cfg["storage"][key] != value for key, value in selected_buckets.items()):
        raise ConfigurationError("Bucket outputs do not match the selected environment")
    connection = output(directory, "database", "instance_connection_name")
    if connection != f"{cfg['project_id']}:{cfg['region']}:harness-{env}":
        raise ConfigurationError("SQL instance output belongs to another environment")
    keys = ("request_subscription_id", "operations_subscription_id", "tick_subscription_id", "tick_topic_id", "triage_subscription_id")
    messaging = {key: output(directory, "messaging", key) for key in keys}
    if any(not value.startswith(f"projects/{cfg['project_id']}/") for value in messaging.values()):
        raise ConfigurationError("Messaging output belongs to another project")
    shared = cfg["shared_budget"]
    document = {
        "schema": "DeploymentContract/v1", "environment": env, "region": cfg["region"],
        "project_id": cfg["project_id"], "gke_project_id": cfg["gke_project_id"],
        "module_commit": locks["environments"][env]["commit"], "workloads": selected,
        "buckets": selected_buckets, "messaging": messaging,
        "database": {"instance_connection_name": connection, "runtime_database": output(directory, "database", "runtime_database")},
        "shared_budget": {key: shared[key] for key in ("instance_connection_name", "database_name", "live_telemetry_enabled")},
        "approved_regional_models": cfg["models"]["approved_regional_models"],
    }
    validate_document(root, "deployment-contract", document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=("dev", "prod"))
    parser.add_argument("--outputs-dir", type=Path, required=True, help="Protected directory holding terraform output -json per unit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if check(ROOT, (args.environment,), ready=True):
            raise ConfigurationError("Deployment readiness checks have not passed")
        document = build_contract(ROOT, args.environment, args.outputs_dir)
        # Never overwrite an existing reviewed/published artifact.
        with args.output.open("x") as handle:
            handle.write(json.dumps(document, indent=2) + "\n")
    except (ConfigurationError, OSError, KeyError, TypeError):
        print("FAIL: deployment contract not exported; check prerequisites and exact nonsecret output contracts")
        return 1
    print("Exported a nonsecret deployment contract; promote through a reviewed GitOps change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
