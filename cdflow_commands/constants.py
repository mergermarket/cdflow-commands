from os import path

CONFIG_BASE_PATH = 'config'
GLOBAL_CONFIG_FILE = path.join(CONFIG_BASE_PATH, 'common.json')

PLATFORM_CONFIG_BASE_PATH = 'platform-config'

TERRAFORM_BINARY = 'terraform'
INFRASTRUCTURE_DEFINITIONS_PATH = 'infra'

CDFLOW_BASE_PATH = '/cdflow'
TERRAFORM_DESTROY_DEFINITION = path.join(CDFLOW_BASE_PATH, 'tf-destroy')

RELEASE_METADATA_FILE = 'release.json'
