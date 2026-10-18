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
  source = "git::${local.module_repo}//modules/storage?ref=${local.module_ref}"
}

dependency "identities" {
  config_path = "../identities"
}

inputs = {
  project_id  = local.env.project_id
  region      = local.env.region
  environment = local.env.environment
  labels      = local.labels
  bucket_names = {
    requests      = local.env.storage.requests
    configuration = local.env.storage.configuration
    operations    = local.env.storage.operations
    evidence      = local.env.storage.evidence
    reports       = local.env.storage.reports
  }
  cmek_key_name               = local.env.storage.cmek_key_name
  workload_configuration      = dependency.identities.outputs.workload_configuration
  evidence_retention_days     = 30
  report_retention_days       = 90
  managed_object_expiration   = false
  force_destroy               = false
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true
  # Registration publishers are existing pipeline identities. Their scoped
  # grants belong to the enterprise pipeline owner, not application workloads.
}
