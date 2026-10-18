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
  source = "git::${local.module_repo}//modules/database?ref=${local.module_ref}"
}

dependency "identities" {
  config_path = "../identities"
}

inputs = {
  project_id                     = local.env.project_id
  region                         = local.env.region
  environment                    = local.env.environment
  labels                         = local.labels
  instance_name                  = "harness-${local.env.environment}"
  edition                        = "ENTERPRISE"
  database_version               = local.env.database.version
  tier                           = local.env.database.tier
  availability_type              = local.env.database.availability_type
  disk_size_gb                   = local.env.database.disk_size_gb
  disk_autoresize_limit_gb       = local.env.database.disk_autoresize_limit_gb
  point_in_time_recovery_enabled = local.env.database.pitr_enabled
  deletion_protection            = local.env.database.deletion_protection
  private_network                = local.env.network.self_link
  ipv4_enabled                   = false
  iam_authentication             = true
  cmek_key_name                  = null
  runtime_database               = "harness"
  runtime_service_accounts = {
    for name in ["dispatcher", "worker", "migration"] : name => dependency.identities.outputs.workload_configuration[name].gsa_email
  }
  create_shared_budget_database = local.env.environment == "prod"
  shared_budget_database_name   = "query_budget"
  # Populate the reviewed dev/prod budget client list before enabling live
  # telemetry. No other environment's Terraform state is read here.
  shared_budget_clients = local.env.environment == "prod" ? jsondecode(file("${get_repo_root()}/shared/query-budget-clients.json")).service_accounts : []
}
