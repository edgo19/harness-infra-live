"""Prepare an immutable registration unit locally; never invoke Terraform."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from check import ROOT, ConfigurationError, load, validate_document


def register(root: Path, env: str, kind: str, source: Path):
    document = load(source)
    validate_document(root, kind, document)
    control = kind == "control-request"
    if control and document["environment"] != env:
        raise ConfigurationError("Control environment does not match requested environment")
    identity = document["operation_id" if control else "request_id"]
    category = "operations" if control else "requests"
    unit = "control-registration" if control else "request-registration"
    target = root / "environments" / env / "region" / category / identity
    # Exclusive directory creation also prevents reusing an existing ID. Do not
    # overwrite even if its manifest happens to match the new input.
    target.mkdir(parents=False, exist_ok=False)
    try:
        (target / "manifest.json").write_text(json.dumps(document, indent=2) + "\n")
        (target / "terragrunt.hcl").write_text(
            'include "root" {\n  path   = find_in_parent_folders("root.hcl")\n  expose = true\n}\n\n'
            f'include "unit" {{\n  path = "${{get_repo_root()}}/_units/{unit}.hcl"\n}}\n'
        )
    except Exception:
        for file in target.iterdir():
            file.unlink()
        target.rmdir()
        raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=("dev", "prod"))
    parser.add_argument("--kind", default="task-request", choices=("task-request", "control-request"))
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        target = register(ROOT, args.environment, args.kind, args.manifest)
    except (ConfigurationError, OSError) as exc:
        print(f"FAIL: {type(exc).__name__}; registration not overwritten or submitted")
        return 1
    print(f"Prepared {target.relative_to(ROOT)}; review and commit it. No cloud operation performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
