# Harness infrastructure live

**Start with the [complete three-repository example](examples/argo-infrastructure-investigation/README.md)** for a concrete request, resource/input/output tables, relationship diagrams, the deployment/runtime sequence and an illustrative report. It is separate from the production-oriented stacks below.

Reviewed Terragrunt configuration for the generic harness on the existing GCP observability GKE cluster. This repository provisions hosting infrastructure and registers runtime intent. CI/CD never performs an investigation.

**Initial implementation:** dev and prod in `us-east4`, with mock project/network/state settings. Deployment is blocked. The referenced modules in [`harness-terraform-modules`](https://github.com/edgo19/harness-terraform-modules) are not implemented yet, and their commit pins are deliberately `null`. This repository cannot produce a resource plan until those modules and real deployment inputs are available.

The [detailed architecture](https://github.com/edgo19/harness-agent-framework/blob/3e58128fc9c3cdb0b133123ba6445b9d1c187dda/docs/design/2026-10-18/README.md) is the design baseline. This implementation defines the proposed exact [module interfaces](docs/module-contracts.md) for the next repository. Kubernetes workloads, namespaces, NetworkPolicy and ExternalSecrets belong in [`harness-gitops`](https://github.com/edgo19/harness-gitops).

## Layout

```text
root.hcl                         # provider/backend pins, readiness hook, destroy guard
_units/                          # reusable live configuration for each module
dependency-locks/modules.json    # reviewed full module commit per environment
environments/{dev,prod}/
  environment.json               # nonsecret values; deployment disabled
  environment.hcl
  region/
    identities/ storage/ messaging/ database/ scheduling/ secrets/ schedules/
    requests/<request-id>/        # one immutable request and state per ID
    operations/<operation-id>/    # separate operator-only control registration
schedules/{dev,prod}/registry.json
shared/query-budget-clients.json # exact cross-environment SQL budget GSAs
deployment-contracts/{dev,prod}/ # reviewed nonsecret output artifacts when provisioned
schemas/ examples/ scripts/ tests/
```

`region` is a fixed directory name; the actual region comes from `environment.json`. Keeping the directory stable avoids moving Terraform state when editing configuration. Changing an actual resource region still requires a migration design.

## Local development

Required tools: Python 3.12/3.13, `uv`, Terraform **1.16.6**, Terragrunt **1.1.6**, Git and Make. Google provider **8.7.0** is pinned in generated configuration. These are initial tested tool versions, not a requirement to upgrade enterprise tooling without review.

```bash
uv sync --frozen
make check
```

If your home directory is read-only, set `UV_CACHE_DIR` to an approved writable cache first. Put Terraform and Terragrunt on `PATH`. No application service or cloud credential is needed for these checks.

`make check` validates HCL syntax/formatting, JSON contracts and negative policy cases. Its Terragrunt integration tests render 14 environment units and two locally generated registration units in a temporary Git checkout. Dependency outputs exist only in those test fixtures; live configuration has no mock dependency outputs. Tests also verify that a mock `plan` stops before module download. No resource plan, cloud apply, model call or investigation is performed.

See [verification](docs/verification.md) for the checks actually executed and [deployment operations](docs/operations.md) for the enterprise pipeline contract.

## Prepare an ad-hoc request

The examples are not submitted automatically. Copy and edit `examples/task-request.json`, select a unique ID and a released capability, and use only enabled CI/CD infrastructure sources. The `-design` capability in the example is not a runnable release.

```bash
uv run --frozen python scripts/register.py \
  --environment dev --manifest /path/to/reviewed-request.json
uv run --frozen python scripts/check.py --base-ref origin/main
```

The helper creates a dedicated unit and `manifest.json` without overwriting an ID. Review and commit those files. Once infrastructure/modules/runtime are ready, the enterprise request-registration pipeline plans and applies **only that unit**, with a restricted request-publisher identity. Its GCS `OBJECT_FINALIZE` notification reaches Pub/Sub; the deployed dispatcher admits the request and starts the worker Job. The pipeline registers intent and exits.

## Scheduled and operator tasks

Edit `schedules/<environment>/registry.json` for reviewed schedules. Initially both registries are empty and the native Pub/Sub Scheduler heartbeat is paused. Pilot cron syntax accepts a minute, every minute, or every N minutes with remaining fields `*`, always UTC. Broader schedules need explicit schema/runtime compatibility work. Scheduling decisions, overlap handling, deduplication and run execution belong to the dispatcher and SQL.

Operator cancellation/pause/resume uses `scripts/register.py --kind control-request` and a separately authorized operations path/pipeline identity. File location or a claimed operator name grants no permission. Ordinary request authors must not be able to approve operator changes or use operator credentials.

Per-run memory, SQL migrations, query builders, backend credentials, source authorization and model execution belong in the runtime, module and GitOps repositories and remain implementation work. This repository configures their hosting and integration contracts. No credentials, Terraform state, saved plans or raw output exports belong in Git.
