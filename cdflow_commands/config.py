import json
from collections import namedtuple
from re import sub, match, DOTALL

from boto3.session import Session


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
    path_template = 'infra/platform-config/{}/{}/{}.json'

    with open(path_template.format(account_prefix, 'dev', aws_region)) as f:
        dev_account_id = json.loads(f.read())['platform_config']['account_id']

    with open(path_template.format(account_prefix, 'prod', aws_region)) as f:
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
