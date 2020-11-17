import json
from base64 import b64decode
from os import path
from os.path import expanduser
from os.path import isfile
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
        users_docker_config = expanduser("~") + "/.docker/config.json"
        logger.info(
            'Looking for a docker config at \'{}\''.format(
                users_docker_config
            )
        )
        if isfile(users_docker_config):
            logger.info('docker config found, attempting docker login')
            self._docker_login_dockerhub()

        check_call([
            'docker', 'build',
            '-t', self._image_name, '.'
        ])

        self._on_docker_build()

        if self._release.version:
            if self._account_scheme.classic_metadata_handling:
                self._ensure_ecr_repo_exists()
                self._ensure_ecr_policy_set()
            self._docker_login_ecr()
            self._docker_push(self._image_name)
            self._docker_tag_latest()
            self._docker_push(self._latest_image_name)

        return {'image_id': self._image_name}

    def _on_docker_build(self):
        if path.exists(self.ON_BUILD_HOOK):
            try:
                check_call([
                    path.abspath(self.ON_BUILD_HOOK), self._image_name
                ])
            except CalledProcessError as e:
                raise OnDockerBuildError(str(e))

    @property
    def _boto_ecr_client(self):
        if not hasattr(self, '_ecr_client'):
            logger.debug('AWS region on client: {}'.format(
                self._release.boto_session.region_name
            ))
            self._ecr_client = self._release.boto_session.client('ecr')
        return self._ecr_client

    @property
    def _image_name(self):
        return '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._account_scheme.release_account.id,
            self._account_scheme.release_account.region,
            self._release.component_name,
            self._release.version or 'dev'
        )

    @property
    def _latest_image_name(self):
        return '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._account_scheme.release_account.id,
            self._account_scheme.release_account.region,
            self._release.component_name,
            'latest'
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

    def _ensure_ecr_lifecycle_policy_set(self):
        lifecycle_policy = json.dumps({
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep 500 tagged images (we tag all images), expire all others", # noqa
                    "selection": {
                        "tagStatus": "tagged",
                        "tagPrefixList": ["1", "2", "3", "4", "5", "6", "7", "8", "9"], # noqa
                        "countType": "imageCountMoreThan",
                        "countNumber": 500
                    },
                    "action": {
                        "type": "expire"
                    }
                }
            ]
        })

        self._boto_ecr_client.put_lifecycle_policy(
            registryId=self._account_scheme.release_account.id,
            repositoryName=self._release.component_name,
            lifecyclePolicyText=lifecycle_policy
        )

    def _docker_login_dockerhub(self):
        logger.info('running docker login')
        check_call(['docker', 'login'])

    def _docker_login_ecr(self):
        response = self._boto_ecr_client.get_authorization_token()

        username, password = b64decode(
            response['authorizationData'][0]['authorizationToken']
        ).decode('utf-8').split(':')

        proxy_endpoint = response['authorizationData'][0]['proxyEndpoint']

        check_call(
            ['docker', 'login', '-u', username, '-p', password, proxy_endpoint]
        )

    def _docker_push(self, image_name):
        check_call(['docker', 'push', image_name])

    def _docker_tag_latest(self):
        check_call([
            'docker', 'tag', self._image_name, self._latest_image_name
        ])
