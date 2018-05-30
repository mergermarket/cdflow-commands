"""
cdflow

Create and manage software services using continuous delivery.

Usage:
    cdflow release (--platform-config <platform_config>)...
                   [--release-data=key=value]... <version> [options]
    cdflow deploy <environment> <version> [options]
    cdflow destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>
    -v, --verbose
    -p, --plan-only

"""
import os
import logging
import sys
from shutil import rmtree
from subprocess import check_output

from boto3.session import Session

from cdflow_commands.config import (
    assume_role, get_component_name, load_manifest, build_account_scheme_s3,
    build_account_scheme_file
)
from cdflow_commands.constants import (
    INFRASTRUCTURE_DEFINITIONS_PATH, ACCOUNT_SCHEME_FILE
)
from cdflow_commands.deploy import Deploy
from cdflow_commands.destroy import Destroy
from cdflow_commands.exceptions import UnknownProjectTypeError, UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.plugins.ecs import ReleasePlugin as ECSReleasePlugin
from cdflow_commands.plugins.aws_lambda import (
    ReleasePlugin as LambdaReleasePlugin
)
from cdflow_commands.release import (
    Release, fetch_release, find_latest_release_version,
)
from cdflow_commands.secrets import get_secrets
from cdflow_commands.state import initialise_terraform, remove_state
from docopt import docopt


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


class NoopReleasePlugin:

    def create(*args):
        return {}


def _run(argv):
    args = docopt(__doc__, argv=argv)

    conditionally_set_debug(args['--verbose'])

    manifest = load_manifest()
    root_session = Session()

    account_scheme = build_account_scheme_s3(
        root_session.resource('s3'), manifest.account_scheme_url, manifest.team
    )
    root_session = Session(region_name=account_scheme.default_region)
    release_account_session = assume_role(
        root_session, account_scheme.release_account.id,
        account_scheme.default_region,
    )

    if args['release']:
        run_release(release_account_session, account_scheme, manifest, args)
    else:
        run_non_release_command(
            root_session, release_account_session, account_scheme, manifest,
            args
        )


def run_release(release_account_session, account_scheme, manifest, args):
    commit = check_output(
        ['git', 'rev-parse', 'HEAD']
    ).decode('utf-8').strip()
    release = Release(
        boto_session=release_account_session,
        release_bucket=account_scheme.release_bucket,
        platform_config_paths=args['<platform_config>'],
        release_data=args['--release-data'],
        version=args['<version>'],
        commit=commit,
        component_name=get_component_name(args['--component']),
        team=manifest.team,
        account_scheme=account_scheme,
    )

    if manifest.type == 'docker':
        plugin = ECSReleasePlugin(release, account_scheme)
    elif manifest.type == 'lambda':
        plugin = LambdaReleasePlugin(release, account_scheme)
    elif manifest.type == 'infrastructure':
        plugin = NoopReleasePlugin()
    else:
        raise UnknownProjectTypeError('Unknown project type: {}'.format(
            manifest.type
        ))

    release.create(plugin)


def run_non_release_command(
    root_session, release_account_session, account_scheme, manifest, args
):
    assert args['deploy'] or args['destroy']

    component_name = get_component_name(args['--component'])

    if args['destroy']:
        version = find_latest_release_version(
            release_account_session, account_scheme.release_bucket,
            component_name,
        )
    else:
        version = args['<version>']

    with fetch_release(
        release_account_session, account_scheme.release_bucket,
        component_name, version,
    ) as path_to_release:
        logger.debug('Unpacked release: {}'.format(path_to_release))
        path_to_release = os.path.join(
            path_to_release, '{}-{}'.format(component_name, version)
        )
        run_non_release_command_on_release(
            args, path_to_release, manifest, component_name,
            root_session, release_account_session
        )


def assume_infrastructure_account_role(
    account_scheme, environment, root_session
):
    account_id = account_scheme.account_for_environment(environment).id
    logger.debug('Assuming role in {}'.format(account_id))

    return assume_role(
        root_session, account_id, account_scheme.default_region,
    )


def run_non_release_command_on_release(
    args, path_to_release, manifest, component_name, root_session,
    release_account_session
):
    account_scheme = build_account_scheme_file(os.path.join(
        path_to_release, ACCOUNT_SCHEME_FILE
    ), manifest.team)
    environment = args['<environment>']

    infrastructure_account_session = assume_infrastructure_account_role(
        account_scheme, environment, root_session
    )
    if account_scheme.classic_metadata_handling:
        metadata_account_session = infrastructure_account_session
    else:
        metadata_account_session = release_account_session

    if args['deploy']:
        run_deploy(
            path_to_release, account_scheme, metadata_account_session,
            infrastructure_account_session, manifest, args, environment,
            component_name
        )
    elif args['destroy']:
        run_destroy(
            path_to_release, metadata_account_session,
            infrastructure_account_session, manifest, args, environment,
            component_name, account_scheme
        )


def run_deploy(
    path_to_release, account_scheme, metadata_account_session,
    infrastructure_account_session, manifest, args, environment, component_name
):
    initialise_terraform(
        path_to_release, INFRASTRUCTURE_DEFINITIONS_PATH,
        metadata_account_session, environment, component_name,
        manifest.tfstate_filename, account_scheme.backend_s3_bucket,
        account_scheme.backend_s3_dynamodb_table
    )

    secrets = {
        'secrets': get_secrets(
            environment, manifest.team,
            component_name, metadata_account_session
        )
    }

    deploy = Deploy(
        environment, path_to_release, secrets,
        account_scheme, infrastructure_account_session
    )
    deploy.run(args['--plan-only'])


def run_destroy(
    path_to_release, metadata_account_session, infrastructure_account_session,
    manifest, args, environment, component_name, account_scheme
):
    initialise_terraform(
        path_to_release, '',
        metadata_account_session, environment, component_name,
        manifest.tfstate_filename, account_scheme.backend_s3_bucket,
        account_scheme.backend_s3_dynamodb_table
    )

    destroy = Destroy(infrastructure_account_session, path_to_release)

    plan_only = args['--plan-only']

    logger.info(
        f'Planning destruction of {component_name} in {environment}'
    )

    destroy.run(plan_only)

    if not plan_only:
        logger.info(
            f'Removing state for {component_name} in {environment}'
        )
        remove_state(
            metadata_account_session, environment, component_name,
            manifest.tfstate_filename, account_scheme.backend_s3_bucket
        )


def conditionally_set_debug(verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Debug logging on')
