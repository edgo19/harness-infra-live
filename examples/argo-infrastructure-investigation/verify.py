"""Check the complete three-repository example without applying anything."""
import json
import hashlib
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[2]
NAME = ROOT.name


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    roots = {name: WORKSPACE / name / "examples" / NAME for name in
             ("harness-terraform-modules", "harness-infra-live", "harness-gitops")}
    for name, root in roots.items():
        require(root.is_dir(), f"Clone sibling repository first: {name}")
    for filename in ("scenario.json", "request.json", "registry.json"):
        copies = [json.loads((root / filename).read_text()) for root in roots.values()]
        require(all(value == copies[0] for value in copies), f"Cross-repository drift: {filename}")
    scenario = json.loads((ROOT / "scenario.json").read_text())
    require(scenario["region"] == "us-east4", "Example region mismatch")
    require(not json.loads((ROOT / "deployment.json").read_text())["deployment_enabled"], "Example deployment must remain disabled")
    # Reuse the normal live repository's task/schedule schema validation.
    sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
    from check import validate_document
    validate_document(ROOT.parents[1], "task-request", json.loads((ROOT / "request.json").read_text()))
    validate_document(ROOT.parents[1], "schedule-registry", json.loads((ROOT / "registry.json").read_text()))
    require(not json.loads((ROOT / "registry.json").read_text())["schedules"][0]["enabled"], "Schedule must start disabled")
    prefixes = set()
    for unit in ("platform", "request", "schedules"):
        result = subprocess.run(["terragrunt", "--no-color", "render", "--json"], cwd=ROOT / "live" / unit,
                                check=True, capture_output=True, text=True)
        rendered = json.loads(result.stdout)
        require(not rendered["inputs"]["deployment_enabled"], "Example unexpectedly enabled")
        require(not rendered["dependency"], "Registration must not read privileged infrastructure state")
        prefixes.add(rendered["remote_state"]["config"]["prefix"])
        require(f"//examples/{NAME}/" in rendered["terraform"]["source"], "Wrong Terraform example source")
        if unit == "request":
            require(rendered["inputs"]["bucket_name"] == scenario["bucket_names"]["requests"], "Wrong request bucket")
    require(len(prefixes) == 3, "Example units share a state prefix")
    code = runpy.run_path(str(roots["harness-gitops"] / "verify.py"))
    count = code["verify"](roots["harness-gitops"])
    report = json.loads((ROOT / "expected/report.json").read_text())
    require(report["example_only"] and report["task"]["request_id"] == json.loads((ROOT / "request.json").read_text())["request_id"], "Illustrative report is mislabeled")
    for item in report["evidence"]:
        path = ROOT / "expected" / item["object_ref"].rsplit("/", 1)[1]
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], "Synthetic evidence hash mismatch")
        require(item["object_generation"] == "NOT_UPLOADED_EXAMPLE", "Fixture must not claim a real GCS upload")
    print(f"PASS: three matching repositories, three isolated Terragrunt units and {count} Kubernetes resources. No cloud calls or investigation.")


if __name__ == "__main__":
    main()
