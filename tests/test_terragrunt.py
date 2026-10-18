"""Render live HCL using test-only dependency outputs, never cloud credentials."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_configuration import ROOT


@unittest.skipUnless(shutil.which("terragrunt"), "Terragrunt must be on PATH for HCL integration checks")
class TerragruntIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        for item in ROOT.iterdir():
            if item.name in {".git", ".venv", ".terragrunt-cache", "__pycache__"}:
                continue
            if item.is_dir():
                shutil.copytree(item, cls.root / item.name, ignore=shutil.ignore_patterns("__pycache__", ".terragrunt-cache"))
            else:
                shutil.copy2(item, cls.root / item.name)
        subprocess.run(["git", "init", "-q"], cwd=cls.root, check=True)
        # Mocks are inserted exclusively into a temporary checkout, with all
        # dependency state reads disabled. Live HCL contains no mock_outputs.
        for path in (cls.root / "_units").glob("*.hcl"):
            text = path.read_text()
            mocks = {
                "identities": {"workload_configuration": {
                    name: {"gsa_email": f"fixture-{name}@fixture-project.iam.gserviceaccount.com"}
                    for name in ("worker", "gateway", "dispatcher", "telemetry", "migration")}},
                "storage": {"bucket_names": {key: f"fixture-{key}" for key in ("requests", "operations", "configuration", "evidence", "reports")}},
                "messaging": {"tick_topic_id": "projects/fixture-project/topics/fixture-tick"},
            }
            for name, value in mocks.items():
                text = text.replace(f'dependency "{name}" {{\n', f'dependency "{name}" {{\n'
                                    '  skip_outputs = true\n'
                                    '  mock_outputs_allowed_terraform_commands = ["render"]\n'
                                    f'  mock_outputs = jsondecode({json.dumps(json.dumps(value))})\n')
            path.write_text(text)
        for kind in ("task-request", "control-request"):
            subprocess.run(["python3", "scripts/register.py", "--environment", "dev", "--kind", kind,
                            "--manifest", f"examples/{kind}.json"], cwd=cls.root, check=True, capture_output=True)

    def run_tg(self, path, *args):
        return subprocess.run(["terragrunt", "--no-color", *args], cwd=self.root / path,
                              capture_output=True, text=True, timeout=30)

    def test_all_environment_units_render_and_retain_guards(self):
        for env in ("dev", "prod"):
            for unit in ("identities", "storage", "messaging", "database", "scheduling", "secrets", "schedules"):
                with self.subTest(environment=env, unit=unit):
                    result = self.run_tg(f"environments/{env}/region/{unit}", "render", "--json")
                    self.assertEqual(0, result.returncode, result.stderr)
                    data = json.loads(result.stdout)
                    self.assertTrue(data["prevent_destroy"])
                    self.assertTrue(data["remote_state"]["config"]["prefix"].startswith(f"harness/{env}/"))
                    self.assertTrue(data["remote_state"]["config"]["skip_bucket_creation"])
                    self.assertIn("?ref=" + "0" * 40, data["terraform"]["source"])
                    self.assertIn('region  = "us-east4"', data["generate"]["providers"]["contents"])
                    self.assertIn("deployment_readiness", data["terraform"]["before_hook"])
                    if unit == "scheduling":
                        self.assertTrue(data["inputs"]["paused"])
                        self.assertEqual("UTC", data["inputs"]["time_zone"])
                    if unit == "database" and env == "dev":
                        self.assertFalse(data["inputs"]["create_shared_budget_database"])
                        self.assertEqual([], data["inputs"]["shared_budget_clients"])

    def test_registered_units_render_with_separate_buckets(self):
        for category, identity, key, bucket in (
            ("requests", "example-argo-latency-001", "request", "mock-harness-dev-requests"),
            ("operations", "example-cancel-001", "control", "mock-harness-dev-operations"),
        ):
            result = self.run_tg(f"environments/dev/region/{category}/{identity}", "render", "--json")
            self.assertEqual(0, result.returncode, result.stderr)
            rendered = json.loads(result.stdout)
            self.assertEqual({}, rendered["dependency"])
            inputs = rendered["inputs"]
            self.assertEqual("PREVENT", inputs["deletion_policy"])
            self.assertEqual(bucket, inputs["bucket_name"])
            self.assertIn(key, inputs)

    @unittest.skipUnless(shutil.which("terraform"), "Terraform must be on PATH for the negative plan check")
    def test_mock_plan_stops_before_module_download(self):
        result = self.run_tg("environments/dev/region/identities", "plan", "-out=forbidden.tfplan")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("deployment_enabled is false", result.stdout + result.stderr)
        self.assertIn("Not running 'download source'", result.stderr)
        self.assertFalse(list(self.root.rglob("forbidden.tfplan")))
