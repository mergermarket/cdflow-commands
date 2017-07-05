import json
from base64 import b64decode
from os import path
from subprocess import CalledProcessError, check_call

from botocore.exceptions import ClientError

from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.logger import logger


class OnDockerBuildError(UserFacingError):
    pass


class ReleasePlugin:

    ON_BUILD_HOOK = './on-docker-build'

    def __init__(self, release, account_scheme):
        self._release = release
        self._account_scheme = account_scheme

    def create(self):
        check_call(['docker', 'build', '-t', self._image_name, '.'])

        self._on_docker_build()

        if self._release.version:
            self._ensure_ecr_repo_exists()
            self._ensure_ecr_policy_set()
            self._docker_login()
            self._docker_push()

        return {'image_id': self._image_name}

    def _on_docker_build(self):
        if path.exists(self.ON_BUILD_HOOK):
            try:
                check_call([self.ON_BUILD_HOOK, self._image_name])
            except CalledProcessError as e:
                raise OnDockerBuildError(str(e))

    @property
    def _boto_ecr_client(self):
        if not hasattr(self, '__ecr_client'):
            logger.debug('AWS region on client: {}'.format(
                self._release.boto_session.region_name
            ))
            self.__ecr_client = self._release.boto_session.client('ecr')
        return self.__ecr_client

    @property
    def _image_name(self):
        return '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._account_scheme.release_account.id,
            self._account_scheme.default_region,
            self._release.component_name,
            self._release.version or 'dev'
        )

    def _ensure_ecr_repo_exists(self):
        try:
            self._boto_ecr_client.describe_repositories(
                repositoryNames=[self._release.component_name]
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'RepositoryNotFoundException':
                raise
            self._boto_ecr_client.create_repository(
                repositoryName=self._release.component_name
            )

    def _ensure_ecr_policy_set(self):
        account_ids = [
            account_id
            for account_id
            in self._account_scheme.account_ids
            if account_id != self._account_scheme.release_account.id
        ]
        if len(account_ids) == 0:
            return
        self._boto_ecr_client.set_repository_policy(
            repositoryName=self._release.component_name,
            policyText=json.dumps({
                'Version': '2008-10-17',
                'Statement': [{
                    'Sid': 'allow {}'.format(account_id),
                    'Effect': 'Allow',
                    'Principal': {
                        'AWS': 'arn:aws:iam::{}:root'.format(account_id)
                    },
                    'Action': [
                        'ecr:GetDownloadUrlForLayer',
                        'ecr:BatchGetImage',
                        'ecr:BatchCheckLayerAvailability'
                    ]
                } for account_id in sorted(account_ids)]
            }, sort_keys=True)
        )

    def _docker_login(self):
        response = self._boto_ecr_client.get_authorization_token()

        username, password = b64decode(
            response['authorizationData'][0]['authorizationToken']
        ).decode('utf-8').split(':')

        proxy_endpoint = response['authorizationData'][0]['proxyEndpoint']

        check_call(
            ['docker', 'login', '-u', username, '-p', password, proxy_endpoint]
        )

    def _docker_push(self):
        check_call(['docker', 'push', self._image_name])
