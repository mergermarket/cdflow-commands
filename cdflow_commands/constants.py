from os import path

CONFIG_BASE_PATH = 'config'
GLOBAL_CONFIG_FILE = path.join(CONFIG_BASE_PATH, 'common.json')

PLATFORM_CONFIG_BASE_PATH = 'platform-config'

TERRAFORM_BINARY = 'terraform'
INFRASTRUCTURE_DEFINITIONS_PATH = 'infra'

CDFLOW_BASE_PATH = '/cdflow'

RELEASE_METADATA_FILE = 'release.json'
ACCOUNT_SCHEME_FILE = 'account-scheme.json'

# More in: https://www.terraform.io/docs/commands/plan.html#detailed-exitcode
TERRAFORM_PLAN_EXIT_CODE_SUCCESS_NO_CHANGES = 0
TERRAFORM_PLAN_EXIT_CODE_ERROR = 1
TERRAFORM_PLAN_EXIT_CODE_SUCCESS_CHANGES_PRESENT = 2
