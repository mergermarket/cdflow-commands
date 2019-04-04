"""
cdflow

Create and manage software services using continuous delivery.

Usage:
    cdflow release (--platform-config <platform_config>)...
                   [--release-data=key=value]... <version> [options]
    cdflow deploy <environment> <version> [options]
    cdflow destroy <environment> [options]
    cdflow shell <environment> [options]

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
import pty

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
from cdflow_commands.state import terraform_state, migrate_state
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


def swap_account_schemes_back_if_component_flag(
    account_scheme, old_scheme, args,
):
    if args['--component'] and old_scheme:
        account_scheme, old_scheme = old_scheme, None

        highlight_log_message(
            ('Passing the --component flag to cdflow is deprecated',)
        )

    return account_scheme, old_scheme


def highlight_log_message(messages):
    stars_count = max(len(m) for m in messages)
    logger.warning('*'*stars_count)
    for message in messages:
        logger.warning(message)
    logger.warning('*'*stars_count)


def get_command_function(args):
    if args['release']:
        return run_release
    elif args['shell']:
        return run_shell
    else:
        return run_non_release_command


def _run(argv):
    args = docopt(__doc__, argv=argv)

    conditionally_set_debug(args['--verbose'])

    manifest = load_manifest()
    root_session = Session()

    team = manifest.team
    component = get_component_name(args['--component'])

    account_scheme, old_scheme = build_account_scheme_s3(
        root_session.resource('s3'), manifest.account_scheme_url,
        team, component,
    )

    account_scheme, old_scheme = swap_account_schemes_back_if_component_flag(
        account_scheme, old_scheme, args,
    )

    root_session = Session(region_name=account_scheme.default_region)

    if old_scheme:
        logger.debug(
            f'Migrating state from {old_scheme.release_account.alias} '
            f'to {account_scheme.release_account.alias}'
        )
        migrate_state(
            root_session, account_scheme, old_scheme, team, component,
        )

    release_account_session = assume_role(
        root_session, account_scheme.release_account,
    )

    get_command_function(args)(
        root_session,
        release_account_session,
        account_scheme,
        manifest,
        args,
    )

    if old_scheme:
        new_url = old_scheme.raw_scheme\
            .get('upgrade-account-scheme', {}).get('new-url')
        highlight_log_message((
            'Account scheme has been upgraded.',
            (
                'Manually change account_scheme_url key in '
                f'cdflow.yml to {new_url}'
            ),
        ))


def run_release(_, release_account_session, account_scheme, manifest, args):
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
        multi_region=manifest.multi_region,
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


def run_shell(
    root_session, release_account_session, account_scheme, manifest, args
):
    os.chdir(INFRASTRUCTURE_DEFINITIONS_PATH)
    cwd = os.getcwd()

    environment = args['<environment>']
    component_name = get_component_name(args['--component'])

    infrastructure_account_session = assume_infrastructure_account_role(
        account_scheme, environment, root_session
    )
    if account_scheme.classic_metadata_handling:
        metadata_account_session = infrastructure_account_session
    else:
        metadata_account_session = release_account_session

    state = terraform_state(
        cwd, '.',
        metadata_account_session, environment, component_name,
        manifest.tfstate_filename, account_scheme, manifest.team,
    )
    state.init(True)

    with open('/tmp/shrc', 'w+') as f:
        f.write('export PS1="terraform # "')
    pty.spawn(('bash', '--rcfile', '/tmp/shrc',))


def run_non_release_command(
    root_session, release_account_session, account_scheme, manifest, args
):
    assert args['deploy'] or args['destroy']

    component_name = get_component_name(args['--component'])

    if args['destroy']:
        version = find_latest_release_version(
            release_account_session, account_scheme, manifest.team,
            component_name,
        )
    else:
        version = args['<version>']

    with fetch_release(
        release_account_session, account_scheme, manifest.team, component_name,
        version,
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
    account = account_scheme.account_for_environment(environment)
    logger.debug(f'Assuming role {account.role} in {account.id}')

    return assume_role(root_session, account)


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
            path_to_release, account_scheme, metadata_account_session,
            infrastructure_account_session, manifest, args, environment,
            component_name
        )


def run_deploy(
    path_to_release, account_scheme, metadata_account_session,
    infrastructure_account_session, manifest, args, environment, component_name
):
    state = terraform_state(
        path_to_release, INFRASTRUCTURE_DEFINITIONS_PATH,
        metadata_account_session, environment, component_name,
        manifest.tfstate_filename, account_scheme, manifest.team,
    )
    state.init()

    secrets = {
        'secrets': get_secrets(
            environment, manifest.team,
            component_name, infrastructure_account_session
        )
    }

    deploy = Deploy(
        environment, path_to_release, secrets,
        account_scheme, infrastructure_account_session
    )
    deploy.run(args['--plan-only'])


def run_destroy(
    path_to_release, account_scheme, metadata_account_session,
    infrastructure_account_session, manifest, args, environment, component_name
):
    state = terraform_state(
        path_to_release, INFRASTRUCTURE_DEFINITIONS_PATH,
        metadata_account_session, environment, component_name,
        manifest.tfstate_filename, account_scheme, manifest.team,
    )
    state.init()

    secrets = {
        'secrets': get_secrets(
            environment, manifest.team,
            component_name, infrastructure_account_session
        )
    }

    destroy = Destroy(
        environment, path_to_release, secrets,
        account_scheme, infrastructure_account_session
    )

    logger.info(
        f'Planning destruction of {component_name} in {environment}'
    )

    destroy.run(args['--plan-only'])


def conditionally_set_debug(verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Debug logging on')
