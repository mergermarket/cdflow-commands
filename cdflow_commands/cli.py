"""CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow release --platform-config <platform_config> <version> [options]
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
from subprocess import check_output

from boto3.session import Session

from cdflow_commands.config import (
    assume_role, get_component_name, load_manifest, build_account_scheme
)
from cdflow_commands.deploy import Deploy
from cdflow_commands.exceptions import UnknownProjectTypeError, UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.plugins.ecs import (
    build_ecs_plugin, ReleasePlugin as ECSReleasePlugin
)
from cdflow_commands.plugins.infrastructure import build_infrastructure_plugin
from cdflow_commands.plugins.aws_lambda import (
    build_lambda_plugin, ReleasePlugin as LambdaReleasePlugin
)
from cdflow_commands.release import Release, fetch_release
from cdflow_commands.state import initialise_terraform
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
        pass


def _run(argv):
    args = docopt(__doc__, argv=argv)

    conditionally_set_debug(args['--verbose'])

    manifest = load_manifest()
    root_session = Session()

    account_scheme = build_account_scheme(
        root_session.resource('s3'), manifest.account_scheme_url
    )

    release_account_session = assume_role(
        root_session, account_scheme.release_account.id, 'role-name'
    )

    if args['release']:
        commit = check_output(
            ['git', 'rev-parse', 'HEAD']
        ).decode('utf-8').strip()

        release = Release(
            boto_session=release_account_session,
            release_bucket=account_scheme.release_bucket,
            platform_config_path=args['--platform-config'],
            version=args['<version>'],
            commit=commit,
            component_name=get_component_name(args['--component']),
            team=manifest.team,
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
    elif args['deploy']:
        environment = args['<environment>']
        component_name = get_component_name(args['--component'])
        version = args['<version>']
        account_id = account_scheme.account_for_environment(environment).id

        deploy_account_session = assume_role(
            root_session, account_id, 'role-name'
        )

        with fetch_release(
            release_account_session, account_scheme.release_bucket,
            component_name, version,
        ) as path_to_release:
            initialise_terraform(
                '{}/infra'.format(path_to_release), deploy_account_session,
                environment, component_name
            )

            deploy = Deploy(
                environment, path_to_release,
                account_scheme, deploy_account_session
            )
            deploy.run(args['--plan-only'])


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
