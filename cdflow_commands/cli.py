"""
cdflow

Create and manage software services using continuous delivery.

Usage:
    cdflow release (--platform-config <platform_config>)... <version> [options]
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
    assume_role, get_component_name, load_manifest, build_account_scheme
)
from cdflow_commands.constants import (
    INFRASTRUCTURE_DEFINITIONS_PATH, TERRAFORM_DESTROY_DEFINITION,
)
from cdflow_commands.deploy import Deploy
from cdflow_commands.destroy import Destroy
from cdflow_commands.exceptions import UnknownProjectTypeError, UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.plugins.ecs import ReleasePlugin as ECSReleasePlugin
from cdflow_commands.plugins.aws_lambda import (
    ReleasePlugin as LambdaReleasePlugin
)
from cdflow_commands.release import Release, fetch_release
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

    account_scheme = build_account_scheme(
        root_session.resource('s3'), manifest.account_scheme_url
    )
    root_session = Session(region_name=account_scheme.default_region)

    release_account_session = assume_role(
        root_session, account_scheme.release_account.id,
        account_scheme.default_region,
    )

    if args['release']:
        run_release(release_account_session, account_scheme, manifest, args)
    elif args['deploy']:
        run_deploy(
            root_session, release_account_session,
            account_scheme, manifest, args,
        )
    elif args['destroy']:
        run_destroy(
            root_session, release_account_session,
            account_scheme, manifest, args
        )


def run_release(release_account_session, account_scheme, manifest, args):
    commit = check_output(
        ['git', 'rev-parse', 'HEAD']
    ).decode('utf-8').strip()

    release = Release(
        boto_session=release_account_session,
        release_bucket=account_scheme.release_bucket,
        platform_config_paths=args['<platform_config>'],
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


def run_deploy(
    root_session, release_account_session, account_scheme, manifest, args,
):
    environment = args['<environment>']
    component_name = get_component_name(args['--component'])
    version = args['<version>']

    if account_scheme.multiple_account_deploys:
        deploy_account_session = root_session
    else:
        account_id = account_scheme.account_for_environment(environment).id
        deploy_account_session = assume_role(
            root_session, account_id, account_scheme.default_region,
        )

    with fetch_release(
        release_account_session, account_scheme.release_bucket,
        component_name, version,
    ) as path_to_release:
        logger.debug('Unpacked release: {}'.format(path_to_release))
        path_to_release = os.path.join(
            path_to_release, '{}-{}'.format(component_name, version)
        )
        if manifest.terraform_state_in_release_account:
            terraform_session = release_account_session
        else:
            terraform_session = deploy_account_session

        initialise_terraform(
            os.path.join(path_to_release, INFRASTRUCTURE_DEFINITIONS_PATH),
            terraform_session, environment, component_name,
            manifest.tfstate_filename
        )

        if manifest.secrets_in_release_account:
            secrets_session = release_account_session
        else:
            secrets_session = deploy_account_session

        secrets = {
            'secrets': get_secrets(
                environment, manifest.team,
                component_name, secrets_session
            )
        }

        deploy = Deploy(
            environment, path_to_release, secrets,
            account_scheme, deploy_account_session
        )
        deploy.run(args['--plan-only'])


def run_destroy(
    root_session, release_account_session, account_scheme, manifest, args
):
    environment = args['<environment>']
    component_name = get_component_name(args['--component'])
    account_id = account_scheme.account_for_environment(environment).id

    logger.debug('Assuming role in {}'.format(account_id))
    destroy_account_session = assume_role(
        root_session, account_id, account_scheme.default_region,
    )

    if manifest.terraform_state_in_release_account:
        terraform_session = release_account_session
    else:
        terraform_session = destroy_account_session

    initialise_terraform(
        TERRAFORM_DESTROY_DEFINITION, terraform_session,
        environment, component_name, manifest.tfstate_filename
    )

    destroy = Destroy(destroy_account_session)

    plan_only = args['--plan-only']

    logger.info(
        'Planning destruction of {} in {}'.format(component_name, environment)
    )

    destroy.run(plan_only)

    if not plan_only:
        logger.info('Destroying {} in {}'.format(component_name, environment))
        remove_state(
            destroy_account_session, environment, component_name,
            manifest.tfstate_filename
        )


def conditionally_set_debug(verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Debug logging on')
