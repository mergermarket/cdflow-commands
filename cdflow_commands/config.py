import json
from collections import namedtuple
import re
from subprocess import CalledProcessError, check_output

import yaml
from boto3.session import Session

from cdflow_commands.account import AccountScheme
from cdflow_commands.exceptions import (
    UserFacingError, UserFacingFixedMessageError
)
from cdflow_commands.logger import logger


ILLEGAL_CHARACTERS = '[^\w+=,.@-]+'


class JobNameTooShortError(UserFacingError):
    pass


class InvalidEmailError(UserFacingError):
    pass


class InvalidURLError(UserFacingError):
    pass


class NoGitRemoteError(UserFacingFixedMessageError):
    _message = 'No git remote configured - cannot infer component name'


Manifest = namedtuple('Manifest', [
        'account_scheme_url',
        'team',
        'type',
        'terraform_state_in_release_account',
    ]
)


def load_manifest():
    with open('cdflow.yml') as f:
        manifest_data = yaml.load(f.read())
        return Manifest(
            manifest_data['account-scheme-url'],
            manifest_data['team'],
            manifest_data['type'],
            manifest_data.get('terraform-state-in-release-account', False),
        )


def assume_role(root_session, acccount_id, region=None):
    sts = root_session.client('sts')
    session_name = get_role_session_name(sts)
    logger.debug(
        "Assuming role arn:aws:iam::{}:role/admin with session {}".format(
            acccount_id, session_name
        )
    )
    response = sts.assume_role(
        RoleArn='arn:aws:iam::{}:role/admin'.format(acccount_id),
        RoleSessionName=session_name,
    )
    return Session(
        response['Credentials']['AccessKeyId'],
        response['Credentials']['SecretAccessKey'],
        response['Credentials']['SessionToken'],
        region if region else root_session.region_name,
    )


def env_with_aws_credetials(env, boto_session):
    result = env.copy()
    credentials = boto_session.get_credentials()
    result.update({
        'AWS_ACCESS_KEY_ID': credentials.access_key,
        'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
        'AWS_SESSION_TOKEN': credentials.token,
        'AWS_DEFAULT_REGION': boto_session.region_name,
    })
    return result


def get_role_session_name(sts_client):
    caller_response = sts_client.get_caller_identity()
    user_id = caller_response.get('UserId')
    return re.sub(ILLEGAL_CHARACTERS, '-', user_id)


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


def parse_s3_url(s3_url):
    if not s3_url.startswith('s3://'):
        raise InvalidURLError('URL must start with s3:// - {}'.format(s3_url))
    bucket_and_key = s3_url[5:].split('/', 1)
    if len(bucket_and_key) != 2:
        raise InvalidURLError(
            'URL must contain a bucket and a key - {}'.format(s3_url)
        )
    return bucket_and_key


def fetch_account_scheme(s3_resource, bucket, key):
    s3_object = s3_resource.Object(bucket, key)
    f = s3_object.get()['Body']
    return json.loads(f.read())


def build_account_scheme(s3_resource, s3_url):
    bucket, key = parse_s3_url(s3_url)
    return AccountScheme.create(fetch_account_scheme(s3_resource, bucket, key))
