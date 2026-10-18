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
  source = "git::${local.module_repo}//modules/identities?ref=${local.module_ref}"
}

inputs = {
  identity_project_id = local.env.project_id
  gke_project_id      = local.env.gke_project_id
  environment         = local.env.environment
  labels              = local.labels
  workloads = {
    worker     = { namespace = "harness-workers-${local.env.environment}", ksa_name = "harness-worker" }
    gateway    = { namespace = "harness-control-${local.env.environment}", ksa_name = "harness-gateway" }
    dispatcher = { namespace = "harness-control-${local.env.environment}", ksa_name = "harness-dispatcher" }
    telemetry  = { namespace = "harness-tools-${local.env.environment}", ksa_name = "harness-telemetry" }
    migration  = { namespace = "harness-control-${local.env.environment}", ksa_name = "harness-migration" }
  }
  # Regional/model allowlisting is a runtime policy, not provided by this role.
  project_roles_by_workload = { worker = ["roles/aiplatform.user"] }
}
