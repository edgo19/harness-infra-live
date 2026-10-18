locals {
  settings = jsondecode(file("${get_terragrunt_dir()}/environment.json"))
}
