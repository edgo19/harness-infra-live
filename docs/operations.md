# Delivery, state and runtime intent

## Separate enterprise pipeline permissions

Use existing enterprise WIF/ADC. No downloaded service-account keys, client secret values or interactive login steps are introduced. Plan artifacts, Terraform output JSON and state may contain sensitive data and stay in access-controlled enterprise storage.

| Change | Execution path | Authority |
|---|---|---|
| identities/storage/messaging/database/scheduling/secrets | Reviewed platform plan, then the exact approved saved plan | Harness provisioner; restricted infrastructure state and approved IAM/resource administration |
| new request directory | Plan/apply that single request unit | Request publisher; only request-bucket object creation/required metadata reads and its state access |
| schedule registry | Plan/apply that environment's `schedules` unit | Schedule publisher; configuration bucket only plus its state access |
| new operation directory | Independently approved operator registration unit | Operator publisher; operations bucket only plus separate state access |
| Kubernetes/application release | Separate GitOps change consumed by Argo | Existing Argo deployment controls |

Enforce these differences using existing repository protection/approval rules, pipeline path selection and cloud IAM. A Python validator or folder separation alone is not authorization. Ordinary task authors must not be able to change `_units`, root configuration, module locks, environment inputs, scripts or pipeline definitions using their request approval path. Those changes require platform-owner review and must not execute with the request publisher's credentials. Operators must have a distinct approval and credential path even within the same repository.

Never run `terragrunt run --all apply` from this repository root. It mixes environments, infrastructure, requests and operator actions. For platform bootstrap select only reviewed infrastructure units; do not include registrations. For request/control pipelines select exact changed new directories and fail on changes outside their allowed paths. Do not use `-target` to hide dependencies.

## Configure real infrastructure later

1. Implement/version the reusable modules with the interfaces in [module-contracts.md](module-contracts.md), including provider/resource/IAM tests. Replace the appropriate environment's `null` commit in `dependency-locks/modules.json` with the reviewed 40-character commit. Dev/prod can promote different revisions without floating tags/branches.
2. Replace all `mock-*` identifiers in the selected environment with approved project IDs, globally unique buckets, existing GKE project, private network and enterprise state settings. State is independently namespaced per environment/unit; operator and request publisher identities must have restricted state-object access. Use a separate state bucket for operator/infrastructure roles if enterprise prefix-scoped access is unavailable.
3. Verify platform-owned APIs, existing state bucket locking/versioning/access, private SQL routing, pipeline federation, metadata-enabled GKE and SQL bootstrap owner. Set prerequisite flags only when confirmed. An asserted flag is not a functional test.
4. Select approved Vertex model IDs supported in `us-east4`. Keep live telemetry disabled until both environments reference the same provisioned shared budget DB, its exact clients are registered and its SQL procedure boundary/concurrency have been tested.
5. Enable deployment for that environment and run `uv run --frozen python scripts/check.py --ready --environment dev`. This checks reviewed declarations; module initialization and cloud plan still have to succeed. The Terragrunt hook repeats this check before source download and plan/apply.
6. Plan in dependency order: identities → storage/database → messaging → scheduling; secret bindings are independent. Initially the Scheduler is paused and no schedule/request runs are registered. Use an approved plan/apply pipeline, generate provider locks and inspect IAM/network/data-retention decisions before apply.
7. Run enterprise SQL bootstrap, then application migrations and GitOps deployment. Validate runtime health, ID-token audiences, SQL, artifacts, permitted model calls and backend scope. Do not enable investigations based only on successful Terraform apply.
8. Publish the initial empty registry, then reviewed schedules/requests. Unpause the heartbeat by reviewed configuration only after runtime admission/reconciliation is tested. With no dispatcher, Pub/Sub can retain notifications only within configured retention; verify subscriptions exist before publishing requests and reconcile retained objects if bootstrap messages predate notification/subscription creation.

The root sets `prevent_destroy=true` and configures an existing GCS backend without creating it. Run Terragrunt with `--disable-bucket-update --backend-require-bootstrap` in enterprise execution. Reusing the bucket must not grant its administration to application pipelines. Protect locking/state objects with enterprise controls; never use `-lock=false` routinely. The actual prefix is `harness/<env>/environments/<env>/region/<unit>`, including a request/operation ID for individual registrations. Do not change it casually.

The readiness hook is an accident guard that a repository administrator could edit. Cloud IAM, enterprise approval and state controls remain authoritative. The hook deliberately blocks even `init` and dependency output reads with the shipped mock values, before fetching a nonexistent module revision. Pure HCL rendering and test fixtures do not assert deployment readiness.

## Inspect the exact saved plan

Once real modules are available, the selected unit pipeline should execute the equivalent of these commands with approved paths and a protected temporary/artifact directory:

```bash
# Working directory: the one approved Terragrunt unit.
uv run --project /path/to/harness-infra-live --frozen terragrunt \
  --disable-bucket-update --backend-require-bootstrap plan -out=/secure/run/approved.tfplan
uv run --project /path/to/harness-infra-live --frozen terragrunt \
  show -json /secure/run/approved.tfplan > /secure/run/approved.tfplan.json
uv run --project /path/to/harness-infra-live --frozen python \
  /path/to/harness-infra-live/scripts/check_plan.py /secure/run/approved.tfplan.json
```

Add `--registration` to `check_plan.py` for request/control units: only create/no-op immutable GCS objects with PREVENT are permitted. Run `scripts/check.py --base-ref <trusted-merge-base>` against the reviewed base commit to reject changed/removed committed registrations. Apply that same saved plan, never regenerate it after approval. The plan checker rejects deletion/replacement everywhere and obvious broad IAM/key resources, but does not prove comprehensive least privilege. Enterprise plan review remains necessary. Schedule registry plans intentionally allow their mutable pointer update and do not use the registration-only mode.

## Registration lifetime and cancellation

Each request/control unit owns one immutable intent. A new intent requires a new ID, directory and state. Runtime deduplication additionally uses ID/hash and retains tombstones beyond replay horizons. No `timestamp()`, UUID regeneration or notification publication occurs during ordinary drift checks.

Keep TF-managed request/control objects: deleting them via lifecycle or externally can cause Terraform drift repair to recreate an object and emit a new notification. The runtime must still deduplicate. There is no automatic retirement command in this release. A future explicit retirement workflow must coordinate runtime tombstones and supported provider PREVENT/ABANDON/state handling. Deleting a Git file/object/state is not cancellation.

To cancel a run, register `ControlRequest/v1` in `operations` with the operator-only identity. Dispatcher independently validates the approved source, schema, target and idempotency and reconciles the cancellation. Previously authorized in-flight reads can finish within their backend limits. Schedule disable/pause is effective after runtime reconciliation, not merely after Git merge or registry upload. Report lag and audit operator operations in the runtime.

## Export nonsecret deployment information

Capture `terragrunt output -json` for identities/storage/messaging/database to protected `identities.json`, `storage.json`, `messaging.json`, `database.json` files. Only the provisioner/promotion workflow needs those infrastructure outputs; restricted request publishers do not. Do not commit these raw exports.

```bash
uv run --frozen python scripts/export_contract.py --environment dev \
  --outputs-dir /secure/run/outputs \
  --output deployment-contracts/dev/revision-001.json
```

The exporter requires deployment readiness, accepts only explicitly nonsensitive outputs, verifies workload/bucket/project/environment identity, and whitelists nested fields. It refuses to overwrite a file. Review the resulting `DeploymentContract/v1` and promote it through the GitOps repository with the approved application release. Argo never reads Terraform state. This cloud contract is not a complete application release: capability/skills/query policy/source inventory/image digests and KSA annotations are separately reviewed GitOps inputs. Secret payloads and temporary tokens are absent.
