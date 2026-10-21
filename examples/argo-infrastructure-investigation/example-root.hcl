locals {
  example_root = "${get_repo_root()}/examples/argo-infrastructure-investigation"
  scenario     = jsondecode(file("${local.example_root}/scenario.json"))
  enabled      = jsondecode(file("${local.example_root}/deployment.json")).deployment_enabled
}

terraform_binary              = "terraform"
terraform_version_constraint  = "= 1.16.6"
terragrunt_version_constraint = "= 1.1.6"
prevent_destroy               = true

remote_state {
  backend = "gcs"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket                 = local.scenario.state_bucket
    prefix                 = "${local.scenario.state_prefix}/${path_relative_to_include("example")}"
    project                = "mock-enterprise-state"
    location               = local.scenario.region
    skip_bucket_creation   = true
    skip_bucket_versioning = true
  }
}

generate "provider" {
  path      = "example-provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    provider "google" {
      project = "${local.scenario.project_id}"
      region  = "${local.scenario.region}"
    }
  EOF
}

terraform {
  before_hook "example_readiness" {
    commands = ["init-from-module", "init", "plan", "apply", "destroy", "output"]
    execute  = ["python3", "${local.example_root}/guard.py"]
  }
}

inputs = { deployment_enabled = local.enabled }
