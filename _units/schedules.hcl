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
  source = "git::${local.module_repo}//modules/schedule-registry?ref=${local.module_ref}"
}

dependencies {
  paths = ["../storage"]
}

inputs = {
  bucket_name      = local.env.storage.configuration
  registry         = jsondecode(file("${get_repo_root()}/schedules/${local.env.environment}/registry.json"))
  immutable_prefix = "schedule-registries/"
  pointer_name     = "schedules/current.json"
  # Module canonicalizes the payload, hashes it and stores an immutable
  # revision before updating the versioned current pointer.
}
