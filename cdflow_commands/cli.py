"""CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow release [<version>] [options]
    cdflow deploy <environment>  [(--var <key=value>)...] [<version>] [options]
    cdflow destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>
    -v, --verbose

"""
import logging
import sys
from shutil import rmtree

from boto3.session import Session
from docopt import docopt

from cdflow_commands.config import (
    get_component_name, load_global_config, load_service_metadata
)
from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.plugins.ecs import build_ecs_plugin
from cdflow_commands.plugins.infrastructure import build_infrastructure_plugin


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

    metadata = load_service_metadata()
    global_config = load_global_config(
        metadata.account_prefix, metadata.aws_region
    )
    root_session = Session(region_name=metadata.aws_region)

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

    if args['release']:
        plugin.release()
    elif args['deploy']:
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
        )
    elif project_type == 'infrastructure':
        plugin = build_infrastructure_plugin(
            kwargs['environment_name'],
            kwargs['component_name'],
            kwargs['additional_variables'],
            kwargs['metadata'],
            kwargs['global_config'],
            kwargs['root_session'],
        )
    return plugin


def conditionally_set_debug(verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('Debug logging on')
