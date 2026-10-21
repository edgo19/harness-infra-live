include "example" {
  path = find_in_parent_folders("example-root.hcl")
}
locals {
  scenario = jsondecode(file("${get_repo_root()}/examples/argo-infrastructure-investigation/scenario.json"))
}
terraform {
  source = "${dirname(get_repo_root())}/harness-terraform-modules//examples/argo-infrastructure-investigation/schedule-registry"
}
inputs = {
  bucket_name = local.scenario.bucket_names.configuration
  registries  = { initial = jsondecode(file("${get_repo_root()}/examples/argo-infrastructure-investigation/registry.json")) }
  current_key = "initial"
}
