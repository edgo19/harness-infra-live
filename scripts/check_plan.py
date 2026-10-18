"""Reject destructive or out-of-scope resource actions in a saved plan JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def violations(plan, registration=False):
    errors = []
    for item in plan.get("resource_changes", []):
        if item.get("mode") == "data":
            continue
        actions = item["change"]["actions"]
        resource_type = item["type"]
        if "delete" in actions:
            errors.append("Resource deletion/replacement requires a separate retirement design")
        if resource_type in {"google_service_account_key", "google_project_iam_policy", "google_project_iam_binding"}:
            errors.append("Keys and authoritative project IAM are prohibited")
        if resource_type == "google_project_iam_member":
            role = (item["change"].get("after") or {}).get("role")
            if role in {"roles/owner", "roles/editor", "roles/iam.serviceAccountTokenCreator"} or role is None:
                errors.append("Broad or unknown project role is prohibited")
        if registration:
            if resource_type != "google_storage_bucket_object":
                errors.append("Registration plans may only manage immutable GCS objects")
            if actions not in (["create"], ["no-op"]):
                errors.append("Registration objects are create-only; use a new ID")
            after = item["change"].get("after") or {}
            if after.get("deletion_policy") != "PREVENT":
                errors.append("Registration requires GCS object deletion_policy PREVENT")
    if plan.get("errored") is True:
        errors.append("Terraform reports an errored plan")
    if plan.get("deferred_changes"):
        errors.append("Deferred changes require a complete new plan")
    if plan.get("complete") is False:
        errors.append("Incomplete plans require a complete new plan")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--registration", action="store_true")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        if not isinstance(plan, dict) or "format_version" not in plan or "planned_values" not in plan:
            raise ValueError("Not a Terraform plan JSON")
        errors = violations(plan, args.registration)
    except (OSError, ValueError, KeyError, TypeError):
        print("FAIL: unreadable or invalid plan JSON")
        return 1
    for error in sorted(set(errors)):
        print(f"FAIL: {error}")
    if not errors:
        print("PASS: plan action policy (does not replace IAM/resource review)")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
