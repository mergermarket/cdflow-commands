import json
from collections import namedtuple
from re import DOTALL, match, sub
from subprocess import CalledProcessError, check_output

from boto3.session import Session
from cdflow_commands.exceptions import (
    UserFacingError, UserFacingFixedMessageError
)

PLATFORM_CONFIG_PATH_TEMPLATE = 'infra/platform-config/{}/{}/{}.json'


class JobNameTooShortError(UserFacingError):
    pass


class InvalidEmailError(UserFacingError):
    pass


class NoJobNameOrEmailError(UserFacingFixedMessageError):
    _message = 'JOB_NAME or EMAIL must be set'


class NoGitRemoteError(UserFacingFixedMessageError):
    _message = 'No git remote configured - cannot infer component name'


Metadata = namedtuple(
    'Metadata', [
        'team',
        'type',
        'aws_region',
        'account_prefix',
        'ecs_cluster',
        'handler',
        'runtime'
    ]
)


GlobalConfig = namedtuple(
    'GlobalConfig', [
        'dev_account_id',
        'prod_account_id'
    ]
)


def load_service_metadata():
    with open('service.json') as f:
        metadata = json.loads(f.read())
        try:
            return Metadata(
                metadata['TEAM'],
                metadata['TYPE'],
                metadata['REGION'],
                metadata['ACCOUNT_PREFIX'],
                metadata.get('ECS_CLUSTER', 'default'),
                metadata.get('HANDLER', ''),
                metadata.get('RUNTIME', '')
            )
        except KeyError as key:
            raise UserFacingError(
                'Deployment failed - did you set {} in {}?'.format(
                    key, f.name))


def load_global_config(account_prefix, aws_region):
    with open(get_platform_config_path(
        account_prefix, aws_region, is_prod=False
    )) as f:
        config = json.loads(f.read())
        dev_account_id = config['platform_config']['account_id']

    with open(get_platform_config_path(
        account_prefix, aws_region, is_prod=True
    )) as f:
        config = json.loads(f.read())
        prod_account_id = config['platform_config']['account_id']

    return GlobalConfig(dev_account_id, prod_account_id)


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


def _validate_job_name(job_name):
    if len(job_name) < 6:
        raise JobNameTooShortError(
            'JOB_NAME must be at least 6 characters', job_name
        )


def _validate_email(email):
    if not match(r'.+@([\w-]+\.)+\w+$', email, DOTALL):
        raise InvalidEmailError(
            'EMAIL does not contain a valid email address', email
        )


def get_role_session_name(env):
    if 'JOB_NAME' in env:
        _validate_job_name(env['JOB_NAME'])
        unsafe_session_name = env['JOB_NAME']
    elif 'EMAIL' in env:
        _validate_email(env['EMAIL'])
        unsafe_session_name = env['EMAIL']
    else:
        raise NoJobNameOrEmailError()
    return sub(r'[^\w+=,.@-]+', '-', unsafe_session_name)[:64]


def get_component_name(component_name):
    if component_name:
        return component_name
    return _get_component_name_from_git_remote()


def _get_component_name_from_git_remote():
    try:
        remote = check_output(['git', 'config', 'remote.origin.url'])
    except CalledProcessError:
        raise NoGitRemoteError()
    name = remote.decode('utf-8').strip('\t\n /').split('/')[-1]
    if name.endswith('.git'):
        return name[:-4]
    return name


def get_platform_config_path(account_prefix, aws_region, is_prod):
    account_postfix = 'prod' if is_prod else 'dev'
    return 'infra/platform-config/{}/{}/{}.json'.format(
        account_prefix, account_postfix, aws_region
    )
