import json
import os
from base64 import b64decode
from collections import namedtuple
from functools import lru_cache
from hashlib import sha1
from os import path
from subprocess import CalledProcessError, check_call
from tempfile import NamedTemporaryFile
from time import sleep, time

from botocore.exceptions import ClientError

from cdflow_commands.config import (
    assume_role, get_platform_config_path, get_role_session_name
)
from cdflow_commands.exceptions import (
    UserFacingError, UserFacingFixedMessageError
)
from cdflow_commands.logger import logger
from cdflow_commands.plugins import Plugin
from cdflow_commands.plugins.base import Destroy as BaseDestroy
from cdflow_commands.secrets import get_secrets
from cdflow_commands.terragrunt import (
    S3BucketFactory, write_terragrunt_config,
    LockTableFactory, initialise_terraform_backend
)


def build_ecs_plugin(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    release_factory = build_release_factory(
        component_name, version, metadata, global_config, root_session
    )

    deploy_factory = build_deploy_factory(
        environment_name, component_name, version,
        metadata, global_config, root_session
    )

    destroy_factory = build_destroy_factory(
        environment_name, component_name, metadata, global_config, root_session
    )

    deploy_monitor_factory = build_deploy_monitor_factory(
        metadata, global_config, environment_name, component_name, version,
        root_session
    )

    return ECSPlugin(
        release_factory,
        deploy_factory,
        destroy_factory,
        deploy_monitor_factory
    )


def build_release_factory(
    component_name, version, metadata, global_config, root_session
):
    def _release_factory():
        boto_session = assume_role(
            root_session,
            global_config.dev_account_id,
            get_role_session_name(os.environ)
        )
        ecr_client = boto_session.client('ecr')
        release_config = ReleaseConfig(
            global_config.dev_account_id,
            global_config.prod_account_id,
            metadata.aws_region
        )

        return Release(
            release_config, ecr_client, component_name, version
        )
    return _release_factory


def build_deploy_factory(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    def _deploy_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

        platform_config_file = get_platform_config_path(
            metadata.account_prefix, metadata.aws_region, is_prod
        )
        boto_session = assume_role(
            root_session,
            account_id,
            get_role_session_name(os.environ)
        )
        s3_bucket_factory = S3BucketFactory(boto_session, account_id)
        s3_bucket = s3_bucket_factory.get_bucket_name()

        lock_table_factory = LockTableFactory(boto_session)
        lock_table_name = lock_table_factory.get_table_name()

        initialise_terraform_backend(
            'infra', metadata.aws_region, s3_bucket, lock_table_name,
            environment_name, component_name
        )

        write_terragrunt_config(
            metadata.aws_region, s3_bucket, environment_name, component_name
        )

        deploy_config = DeployConfig(
            team=metadata.team,
            dev_account_id=global_config.dev_account_id,
            platform_config_file=platform_config_file,
        )
        return Deploy(
            boto_session, component_name, environment_name, version,
            metadata.ecs_cluster, deploy_config
        )
    return _deploy_factory


def build_destroy_factory(
    environment_name, component_name, metadata, global_config, root_session
):
    def _destroy_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

        boto_session = assume_role(
            root_session,
            account_id,
            get_role_session_name(os.environ)
        )
        s3_bucket_factory = S3BucketFactory(boto_session, account_id)
        s3_bucket = s3_bucket_factory.get_bucket_name()

        lock_table_factory = LockTableFactory(boto_session)
        lock_table_name = lock_table_factory.get_table_name()

        initialise_terraform_backend(
            'tf-destroy', metadata.aws_region, s3_bucket, lock_table_name,
            environment_name, component_name
        )

        write_terragrunt_config(
            metadata.aws_region, s3_bucket, environment_name, component_name
        )
        return Destroy(
            boto_session, component_name, environment_name, s3_bucket
        )
    return _destroy_factory


def build_deploy_monitor_factory(
    metadata, global_config, environment_name,
    component_name, version, root_session
):
    def _deploy_monitor_factory():
        is_prod = environment_name == 'live'
        if is_prod:
            account_id = global_config.prod_account_id
        else:
            account_id = global_config.dev_account_id

        boto_session = assume_role(
            root_session,
            account_id,
            get_role_session_name(os.environ)
        )
        events = ECSEventIterator(
            metadata.ecs_cluster, environment_name,
            component_name, version, boto_session
        )
        return ECSMonitor(events)
    return _deploy_monitor_factory


class Destroy(BaseDestroy):
    pass


ReleaseConfig = namedtuple('ReleaseConfig', [
    'dev_account_id',
    'prod_account_id',
    'aws_region',
])


class OnDockerBuildError(UserFacingError):
    pass


class Release(object):

    ON_BUILD_HOOK = './on-docker-build'

    def __init__(self, config, boto_ecr_client, component_name, version=None):
        self._dev_account_id = config.dev_account_id
        self._prod_account_id = config.prod_account_id
        self._aws_region = config.aws_region
        self._boto_ecr_client = boto_ecr_client
        self._component_name = component_name
        self._version = version

    def create(self):
        check_call(['docker', 'build', '-t', self._image_name, '.'])

        self._on_docker_build()

        if self._version:
            self._ensure_ecr_repo_exists()
            self._ensure_ecr_policy_set()
            self._docker_login()
            self._docker_push()

    def _on_docker_build(self):
        if path.exists(self.ON_BUILD_HOOK):
            try:
                check_call([self.ON_BUILD_HOOK, self._image_name])
            except CalledProcessError as e:
                raise OnDockerBuildError(str(e))

    @property
    def _image_name(self):
        return '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._dev_account_id,
            self._aws_region,
            self._component_name,
            self._version or 'dev'
        )

    def _ensure_ecr_repo_exists(self):
        try:
            self._boto_ecr_client.describe_repositories(
                repositoryNames=[self._component_name]
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'RepositoryNotFoundException':
                raise
            self._boto_ecr_client.create_repository(
                repositoryName=self._component_name
            )

    def _ensure_ecr_policy_set(self):
        self._boto_ecr_client.set_repository_policy(
            repositoryName=self._component_name,
            policyText=json.dumps({
                'Version': '2008-10-17',
                'Statement': [{
                    'Sid': 'allow production',
                    'Effect': 'Allow',
                    'Principal': {'AWS': 'arn:aws:iam::{}:root'.format(
                        self._prod_account_id
                    )},
                    'Action': [
                        'ecr:GetDownloadUrlForLayer',
                        'ecr:BatchGetImage',
                        'ecr:BatchCheckLayerAvailability'
                    ]
                }]
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


DeployConfig = namedtuple('DeployConfig', [
    'team',
    'dev_account_id',
    'platform_config_file',
])


class Deploy(object):

    def __init__(
        self, boto_session, component_name, environment_name,
        version, ecs_cluster, config
    ):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._version = version
        self._ecs_cluster = ecs_cluster
        self._team = config.team
        self._dev_account_id = config.dev_account_id
        self._platform_config_file = config.platform_config_file

    @property
    def _image_name(self):
        return '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._dev_account_id,
            self._aws_region,
            self._component_name,
            self._version
        )

    def _terraform_parameters(self, secrets_file):
        parameters = [
            '-var', 'component={}'.format(self._component_name),
            '-var', 'env={}'.format(self._environment_name),
            '-var', 'aws_region={}'.format(self._aws_region),
            '-var', 'team={}'.format(self._team),
            '-var', 'image={}'.format(self._image_name),
            '-var', 'version={}'.format(self._version),
            '-var', 'ecs_cluster={}'.format(self._ecs_cluster),
            '-var-file', self._platform_config_file,
            '-var-file', secrets_file
        ]
        config_file = 'config/{}.json'.format(self._environment_name)
        if path.exists(config_file):
            parameters += ['-var-file', config_file]
        return parameters + ['infra']

    def run(self):
        check_call(['terraform', 'get', 'infra'])

        credentials = self._boto_session.get_credentials()
        env = os.environ.copy()
        env.update({
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token
        })

        with NamedTemporaryFile() as f:
            secrets = get_secrets(
                self._environment_name,
                self._team,
                self._component_name,
                self._boto_session
            )
            f.write(json.dumps({'secrets': secrets}).encode('utf-8'))
            f.flush()
            parameters = self._terraform_parameters(f.name)
            check_call(
                ['terraform', 'plan'] + parameters,
                env=env
            )
            check_call(
                ['terraform', 'apply'] + parameters,
                env=env
            )


class ECSPlugin(Plugin):
    def __init__(
        self, release_factory, deploy_factory,
        destroy_factory, deploy_monitor_factory
    ):
        self.release_factory = release_factory
        self.deploy_factory = deploy_factory
        self.destroy_factory = destroy_factory
        self.deploy_monitor_factory = deploy_monitor_factory

    def release(self):
        release = self.release_factory()
        release.create()

    def deploy(self):
        deploy = self.deploy_factory()
        deploy.run()
        monitor = self.deploy_monitor_factory()
        monitor.wait()

    def destroy(self):
        destroy = self.destroy_factory()
        destroy.run()


def build_service_name(environment, component):
    service_name = '{}-{}'.format(environment, component)
    if len(service_name) > 32:
        service_name_hash = sha1(service_name.encode('utf-8')).hexdigest()
        service_name = '{}tf{}'.format(
            service_name[:24], service_name_hash[:4]
        )
    return service_name


class ECSMonitor:

    _TIMEOUT = 600
    _INTERVAL = 15

    def __init__(self, ecs_event_iterator):
        self._ecs_event_iterator = ecs_event_iterator
        self._previous_running_count = 0

    def wait(self):
        start = time()

        for event in self._ecs_event_iterator:
            if time() - start > self._TIMEOUT:
                raise TimeoutError(
                    'Deployment timed out - didn\'t complete '
                    'within {} seconds'.format(self._TIMEOUT)
                )

            self._show_deployment_progress(event)
            self._check_for_failed_tasks(event)

            if event.done:
                logger.info('Deployment complete')
                return True

            sleep(self._INTERVAL)

    def _show_deployment_progress(self, event):
        for message in event.messages:
            logger.info('ECS service event - {}'.format(message))

        logger.info(
            'ECS service tasks - '
            'desired: {} pending: {} running: {} previous: {}'.format(
                event.desired, event.pending,
                event.running, event.previous_running
            )
        )

    def _check_for_failed_tasks(self, event):
        if event.running < self._previous_running_count:
            raise FailedTasksError

        self._previous_running_count = event.running


class ECSEventIterator:

    _INTERVAL = 15
    _NEW_SERVICE_GRACE_PERIOD = 60

    def __init__(self, cluster, environment, component, version, boto_session):
        self._cluster = cluster
        self._environment = environment
        self._component = component
        self._version = version
        self._boto_session = boto_session
        self._done = False
        self._seen_ecs_service_events = set()
        self._new_service_deployment = None
        self._new_service_grace_period = self._NEW_SERVICE_GRACE_PERIOD

    def __iter__(self):
        return self

    def __next__(self):
        if self._done:
            raise StopIteration

        ecs_service_data = self._ecs.describe_services(
            cluster=self._cluster,
            services=[self.service_name]
        )

        deployments = self._get_deployments(ecs_service_data)
        primary_deployment = self._get_primary_deployment(deployments)
        running = primary_deployment['runningCount']
        pending = primary_deployment['pendingCount']
        desired = primary_deployment['desiredCount']
        previous_running = self._get_previous_running_count(deployments)
        messages = self._get_task_event_messages(
            ecs_service_data, primary_deployment
        )

        self._assert_correct_image_being_deployed(
            primary_deployment['taskDefinition']
        )

        if self._new_service_deployment is None:
            self._new_service_deployment = previous_running == 0

        if self._deploy_in_progress(running, desired, previous_running):
            return InProgressEvent(
                running, pending, desired, previous_running, messages
            )

        self._done = True
        return DoneEvent(
            running, pending, desired, previous_running, messages
        )

    def _deploy_in_progress(self, running, desired, previous_running):
        if running != desired or previous_running:
            return True
        elif (running == desired and self._new_service_deployment and
                self._new_service_grace_period > 0):
            self._new_service_grace_period -= self._INTERVAL
            return True

        return False

    @property
    def service_name(self):
        return build_service_name(self._environment, self._component)

    @property
    @lru_cache(maxsize=1)
    def _ecs(self):
        return self._boto_session.client('ecs')

    @lru_cache(maxsize=10)
    def _get_release_image(self, task_definition_arn):
        task_def = self._ecs.describe_task_definition(
            taskDefinition=task_definition_arn
        )['taskDefinition']['containerDefinitions'][0]

        return task_def['image'].split('/', 1)[1]

    def _assert_correct_image_being_deployed(self, task_definition):
        release_image = self._get_release_image(task_definition)
        requested_image = '{}:{}'.format(self._component, self._version)

        if release_image != requested_image:
            raise ImageDoesNotMatchError(
                'Requested image {} does not match image '
                'found in deployment {}'.format(
                    requested_image, release_image
                )
            )

    def _get_new_ecs_service_events(self, ecs_service_data, since):
        filtered_ecs_events = [
            event
            for event in ecs_service_data['services'][0].get('events', [])
            if event['id'] not in self._seen_ecs_service_events and
            event['createdAt'] > since
        ]

        for event in filtered_ecs_events:
            self._seen_ecs_service_events.add(event['id'])

        return list(reversed(filtered_ecs_events))

    def _get_task_event_messages(self, ecs_service_data, primary_deployment):
        return [
            event['message']
            for event in self._get_new_ecs_service_events(
                ecs_service_data, primary_deployment['createdAt']
            )
        ]

    def _get_deployments(self, ecs_service_data):
        return [
            deployment
            for deployment in ecs_service_data['services'][0]['deployments']
        ]

    def _get_primary_deployment(self, deployments):
        return [
            deployment
            for deployment in deployments
            if deployment['status'] == 'PRIMARY'
        ][0]

    def _get_previous_running_count(self, deployments):
        return sum(
            deployment['runningCount']
            for deployment in deployments
            if deployment['status'] != 'PRIMARY'
        )


class Event:

    def __init__(self, running, pending, desired, previous_running, messages):
        self.running = running
        self.pending = pending
        self.desired = desired
        self.previous_running = previous_running
        self.messages = messages


class DoneEvent(Event):

    @property
    def done(self):
        return True


class InProgressEvent(Event):

    @property
    def done(self):
        return False


class TimeoutError(UserFacingError):
    pass


class ImageDoesNotMatchError(UserFacingError):
    pass


class FailedTasksError(UserFacingFixedMessageError):
    _message = (
        'Deployment failed - number of running tasks has decreased'
    )
