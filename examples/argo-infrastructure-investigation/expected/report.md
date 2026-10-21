# Illustrative investigation report

**Synthetic example only. No enterprise query, model invocation or GCS upload occurred.**

Request: `example-argo-latency-001`; run: `example-run-001`. Outcome: partial.

The supplied synthetic metrics show reconciliation p95 increasing from 8 seconds to 36 seconds. Two synthetic controller log messages mention timeouts. These observations correlate; they do not establish a cause or a complete count of errors.

Ask the CI/CD infrastructure owner to review controller timeouts, its resource telemetry and the approved internal connectivity path. No action is executed by the harness. Application destination clusters and their telemetry are outside this investigation's scope.

Evidence: `metrics.json` and `logs.jsonl` beside this file. Their actual fixture hashes are recorded in `report.json`; the GCS paths there illustrate future publication locations and have not been uploaded.
