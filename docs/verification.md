# Verification — 2026-10-18

Validated on Linux x86_64 with Python 3.12.14, Terraform 1.16.6 and Terragrunt 1.1.6. The Terraform/Terragrunt executables were downloaded from their official release locations and verified against their published SHA-256 manifests. Google provider 8.7.0 is a configuration pin; it has not been initialized or integration-tested here.

## Checks executed

- `uv sync --frozen`: installed the repository's hashed Python dependency lock.
- `terragrunt hcl fmt --check` and `terragrunt hcl validate`: successful across the live configuration.
- `python scripts/check.py`: both mock environments, empty live schedule registries, module-lock format and example contracts passed offline validation.
- `python -m unittest discover -s tests -v`: **29 tests passed**, none skipped with the pinned tools on PATH. The Terragrunt tests render all 14 environment units plus two generated registration units in an isolated temporary checkout with test-only dependency outputs. The registration renders verify separate bucket selection without dependency state reads.
- Negative `terragrunt plan`: the readiness hook rejected mock configuration before module download; no saved resource plan was produced. A test also checks that fully supplied fixture declarations can pass the declarative readiness checker, without making cloud claims.
- Negative contract/action tests: ID reuse and path traversal, committed intent edits/deletion, invalid controls, cross-purpose/cross-environment bucket collisions, divergent shared budget databases, unvalidated live telemetry, weakened production HA, oversized requests, schedule budget bypass/cron/duplicate IDs, destructive plans, registration updates and broad IAM/key resources.
- Deployment-contract tests: select only whitelisted nested fields, reject sensitive Terraform outputs and reject mixed environment SQL outputs.
- `git diff --check`: no whitespace errors.

## Not verified

No reusable Terraform module implementation exists yet. There was no real module initialization, provider lock generation, `terraform validate` against resource definitions, cloud resource plan or apply. Terragrunt parsing/rendering and fixtures do not establish module compatibility or service availability.

Enterprise GCP/WIF/ADC, state/backend permissions, private SQL routing, SQL bootstrap/migrations, model invocation/region availability, runtime IAM, ESO credentials, Pub/Sub admission/DLQ/replay, scheduling, GKE/Argo deployment and Loki/Mimir query-budget behavior remain integration work. No backend requests, model calls or investigations ran.

Retain these distinctions when promoting the next module/runtime implementation. Mock values are intentional and deployment stays disabled until the real prerequisites are supplied.
