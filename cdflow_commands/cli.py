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
import sys
from os import unlink
from shutil import rmtree

from boto3.session import Session

from cdflow_commands.config import (
    get_component_name, load_global_config, load_service_metadata
)
from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.logger import logger
from cdflow_commands.plugins.ecs import build_ecs_plugin
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
