"""Reject the shipped example before module download or cloud operations."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
scenario = json.loads((root / "scenario.json").read_text())
enabled = json.loads((root / "deployment.json").read_text())["deployment_enabled"]
text = json.dumps(scenario)
if not enabled or any(marker in text for marker in ("mock-", "REPLACE_", "example.invalid")):
    raise SystemExit("BLOCKED: configuration example only; deployment disabled or mock values remain.")
raise SystemExit("BLOCKED: promote to version-pinned production modules and the reviewed live stacks; this local-source example has no deployment approval path.")
