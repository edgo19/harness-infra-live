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
  source = "git::${local.module_repo}//modules/secret-bindings?ref=${local.module_ref}"
}

inputs = {
  # Exact accessor grants for the existing ESO GSA on existing GSM secrets.
  # No payloads, new credential producers, GSA keys or platform WIF ownership.
  secret_bindings = local.env.secret_bindings
}
