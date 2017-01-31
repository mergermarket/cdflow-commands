'''
CDFlow Commands

Commands for managing the software lifecycle.

Usage:
    cdflow-commands release [<version>] [options]

Options:
    -c <component_name>, --component <component_name>

'''
import json
from collections import namedtuple

from boto3.session import Session
from docopt import docopt

from cdflow_commands.release import Release, ReleaseConfig


Metadata = namedtuple(
    'Metadata', ['team', 'type', 'aws_region', 'account_prefix']
)


GlobalConfig = namedtuple(
    'GlobalConfig', ['dev_account_id', 'prod_account_id']
)


def load_service_metadata():
    with open('service.json') as f:
        metadata = json.loads(f.read())
        return Metadata(
            metadata['TEAM'],
            metadata['TYPE'],
            metadata['REGION'],
            metadata['ACCOUNT_PREFIX']
        )


def assume_role(root_session, acccount_id, session_name):
    sts = root_session.client('sts')
    response = sts.assume_role(
        RoleArn='arn:aws:iam::{}:role/admin'.format(acccount_id),
        RoleSessionName=session_name,
    )
    return Session(
        response['Credentials']['AccessKeyId'],
        response['Credentials']['SecretAccessKey'],
        response['Credentials']['SessionToken'],
        root_session.region_name,
    )


def load_global_config(account_prefix, aws_region):
    path_template = 'infra/platform-config/{}/{}/{}.json'

    with open(path_template.format(account_prefix, 'dev', aws_region)) as f:
        dev_account_id = json.loads(f.read())['platform_config']['account_id']

    with open(path_template.format(account_prefix, 'prod', aws_region)) as f:
        prod_account_id = json.loads(f.read())['platform_config']['account_id']

    return GlobalConfig(dev_account_id, prod_account_id)


def run(argv):
    args = docopt(__doc__, argv=argv)

    if args['release']:
        global_config = load_global_config()
        boto_session = assume_role()
        ecr_client = boto_session.client('ecr')
        release_config = ReleaseConfig(
            global_config.dev_account_id,
            global_config.prod_account_id,
            global_config.aws_region
        )
        release = Release(
            release_config, ecr_client, args['--component'], args['<version>']
        )
        release.create()
