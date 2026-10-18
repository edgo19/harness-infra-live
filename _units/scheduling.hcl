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
  source = "git::${local.module_repo}//modules/scheduling?ref=${local.module_ref}"
}

dependency "messaging" {
  config_path = "../messaging"
}

inputs = {
  project_id    = local.env.project_id
  region        = local.env.region
  environment   = local.env.environment
  tick_topic_id = dependency.messaging.outputs.tick_topic_id
  schedule      = "* * * * *"
  time_zone     = "UTC"
  paused        = true
  # Unpause by reviewed configuration only after dispatcher/SQL readiness.
  # Native Pub/Sub target; no user GSA, HTTP target or OIDC client.
}
