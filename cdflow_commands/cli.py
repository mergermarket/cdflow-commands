"""CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow-commands release [<version>] [options]
    cdflow-commands deploy <environment> <version> [options]
    cdflow-commands destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>

"""
import os
import sys

from boto3.session import Session
from docopt import docopt

from cdflow_commands.config import (
    load_service_metadata,
    load_global_config,
    get_role_session_name,
    assume_role,
    get_component_name,
    get_platform_config_path
)
from cdflow_commands.release import Release, ReleaseConfig
from cdflow_commands.deploy import Deploy, DeployConfig
from cdflow_commands.destroy import Destroy
from cdflow_commands.terragrunt import S3BucketFactory, write_terragrunt_config
from cdflow_commands.ecs_monitor import ECSEventIterator, ECSMonitor
from cdflow_commands.exceptions import UserError


def run(argv):
    try:
        _run(argv)
    except UserError as err:
        print(str(err), file=sys.stderr)


def _run(argv):
    args = docopt(__doc__, argv=argv)
    metadata = load_service_metadata()
    global_config = load_global_config(
        metadata.account_prefix, metadata.aws_region
    )
    root_session = Session(region_name=metadata.aws_region)

    component_name = get_component_name(args['--component'])

    if args['release']:
        _run_release(
            args, metadata, global_config, root_session, component_name
        )
    elif args['deploy'] or args['destroy']:
        _run_infrastructure_commmand(
            args, metadata, global_config, root_session, component_name
        )


def _run_release(args, metadata, global_config, root_session, component_name):
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


def _run_infrastructure_commmand(
    args, metadata, global_config, root_session, component_name
):
    environment_name = args['<environment>']
    boto_session, platform_config_file, s3_bucket = _setup_for_infrastructure(
        environment_name, component_name, metadata, global_config, root_session
    )
    if args['deploy']:
        _run_deploy(
            metadata.team,
            platform_config_file,
            boto_session,
            component_name,
            environment_name,
            args['<version>'],
            metadata.ecs_cluster,
            global_config
        )
    elif args['destroy']:
        _run_destroy(boto_session, component_name, environment_name, s3_bucket)


def _setup_for_infrastructure(
    environment_name, component_name, metadata, global_config, root_session
):
    is_prod = environment_name == 'live'
    if is_prod:
        account_id = global_config.prod_account_id
    else:
        account_id = global_config.dev_account_id

    platform_config_file = get_platform_config_path(
        metadata.account_prefix, metadata.aws_region, is_prod
    )
    boto_session = assume_role(
        root_session,
        account_id,
        get_role_session_name(os.environ)
    )
    s3_bucket_factory = S3BucketFactory(boto_session, account_id)
    s3_bucket = s3_bucket_factory.get_bucket_name()
    write_terragrunt_config(
        metadata.aws_region, s3_bucket, environment_name, component_name
    )
    return boto_session, platform_config_file, s3_bucket


def _run_deploy(
    team, platform_config_file, boto_session, component_name, environment_name,
    version, ecs_cluster, global_config
):
    deploy_config = DeployConfig(
        team=team,
        dev_account_id=global_config.dev_account_id,
        platform_config_file=platform_config_file,
    )
    deployment = Deploy(
        boto_session, component_name, environment_name, version,
        ecs_cluster, deploy_config
    )
    deployment.run()
    events = ECSEventIterator(
        ecs_cluster, environment_name, component_name, version, boto_session
    )
    monitor = ECSMonitor(events)
    monitor.wait()


def _run_destroy(boto_session, component_name, environment_name, s3_bucket):
    destroyment = Destroy(
        boto_session, component_name, environment_name, s3_bucket
    )
    destroyment.run()
