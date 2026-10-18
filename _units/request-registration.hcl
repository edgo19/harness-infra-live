locals {
  env          = read_terragrunt_config(find_in_parent_folders("environment.hcl")).locals.settings
  module_locks = jsondecode(file("${get_repo_root()}/dependency-locks/modules.json"))
  module_repo  = local.module_locks.repository
  module_ref   = coalesce(local.module_locks.environments[local.env.environment].commit, "0000000000000000000000000000000000000000")
  labels = {
    application         = "harness"
    environment         = local.env.environment
    owner               = local.env.owner
    data_classification = "internal"
    cost_center         = local.env.cost_center
  }
}

terraform {
  source = "git::${local.module_repo}//modules/request-registration?ref=${local.module_ref}"
}

dependencies {
  paths = ["../../storage"]
}

inputs = {
  bucket_name     = local.env.storage.requests
  request         = jsondecode(file("${get_terragrunt_dir()}/manifest.json"))
  object_prefix   = "requests/"
  deletion_policy = "PREVENT"
}
