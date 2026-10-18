locals {
  repo_root    = get_repo_root()
  env          = read_terragrunt_config(find_in_parent_folders("environment.hcl")).locals.settings
  module_locks = jsondecode(file("${local.repo_root}/dependency-locks/modules.json"))
  module_ref   = coalesce(local.module_locks.environments[local.env.environment].commit, "0000000000000000000000000000000000000000")
  module_repo  = local.module_locks.repository
  labels = {
    application         = "harness"
    environment         = local.env.environment
    owner               = local.env.owner
    data_classification = "internal"
    cost_center         = local.env.cost_center
  }
}

terraform_binary              = "terraform"
terraform_version_constraint  = "= 1.16.6"
terragrunt_version_constraint = "= 1.1.6"
prevent_destroy               = true

# The enterprise owns this bucket. Terragrunt must not bootstrap or update it.
remote_state {
  backend = "gcs"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket                 = local.env.state.bucket
    prefix                 = "${local.env.state.prefix}/${path_relative_to_include("root")}"
    project                = local.env.state.project_id
    location               = local.env.region
    skip_bucket_creation   = true
    skip_bucket_versioning = true
  }
  disable_dependency_optimization = true
}

generate "providers" {
  path      = "providers.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    terraform {
      required_version = "= 1.16.6"
      required_providers {
        google = {
          source  = "hashicorp/google"
          version = "= 8.7.0"
        }
      }
    }
    provider "google" {
      project = "${local.env.project_id}"
      region  = "${local.env.region}"
    }
  EOF
}

terraform {
  # init-from-module runs before module download; other entries also guard an
  # already initialized cache. This is an accident guard, not an IAM boundary.
  before_hook "deployment_readiness" {
    commands = ["init-from-module", "init", "plan", "apply", "destroy", "import", "refresh", "state", "output"]
    execute  = ["python3", "${local.repo_root}/scripts/check.py", "--ready", "--environment", local.env.environment]
  }
}
