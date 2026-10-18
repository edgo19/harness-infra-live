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
  source = "git::${local.module_repo}//modules/messaging?ref=${local.module_ref}"
}

dependency "identities" {
  config_path = "../identities"
}

dependency "storage" {
  config_path = "../storage"
}

inputs = {
  project_id                        = local.env.project_id
  environment                       = local.env.environment
  labels                            = local.labels
  requests_bucket                   = dependency.storage.outputs.bucket_names.requests
  operations_bucket                 = dependency.storage.outputs.bucket_names.operations
  requests_prefix                   = "requests/"
  operations_prefix                 = "operations/"
  notification_event_types          = ["OBJECT_FINALIZE"]
  dispatcher_service_account        = dependency.identities.outputs.workload_configuration.dispatcher.gsa_email
  ack_deadline_seconds              = 60
  message_retention_seconds         = 604800
  dead_letter_max_delivery_attempts = 10
  retry_minimum_seconds             = 10
  retry_maximum_seconds             = 600
  # The module must include Storage publisher and Pub/Sub DLQ forwarding IAM.
  # Operations have their own subscription; tick only wakes SQL due evaluation.
}
