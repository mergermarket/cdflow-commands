import unittest
import datetime
from itertools import islice

from mock import MagicMock, Mock
from hypothesis import given, settings
from hypothesis.strategies import text, fixed_dictionaries

from boto3 import Session

from cdflow_commands.ecs_monitor import (
    ECSEventIterator, build_service_name, ImageDoesNotMatchError
)


class TestECSEventIterator(unittest.TestCase):

    @given(fixed_dictionaries({
        'cluster': text(),
        'environment': text(),
        'component': text(),
        'version': text()
    }))
    @settings(max_examples=5)
    def test_monitor_exited_when_the_deployment_is_stable(
        self, deployment_data
    ):
        environment = deployment_data['environment']
        component = deployment_data['component']
        version = deployment_data['version']
        cluster = deployment_data['cluster']
        boto_session = MagicMock(spec=Session)
        mock_ecs_client = Mock()
        task_definition_arn = ('arn:aws:ecs:eu-west-3:111111111111:'
                               'task-definition/{}:1'.format(component)),
        mock_ecs_client.describe_services.return_value = {
            'failures': [],
            'services': [
                {
                    'clusterArn': 'arn:aws:ecs:eu-1:7:cluster/non-production',
                    'createdAt': datetime.datetime(2017, 1, 6, 10, 58, 9),
                    'deployments': [
                        {
                            'createdAt': datetime.datetime(2017, 1, 6, 13, 57),
                            'desiredCount': 2,
                            'id': 'ecs-svc/9223370553143707624',
                            'pendingCount': 0,
                            'runningCount': 2,
                            'status': 'PRIMARY',
                            'taskDefinition': task_definition_arn,
                            'updatedAt': datetime.datetime(2017, 1, 6, 13, 57)
                        }
                    ],
                    'desiredCount': 2,
                    'loadBalancers': [
                        {
                            'containerName': 'app',
                            'containerPort': 8000,
                            'targetGroupArn': 'd035fe071cf0069f'
                        }
                    ],
                    'pendingCount': 0,
                    'roleArn': '20170106105800480922659dsq',
                    'runningCount': 2,
                    'serviceArn': 'aslive-testtf2469',
                    'serviceName': 'aslive-testtf2469',
                    'status': 'ACTIVE',
                    'taskDefinition': task_definition_arn
                }
            ]
        }
        mock_ecs_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'cpu': 64,
                    'dockerLabels': {
                        'component': component,
                        'env': 'ci',
                        'team': 'platform',
                        'version': '123'
                    },
                    'environment': [
                        {
                            'name': 'VERSION',
                            'value': version
                        },
                        {
                            'name': 'COMPONENT',
                            'value': component
                        },
                    ],
                    'essential': True,
                    'image': ('111111111111.dkr.ecr.eu-west-1.amazonaws.com/'
                              '{}:{}'.format(component, version)),
                    'volumesFrom': []
                }],
                'status': 'ACTIVE',
                'taskDefinitionArn': task_definition_arn,
                'taskRoleArn': 'arn:aws:iam::7:role/role',
                'volumes': []
            }
        }
        boto_session.client.return_value = mock_ecs_client
        events = ECSEventIterator(
            cluster, environment, component, version, boto_session
        )

        event_list = [e for e in events]

        assert len(event_list) == 1
        assert event_list[0].done

    def test_monitor_exited_deploy_finished_after_3_iterations(self):
        environment = 'dummy-environment'
        component = 'dummy-component'
        version = 'dummy-version'
        cluster = 'dummy-cluster'
        boto_session = MagicMock(spec=Session)
        mock_ecs_client = Mock()
        task_definition_arn = ('arn:aws:ecs:eu-west-3:111111111111:'
                               'task-definition/{}:1'.format(component)),

        def describe_services_generator(final_running_count):
            for running_count in range(final_running_count + 1):
                yield {
                    'services': [
                        {
                            'clusterArn': 'arn:aws:ecs:eu-1:7:cstr/non-prod',
                            'deployments': [
                                {
                                    'desiredCount': 2,
                                    'id': 'ecs-svc/9223370553143707624',
                                    'runningCount': running_count,
                                    'status': 'PRIMARY',
                                    'taskDefinition': task_definition_arn,
                                },
                                {
                                    'desiredCount': 2,
                                    'id': 'ecs-svc/9223370553143707624',
                                    'runningCount': 2,
                                    'status': 'ACTIVE',
                                    'taskDefinition': task_definition_arn,
                                }
                            ],
                            'loadBalancers': [
                                {
                                    'containerName': 'app',
                                    'containerPort': 8000,
                                    'targetGroupArn': 'd035fe071cf0069f'
                                }
                            ],
                            'status': 'ACTIVE',
                            'taskDefinition': task_definition_arn
                        }
                    ]
                }

        mock_ecs_client.describe_services.side_effect = \
            describe_services_generator(2)

        mock_ecs_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'cpu': 64,
                    'dockerLabels': {
                        'component': component,
                        'env': 'ci',
                        'team': 'platform',
                        'version': '123'
                    },
                    'environment': [
                        {
                            'name': 'VERSION',
                            'value': version
                        },
                        {
                            'name': 'COMPONENT',
                            'value': component
                        },
                    ],
                    'essential': True,
                    'image': ('111111111111.dkr.ecr.eu-west-1.amazonaws.com/'
                              '{}:{}'.format(component, version)),
                    'volumesFrom': []
                }],
                'status': 'ACTIVE',
                'taskDefinitionArn': task_definition_arn,
                'taskRoleArn': 'arn:aws:iam::7:role/role',
                'volumes': []
            }
        }
        boto_session.client.return_value = mock_ecs_client
        events = ECSEventIterator(
            cluster, environment, component, version, boto_session
        )

        event_list = [e for e in events]

        assert len(event_list) == 3
        assert not event_list[0].done
        assert event_list[0].running == 0
        assert event_list[0].desired == 2
        assert not event_list[1].done
        assert event_list[1].running == 1
        assert event_list[1].desired == 2
        assert event_list[2].done
        assert event_list[2].running == 2
        assert event_list[2].desired == 2

    def test_deployment_does_not_complete_within_time(self):
        environment = 'dummy-environment'
        component = 'dummy-component'
        version = 'dummy-version'
        cluster = 'dummy-cluster'
        boto_session = MagicMock(spec=Session)
        mock_ecs_client = Mock()
        task_definition_arn = ('arn:aws:ecs:eu-west-3:111111111111:'
                               'task-definition/{}:1'.format(component)),

        mock_ecs_client.describe_services.return_value = {
            'services': [
                {
                    'clusterArn': 'arn:aws:ecs:eu-1:7:cstr/non-prod',
                    'deployments': [
                        {
                            'desiredCount': 2,
                            'id': 'ecs-svc/9223370553143707624',
                            'runningCount': 1,
                            'status': 'PRIMARY',
                            'taskDefinition': task_definition_arn,
                        }
                    ],
                    'status': 'ACTIVE',
                    'taskDefinition': task_definition_arn
                }
            ]
        }

        mock_ecs_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'cpu': 64,
                    'dockerLabels': {
                        'component': component,
                        'env': 'ci',
                        'team': 'platform',
                        'version': '123'
                    },
                    'image': ('111111111111.dkr.ecr.eu-west-1.amazonaws.com/'
                              '{}:{}'.format(component, version)),
                }],
                'status': 'ACTIVE',
                'taskDefinitionArn': task_definition_arn,
                'taskRoleArn': 'arn:aws:iam::7:role/role',
                'volumes': []
            }
        }
        boto_session.client.return_value = mock_ecs_client
        events = ECSEventIterator(
            cluster, environment, component, version, boto_session
        )
        statuses = [e.done for e in islice(events, 1000)]
        assert not any(statuses)

    @given(fixed_dictionaries({
        'environment': text(),
        'component': text(),
        'version': text()
    }))
    @settings(max_examples=5)
    def test_monitor_image_does_not_match(
        self, deployment_data
    ):
        environment = deployment_data['environment']
        component = deployment_data['component']
        version = deployment_data['version']
        cluster = 'ecs-cluster'
        boto_session = MagicMock(spec=Session)
        mock_ecs_client = Mock()
        task_definition_arn = ('arn:aws:ecs:eu-west-3:111111111111:'
                               'task-definition/{}:1'.format(component)),
        mock_ecs_client.describe_services.return_value = {
            'services': [
                {
                    'clusterArn': 'arn:aws:ecs:eu-1:7:cluster/non-production',
                    'deployments': [
                        {
                            'desiredCount': 2,
                            'id': 'ecs-svc/9223370553143707624',
                            'pendingCount': 0,
                            'runningCount': 2,
                            'status': 'PRIMARY',
                            'taskDefinition': task_definition_arn,
                            'updatedAt': datetime.datetime(2017, 1, 6, 13, 57)
                        }
                    ],
                    'status': 'ACTIVE',
                    'taskDefinition': task_definition_arn
                }
            ]
        }
        mock_ecs_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'dockerLabels': {
                        'component': component,
                        'env': 'ci',
                        'team': 'platform',
                        'version': '123'
                    },
                    'environment': [
                        {
                            'name': 'VERSION',
                            'value': version
                        },
                        {
                            'name': 'COMPONENT',
                            'value': component
                        },
                    ],
                    'image': 'ecr/none',
                }],
                'taskDefinitionArn': task_definition_arn,
            }
        }
        boto_session.client.return_value = mock_ecs_client
        events = ECSEventIterator(
            cluster, environment, component, version, boto_session
        )

        self.assertRaises(ImageDoesNotMatchError, lambda: [e for e in events])


class TestBuildServiceName(unittest.TestCase):

    @given(fixed_dictionaries({
        'environment': text(max_size=6),
        'component': text(max_size=25),
    }))
    def test_build_service_name_short_name(self, test_data):
        # Given
        # When
        service_name = build_service_name(
            test_data['environment'], test_data['component']
        )
        # Then
        assert service_name == "{}-{}".format(
            test_data['environment'], test_data['component']
        )

    @given(fixed_dictionaries({
        'environment': text(min_size=6),
        'component': text(min_size=26),
    }))
    def test_build_service_name_long_name(self, test_data):
        # When
        service_name = build_service_name(
            test_data['environment'], test_data['component']
        )
        # Then
        assert service_name.startswith("{}-{}".format(
            test_data['environment'], test_data['component']
        )[:24])

    @given(fixed_dictionaries({
        'environment': text(min_size=6),
        'component': text(min_size=26),
    }))
    def test_build_service_name_length_limit(self, test_data):
        # When
        service_name = build_service_name(
            test_data['environment'], test_data['component']
        )
        # Then
        assert len(service_name) <= 32

    @given(fixed_dictionaries({
        'environment': text(min_size=6),
        'component': text(min_size=26),
    }))
    def test_build_service_name_idempotent(self, test_data):
        # Given
        service_name_1 = build_service_name(
            test_data['environment'], test_data['component']
        )
        # When
        service_name_2 = build_service_name(
            test_data['environment'], test_data['component']
        )
        # Then
        assert service_name_1 == service_name_2
