import json
from collections import namedtuple
from re import sub, match, DOTALL
from subprocess import check_output

from boto3.session import Session


PLATFORM_CONFIG_PATH_TEMPLATE = 'infra/platform-config/{}/{}/{}.json'


class UserError(Exception):
    _message = 'User error'

    def __repr__(self):
        return self._message


class JobNameTooShortError(UserError):
    _message = 'JOB_NAME must be at least 6 characters'


class InvalidEmailError(UserError):
    _message = 'EMAIL does not contain a valid email address'


class NoJobNameOrEmailError(UserError):
    _message = 'JOB_NAME or EMAIL must be set'


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


def load_global_config(account_prefix, aws_region):
    with open(get_platform_config_path(
        account_prefix, aws_region, is_prod=False
    )) as f:
        dev_account_id = json.loads(f.read())['platform_config']['account_id']

    with open(get_platform_config_path(
        account_prefix, aws_region, is_prod=True
    )) as f:
        prod_account_id = json.loads(f.read())['platform_config']['account_id']

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
        raise JobNameTooShortError()


def _validate_email(email):
    if not match(r'.+@([\w-]+\.)+\w+$', email, DOTALL):
        raise InvalidEmailError()


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
    remote = check_output(['git', 'config', 'remote.origin.url'])
    name = remote.strip().split('/')[-1]
    if name.endswith('.git'):
        return name[:-4]
    return name


def get_platform_config_path(account_prefix, aws_region, is_prod):
    account_postfix = 'prod' if is_prod else 'dev'
    return 'infra/platform-config/{}/{}/{}.json'.format(
        account_prefix, account_postfix, aws_region
    )
