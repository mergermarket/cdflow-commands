from hashlib import sha1
from functools import lru_cache
from time import sleep, time

from cdflow_commands.logger import logger
from cdflow_commands.exceptions import (
    UserFacingError, UserFacingFixedMessageError
)


TIMEOUT = 600
INTERVAL = 15
NEW_SERVICE_DEPLOYMENT_GRACE_PERIOD_LIMIT = 4


def build_service_name(environment, component):
    service_name = '{}-{}'.format(environment, component)
    if len(service_name) > 32:
        service_name_hash = sha1(service_name.encode('utf-8')).hexdigest()
        service_name = '{}tf{}'.format(
            service_name[:24], service_name_hash[:4]
        )
    return service_name


class ECSMonitor():

    def __init__(self, ecs_event_iterator):
        self._ecs_event_iterator = ecs_event_iterator
        self._previous_running_count = 0

    def wait(self):
        start = time()

        for event in self._ecs_event_iterator:
            if time() - start > TIMEOUT:
                raise TimeoutError

            self._show_deployment_progress(event)
            self._check_for_failed_tasks(event)

            if event.done:
                logger.info('Deployment complete')
                return True

            sleep(INTERVAL)

    def _show_deployment_progress(self, event):
        for message in event.messages:
            logger.info("ECS service event - {}".format(message))

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


class ECSEventIterator():

    def __init__(self, cluster, environment, component, version, boto_session):
        self._cluster = cluster
        self._environment = environment
        self._component = component
        self._version = version
        self._boto_session = boto_session
        self._done = False
        self._seen_ecs_service_events = set()
        self._new_service_deployment = None
        self._new_service_deployment_grace_period_count = 0

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

        self._assert_correct_image_being_deployed(
            primary_deployment['taskDefinition']
        )

        # establish whether we're deploying a brand new service, or updating
        # existing one
        if self._new_service_deployment is None:
            self._new_service_deployment = \
                self._get_previous_running_count(deployments) == 0

        running = primary_deployment['runningCount']
        pending = primary_deployment['pendingCount']
        desired = primary_deployment['desiredCount']
        previous_running = self._get_previous_running_count(deployments)

        messages = self._get_task_event_messages(
            ecs_service_data,
            primary_deployment
        )

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
                self._new_service_deployment_grace_period_count <
                NEW_SERVICE_DEPLOYMENT_GRACE_PERIOD_LIMIT):
            self._new_service_deployment_grace_period_count += 1
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


class Event():

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


class TimeoutError(UserFacingFixedMessageError):
    _message = (
        'Deployment timed out - didn\'t complete within {} seconds'.format(
            TIMEOUT
        )
    )


class FailedTasksError(UserFacingFixedMessageError):
    _message = (
        'Deployment failed - number of running tasks has decreased'
    )


class ImageDoesNotMatchError(UserFacingError):
    pass
