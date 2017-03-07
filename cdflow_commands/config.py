import json
from collections import namedtuple
from re import sub, match, DOTALL
from subprocess import check_output, CalledProcessError

from boto3.session import Session


PLATFORM_CONFIG_PATH_TEMPLATE = 'infra/platform-config/{}/{}/{}.json'


class UserError(Exception):
    _message = 'User error'

    def __str__(self):
        return self._message


class JobNameTooShortError(UserError):
    _message = 'JOB_NAME must be at least 6 characters'


class InvalidEmailError(UserError):
    _message = 'EMAIL does not contain a valid email address'


class NoJobNameOrEmailError(UserError):
    _message = 'JOB_NAME or EMAIL must be set'


class NoGitRemoteError(UserError):
    _message = 'No git remote configured - cannot infer component name'


Metadata = namedtuple(
    'Metadata', ['team', 'type', 'aws_region', 'account_prefix', 'ecs_cluster']
)


GlobalConfig = namedtuple(
    'GlobalConfig', [
        'dev_account_id',
        'prod_account_id',
        'dev_ecs_cluster',
        'prod_ecs_cluster'
    ]
)


def load_service_metadata():
    with open('service.json') as f:
        metadata = json.loads(f.read())
        return Metadata(
            metadata['TEAM'],
            metadata['TYPE'],
            metadata['REGION'],
            metadata['ACCOUNT_PREFIX'],
            metadata.get('ECS_CLUSTER', 'default')
        )


def load_global_config(account_prefix, aws_region):
    ecs_cluster = 'default'
    ecs_cluster_key = 'ecs_cluster.{}.name'.format(ecs_cluster)
    with open(get_platform_config_path(
        account_prefix, aws_region, is_prod=False
    )) as f:
        config = json.loads(f.read())
        dev_account_id = config['platform_config']['account_id']
        dev_ecs_cluster = config['platform_config'][ecs_cluster_key]

    with open(get_platform_config_path(
        account_prefix, aws_region, is_prod=True
    )) as f:
        config = json.loads(f.read())
        prod_account_id = config['platform_config']['account_id']
        prod_ecs_cluster = config['platform_config'][ecs_cluster_key]

    return GlobalConfig(
        dev_account_id, prod_account_id, dev_ecs_cluster, prod_ecs_cluster
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
    return _get_component_name_from_git_remote()


def _get_component_name_from_git_remote():
    try:
        remote = check_output(['git', 'config', 'remote.origin.url'])
    except CalledProcessError:
        raise NoGitRemoteError()
    name = remote.decode('utf-8').strip().split('/')[-1]
    if name.endswith('.git'):
        return name[:-4]
    return name


def get_platform_config_path(account_prefix, aws_region, is_prod):
    account_postfix = 'prod' if is_prod else 'dev'
    return 'infra/platform-config/{}/{}/{}.json'.format(
        account_prefix, account_postfix, aws_region
    )
