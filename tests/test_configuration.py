from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check
import check_plan
import register


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("schemas", "examples", "environments", "schedules", "dependency-locks", "shared"):
            shutil.copytree(ROOT / directory, self.root / directory)

    def config(self, env="dev"):
        return check.load(self.root / "environments" / env / "environment.json")

    def save(self, cfg):
        path = self.root / "environments" / cfg["environment"] / "environment.json"
        path.write_text(json.dumps(cfg))

    def test_mock_configuration_valid_offline_but_blocked_for_deployment(self):
        self.assertEqual([], check.check(self.root))
        errors = check.check(self.root, ("dev",), ready=True)
        for expected in ("deployment_enabled", "Mock", "commit hash", "prerequisites", "model"):
            self.assertTrue(any(expected in error for error in errors), expected)

    def test_toggling_enabled_cannot_bypass_missing_inputs(self):
        cfg = self.config()
        cfg["deployment_enabled"] = True
        self.save(cfg)
        self.assertGreater(len(check.check(self.root, ("dev",), ready=True)), 3)

    def test_complete_declarations_can_pass_readiness_without_claiming_cloud_validation(self):
        for env in ("dev", "prod"):
            cfg = json.loads(json.dumps(self.config(env)).replace("mock-", "corp-"))
            cfg["deployment_enabled"] = True
            cfg["prerequisites"] = {key: True for key in cfg["prerequisites"]}
            cfg["network"]["private_service_access_ready"] = True
            cfg["models"]["approved_regional_models"] = ["approved-model-id"]
            self.save(cfg)
        locks = check.load(self.root / "dependency-locks" / "modules.json")
        locks["environments"]["dev"]["commit"] = "ab" * 20
        (self.root / "dependency-locks" / "modules.json").write_text(json.dumps(locks))
        self.assertEqual([], check.check(self.root, ("dev",), ready=True))

    def test_operation_bucket_cannot_share_request_bucket(self):
        cfg = self.config()
        cfg["storage"]["operations"] = cfg["storage"]["requests"]
        self.save(cfg)
        self.assertTrue(any("distinct buckets" in x for x in check.check(self.root)))

    def test_cross_environment_cross_purpose_bucket_collision_rejected(self):
        cfg = self.config()
        cfg["storage"]["requests"] = self.config("prod")["storage"]["operations"]
        self.save(cfg)
        self.assertTrue(any("across purposes" in x for x in check.check(self.root)))

    def test_shared_backend_cannot_have_independent_budget_instances(self):
        cfg = self.config()
        cfg["shared_budget"]["instance_connection_name"] = "mock-dev:us-east4:separate"
        self.save(cfg)
        self.assertTrue(any("same shared-backend" in x for x in check.check(self.root)))

    def test_live_telemetry_requires_validated_coordinator(self):
        cfg = self.config()
        cfg["shared_budget"]["live_telemetry_enabled"] = True
        self.save(cfg)
        self.assertTrue(any("validated shared" in x for x in check.check(self.root)))

    def test_degraded_production_ha_is_rejected(self):
        cfg = self.config("prod")
        cfg["database"]["availability_type"] = "ZONAL"
        self.save(cfg)
        self.assertTrue(any("HA/size" in x for x in check.check(self.root)))

    def test_generic_parameters_but_no_top_level_credential_selection(self):
        request = check.load(self.root / "examples" / "task-request.json")
        request["capability"] = "future-capability@2.0.0"
        request["parameters"] = {"future_input": {"value": 42}}
        check.validate_document(self.root, "task-request", request)
        request["credential"] = "chosen-by-task"
        with self.assertRaises(check.ConfigurationError):
            check.validate_document(self.root, "task-request", request)

    def test_schedule_template_cannot_bypass_task_budget(self):
        registry = check.load(self.root / "examples" / "schedule-registry.json")
        registry["schedules"][0]["task_template"]["requested_limits"]["backend_query_calls"] = 1000000
        with self.assertRaises(check.ConfigurationError):
            check.validate_document(self.root, "schedule-registry", registry)

    def test_oversized_generic_request_rejected(self):
        request = check.load(self.root / "examples" / "task-request.json")
        request["parameters"] = {"large_text": "x" * 32768}
        with self.assertRaises(check.ConfigurationError):
            check.validate_document(self.root, "task-request", request)

    def test_schedule_ids_are_unique_and_cron_is_bounded(self):
        registry = check.load(self.root / "examples" / "schedule-registry.json")
        registry["schedules"].append(copy.deepcopy(registry["schedules"][0]))
        with self.assertRaises(check.ConfigurationError):
            check.validate_document(self.root, "schedule-registry", registry)
        registry["schedules"] = registry["schedules"][:1]
        registry["schedules"][0]["cron"] = "* * * * * *"
        with self.assertRaises(check.ConfigurationError):
            check.validate_document(self.root, "schedule-registry", registry)

    def test_new_request_is_dedicated_and_cannot_overwrite(self):
        source = self.root / "examples" / "task-request.json"
        target = register.register(self.root, "dev", "task-request", source)
        self.assertIn("/requests/", str(target))
        self.assertIn("request-registration.hcl", (target / "terragrunt.hcl").read_text())
        self.assertEqual([], check.check(self.root))
        with self.assertRaises(FileExistsError):
            register.register(self.root, "dev", "task-request", source)

    def test_control_registration_separate_path_and_environment(self):
        source = self.root / "examples" / "control-request.json"
        with self.assertRaises(check.ConfigurationError):
            register.register(self.root, "prod", "control-request", source)
        target = register.register(self.root, "dev", "control-request", source)
        self.assertIn("/operations/", str(target))
        self.assertIn("control-registration.hcl", (target / "terragrunt.hcl").read_text())

    def test_invalid_request_id_cannot_traverse_paths(self):
        request = check.load(self.root / "examples" / "task-request.json")
        request["request_id"] = "../../escape"
        source = self.root / "malicious.json"
        source.write_text(json.dumps(request))
        with self.assertRaises(check.ConfigurationError):
            register.register(self.root, "dev", "task-request", source)

    def test_cancel_cannot_carry_schedule_target(self):
        operation = check.load(self.root / "examples" / "control-request.json")
        operation["target_schedule_id"] = "another-schedule"
        with self.assertRaises(check.ConfigurationError):
            check.validate_document(self.root, "control-request", operation)

    def test_duplicate_json_keys_rejected(self):
        path = self.root / "invalid.json"
        path.write_text('{"request_id":"a","request_id":"b"}')
        with self.assertRaises(check.ConfigurationError):
            check.load(path)

    def test_committed_request_changes_and_removal_rejected(self):
        target = register.register(self.root, "dev", "task-request", self.root / "examples" / "task-request.json")
        for args in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        self.assertEqual([], check.immutable_changes(self.root, "HEAD"))
        manifest = target / "manifest.json"
        request = check.load(manifest)
        request["goal"] = "Silently change committed intent"
        manifest.write_text(json.dumps(request))
        self.assertTrue(check.immutable_changes(self.root, "HEAD"))
        manifest.unlink()
        self.assertTrue(check.immutable_changes(self.root, "HEAD"))


class PlanPolicy(unittest.TestCase):
    def plan(self, actions, kind="google_storage_bucket_object", **after):
        return {"resource_changes": [{"type": kind, "mode": "managed", "change": {
            "actions": actions, "after": {"deletion_policy": "PREVENT", **after},
        }}]}

    def test_create_only_registration(self):
        self.assertEqual([], check_plan.violations(self.plan(["create"]), registration=True))
        for actions in (["update"], ["delete"], ["delete", "create"]):
            self.assertTrue(check_plan.violations(self.plan(actions), registration=True))

    def test_registration_cannot_edit_infrastructure(self):
        self.assertTrue(check_plan.violations(self.plan(["create"], "google_service_account"), registration=True))

    def test_no_gsa_keys_or_broad_roles(self):
        self.assertTrue(check_plan.violations(self.plan(["create"], "google_service_account_key")))
        for role in ("roles/owner", "roles/editor", "roles/iam.serviceAccountTokenCreator"):
            self.assertTrue(check_plan.violations(self.plan(["create"], "google_project_iam_member", role=role)))

    def test_infrastructure_destroy_is_blocked(self):
        self.assertTrue(check_plan.violations(self.plan(["delete"], "google_sql_database_instance")))

    def test_missing_deletion_protection_is_blocked(self):
        self.assertTrue(check_plan.violations(self.plan(["create"], deletion_policy="DELETE"), registration=True))


if __name__ == "__main__":
    unittest.main()
