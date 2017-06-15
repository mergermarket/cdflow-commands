"""CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow release --platform-config <platform_config> [<version>] [options]
    cdflow deploy <environment>  [(--var <key=value>)...] [<version>] [options]
    cdflow destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>
    -v, --verbose
    -p, --plan-only

"""
import logging
import sys
from shutil import rmtree

from boto3.session import Session

from cdflow_commands.config import (
    assume_role, get_component_name, load_manifest, build_account_scheme
)
from cdflow_commands.exceptions import UnknownProjectTypeError, UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.plugins.ecs import (
    build_ecs_plugin, ReleasePlugin as ECSReleasePlugin
)
from cdflow_commands.plugins.infrastructure import build_infrastructure_plugin
from cdflow_commands.plugins.aws_lambda import build_lambda_plugin
from cdflow_commands.release import Release
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


def _run(argv):
    args = docopt(__doc__, argv=argv)

    conditionally_set_debug(args['--verbose'])

    manifest = load_manifest()
    root_session = Session()

    account_scheme = build_account_scheme(
        root_session.resource('s3'), manifest.account_scheme_url
    )

    if args['release']:
        session=assume_role(
            root_session, account_scheme.release_account.id, 'role-name'
        )
        release = Release(
            boto_session=session,
            release_bucket=account_scheme.release_bucket,
            platform_config_path=args['--platform-config'],
            version=args['<version>'],
            commit='hello',
            component_name=get_component_name(args['--component']),
        )
        plugin = ECSReleasePlugin(release, account_scheme)
        release.create(plugin)

    else:
        plugin = build_plugin(
            metadata.type,
            component_name=get_component_name(args['--component']),
            version=args['<version>'],
            environment_name=args['<environment>'],
            additional_variables=args['<key=value>'],
            metadata=metadata,
            global_config=global_config,
            root_session=root_session,
        )

        if args['deploy']:
            plugin.deploy()
        elif args['destroy']:
            plugin.destroy()


def build_plugin(project_type, **kwargs):
    if project_type == 'docker':
        plugin = build_ecs_plugin(
            kwargs['environment_name'],
            kwargs['component_name'],
            kwargs['version'],
            kwargs['metadata'],
            kwargs['global_config'],
            kwargs['root_session'],
            kwargs['plan_only']
        )
    elif project_type == 'infrastructure':
        plugin = build_infrastructure_plugin(
            kwargs['environment_name'],
            kwargs['component_name'],
            kwargs['additional_variables'],
            kwargs['metadata'],
            kwargs['global_config'],
            kwargs['root_session'],
            kwargs['plan_only']
        )
    elif project_type == 'lambda':
        plugin = build_lambda_plugin(
            kwargs['environment_name'],
            kwargs['component_name'],
            kwargs['version'],
            kwargs['metadata'],
            kwargs['global_config'],
            kwargs['root_session'],
            kwargs['plan_only']
        )
    else:
        raise UnknownProjectTypeError(
            'Unsupported project type specified in service.json'
        )
    return plugin


def conditionally_set_debug(verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Debug logging on')
