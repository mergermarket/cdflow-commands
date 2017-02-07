"""CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow-commands release [<version>] [options]
    cdflow-commands deploy <environment> <version> [options]

Options:
    -c <component_name>, --component <component_name>

"""
import os

from boto3.session import Session
from docopt import docopt

from cdflow_commands.config import (
    load_service_metadata,
    load_global_config,
    get_role_session_name,
    assume_role,
    get_component_name
)
from cdflow_commands.release import Release, ReleaseConfig
from cdflow_commands.deploy import Deploy, DeployConfig


def run(argv):
    args = docopt(__doc__, argv=argv)

    metadata = load_service_metadata()
    global_config = load_global_config(
        metadata.account_prefix, metadata.aws_region
    )
    root_session = Session(region_name=metadata.aws_region)
    component_name = get_component_name(args['--component'])

    if args['release']:
        run_release(
            args, metadata, global_config, root_session, component_name
        )
    elif args['deploy']:
        run_deploy(
            args, metadata, global_config, root_session, component_name
        )


def run_release(args, metadata, global_config, root_session, component_name):
    boto_session = assume_role(
        root_session,
        global_config.dev_account_id,
        get_role_session_name(os.environ)
    )
    ecr_client = boto_session.client('ecr')
    release_config = ReleaseConfig(
        global_config.dev_account_id,
        global_config.prod_account_id,
        metadata.aws_region
    )

    release = Release(
        release_config, ecr_client, component_name, args['<version>']
    )
    release.create()


def run_deploy(args, metadata, global_config, root_session, component_name):

    platform_config_file = './infra/platform-config/{}/{}/{}.json'.format(
        metadata.account_prefix, 'dev', metadata.aws_region
    )
    deploy_config = DeployConfig(
        team=metadata.team,
        account_id=global_config.dev_account_id,
        platform_config_file=platform_config_file,
    )
    boto_session = assume_role(
        root_session,
        global_config.dev_account_id,
        get_role_session_name(os.environ)
    )
    deployment = Deploy(
        boto_session, component_name, args['<environment>'], args['<version>'],
        deploy_config
    )
    deployment.run()
