# Harness Infrastructure Live

Terragrunt live configuration for harness environments. This repository pins immutable module revisions and holds reviewed request, schedule, and operational-control configuration without secrets.

Reusable modules belong in `harness-terraform-modules`; Kubernetes workloads belong in `harness-gitops`.

See the [repository architecture](https://github.com/edgo19/harness-agent-framework/blob/main/docs/design/2026-10-18/repositories-delivery.md) for the ownership and delivery contract.
