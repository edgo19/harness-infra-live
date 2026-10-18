import json
import unittest

import test_configuration as fixtures
import check
import export_contract


class DeploymentContract(unittest.TestCase):
    config = fixtures.Contracts.config
    save = fixtures.Contracts.save

    def setUp(self):
        fixtures.Contracts.setUp(self)
        self.outputs = self.root / "outputs"
        self.outputs.mkdir()
        self.cfg = self.config()
        self.cfg["models"]["approved_regional_models"] = ["fixture-approved-model"]
        self.save(self.cfg)
        locks = check.load(self.root / "dependency-locks" / "modules.json")
        locks["environments"]["dev"]["commit"] = "ab" * 20
        (self.root / "dependency-locks" / "modules.json").write_text(json.dumps(locks))
        spaces = {"worker": "workers", "gateway": "control", "dispatcher": "control", "telemetry": "tools", "migration": "control"}
        workloads = {name: {
            "ksa_namespace": f"harness-{space}-dev", "ksa_name": f"harness-{name}",
            "gsa_email": f"harness-{name}-dev@mock-harness-dev.iam.gserviceaccount.com",
            "gsa_subject": str(100000000000000000000 + i), "unexpected_secret": "must-not-copy",
        } for i, (name, space) in enumerate(spaces.items())}
        self.write_outputs("identities", {"workload_configuration": workloads, "unexpected_private_key": "must-not-copy"})
        self.write_outputs("storage", {"bucket_names": {key: value for key, value in self.cfg["storage"].items() if key != "cmek_key_name"}})
        keys = ("request_subscription_id", "operations_subscription_id", "tick_subscription_id", "triage_subscription_id")
        self.write_outputs("messaging", {**{key: f"projects/mock-harness-dev/subscriptions/{key}" for key in keys},
                                        "tick_topic_id": "projects/mock-harness-dev/topics/ticks"})
        self.write_outputs("database", {"instance_connection_name": "mock-harness-dev:us-east4:harness-dev", "runtime_database": "harness"})

    def write_outputs(self, unit, values):
        data = {key: {"sensitive": False, "value": value} for key, value in values.items()}
        (self.outputs / f"{unit}.json").write_text(json.dumps(data))

    def test_export_whitelists_nested_outputs(self):
        document = export_contract.build_contract(self.root, "dev", self.outputs)
        self.assertNotIn("must-not-copy", json.dumps(document))
        self.assertEqual("us-east4", document["region"])

    def test_sensitive_output_is_rejected(self):
        path = self.outputs / "identities.json"
        data = check.load(path)
        data["workload_configuration"]["sensitive"] = True
        path.write_text(json.dumps(data))
        with self.assertRaises(check.ConfigurationError):
            export_contract.build_contract(self.root, "dev", self.outputs)

    def test_mixed_environment_outputs_are_rejected(self):
        self.write_outputs("database", {"instance_connection_name": "mock-harness-prod:us-east4:harness-prod", "runtime_database": "harness"})
        with self.assertRaises(check.ConfigurationError):
            export_contract.build_contract(self.root, "dev", self.outputs)
