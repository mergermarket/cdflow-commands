"""CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow release [<version>] [options]
    cdflow deploy <environment> <version> [options]
    cdflow destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>
    -v, --verbose

"""
import logging
import os
from os import unlink
from shutil import rmtree
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
from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.terragrunt import S3BucketFactory, write_terragrunt_config
from cdflow_commands.plugins.ecs import (
    Deploy, DeployConfig, ECSPlugin, Release, ReleaseConfig, Destroy,
    ECSEventIterator, ECSMonitor
)


def run(argv):
    try:
        _run(argv)
    except UserFacingError as err:
        logger.error(err)
        sys.exit(1)
    finally:
        try:
            rmtree('.terraform/')
        except OSError:
            logger.debug('No path .terraform/ to remove')
        try:
            unlink('.terragrunt')
        except OSError:
            logger.debug('No path .terragrunt to remove')


def _run(argv):
    args = docopt(__doc__, argv=argv)

    conditionally_set_debug(args['--verbose'])

    metadata = load_service_metadata()
    global_config = load_global_config(
        metadata.account_prefix, metadata.aws_region
    )
    root_session = Session(region_name=metadata.aws_region)

    component_name = get_component_name(args['--component'])
    version = args['<version>']
    environment_name = args['<environment>']

    ecs_plugin = build_ecs_plugin(
        environment_name, component_name, version,
        metadata, global_config, root_session
    )

    if args['release']:
        ecs_plugin.release()
    elif args['deploy']:
        ecs_plugin.deploy()
    elif args['destroy']:
        ecs_plugin.destroy()


def conditionally_set_debug(verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Debug logging on')


def build_ecs_plugin(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    release_factory = build_release_factory(
        component_name, version, metadata, global_config, root_session
    )

    deploy_factory = build_deploy_factory(
        environment_name, component_name, version,
        metadata, global_config, root_session
    )

    destroy_factory = build_destroy_factory(
        environment_name, component_name, metadata, global_config, root_session
    )

    deploy_monitor_factory = build_deploy_monitor_factory(
        metadata, global_config, environment_name, component_name, version,
        root_session
    )

    return ECSPlugin(
        release_factory,
        deploy_factory,
        destroy_factory,
        deploy_monitor_factory
    )


def build_release_factory(
    component_name, version, metadata, global_config, root_session
):
    def _release_factory():
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

        return Release(
            release_config, ecr_client, component_name, version
        )
    return _release_factory


def build_deploy_factory(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    def _deploy_factory():
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
        deploy_config = DeployConfig(
            team=metadata.team,
            dev_account_id=global_config.dev_account_id,
            platform_config_file=platform_config_file,
        )
        return Deploy(
            boto_session, component_name, environment_name, version,
            metadata.ecs_cluster, deploy_config
        )
    return _deploy_factory


def build_destroy_factory(
    environment_name, component_name, metadata, global_config, root_session
):
    def _destroy_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

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
        return Destroy(
            boto_session, component_name, environment_name, s3_bucket
        )
    return _destroy_factory


def build_deploy_monitor_factory(
    metadata, global_config, environment_name,
    component_name, version, root_session
):
    def _deploy_monitor_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

        boto_session = assume_role(
            root_session,
            account_id,
            get_role_session_name(os.environ)
        )
        events = ECSEventIterator(
            metadata.ecs_cluster, environment_name,
            component_name, version, boto_session
        )
        return ECSMonitor(events)
    return _deploy_monitor_factory
