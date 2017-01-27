from subprocess import check_call

from collections import namedtuple

from base64 import b64decode


ReleaseConfig = namedtuple('ReleaseConfig', [
    'dev_account_id',
    'aws_region',
])


class Release(object):

    def __init__(self, config, boto_ecr_client, component_name, version=None):
        self._dev_account_id = config.dev_account_id
        self._aws_region = config.aws_region
        self._boto_ecr_client = boto_ecr_client
        self._component_name = component_name
        self._version = version

    def create(self):
        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._dev_account_id,
            self._aws_region,
            self._component_name,
            self._version or 'dev'
        )

        check_call(['docker', 'build', '-t', image_name])

        if self._version:
            self._ensure_ecr_repo_exists()
            self._docker_login()
            # docker push

    def _ensure_ecr_repo_exists(self):
        self._boto_ecr_client.describe_repositories(
            repositoryNames=[self._component_name]
        )

    def _docker_login(self):
        response = self._boto_ecr_client.get_authorization_details()

        username, password = b64decode(
            response['authorizationData'][0]['authorizationToken']
        ).split(':')

        proxy_endpoint = response['authorizationData'][0]['proxyEndpoint']

        check_call(
            ['docker', 'login', '-u', username, '-p', password, proxy_endpoint]
        )
