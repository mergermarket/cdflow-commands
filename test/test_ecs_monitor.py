import unittest
import datetime
from dateutil.tz import tzlocal
from itertools import cycle, islice

from mock import MagicMock, Mock, ANY
from hypothesis import given, settings, example
from hypothesis.strategies import text, fixed_dictionaries

from boto3 import Session

from cdflow_commands import ecs_monitor as ecs_monitor_module
from cdflow_commands.ecs_monitor import (
    ECSEventIterator, ECSMonitor, build_service_name, DoneEvent,
    InProgressEvent, ImageDoesNotMatchError, TimeoutError, FailedTasksError
)


class TestECSMonitor(unittest.TestCase):

    def test_ecs_monitor_successful_deployment(self):
        # Given
        ecs_event_iterator = [
            DoneEvent(2, 0, 2, 0, [])
        ]
        ecs_monitor = ECSMonitor(ecs_event_iterator)

        # When
        with self.assertLogs('cdflow_commands.logger', level='INFO') as logs:
            ecs_monitor.wait()

        # Then
        assert logs.output == [
            ('INFO:cdflow_commands.logger:ECS service tasks - desired: 2 '
             'pending: 0 running: 2 previous: 0'),
            'INFO:cdflow_commands.logger:Deployment complete'
        ]

    def test_ecs_monitor_eventual_successful_deployment(self):
        # Given
        ecs_event_iterator = [
            InProgressEvent(0, 1, 2, 2, []),
            InProgressEvent(1, 0, 2, 1, []),
            DoneEvent(2, 0, 2, 0, [])
        ]
        ecs_monitor_module.INTERVAL = 0
        ecs_monitor = ECSMonitor(ecs_event_iterator)

        # When
        with self.assertLogs('cdflow_commands.logger', level='INFO') as logs:
            ecs_monitor.wait()

        # Then
        assert logs.output == [
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 1 running: 0 previous: 2'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 1 previous: 1'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 2 previous: 0'),
            'INFO:cdflow_commands.logger:Deployment complete'
        ]

    def test_ecs_monitor_deployment_times_out(self):
        # Given
        ecs_event_iterator = cycle([
            InProgressEvent(0, 0, 2, 0, []),
            InProgressEvent(1, 0, 2, 0, []),
        ])
        ecs_monitor_module.INTERVAL = 0
        ecs_monitor_module.TIMEOUT = 1
        ecs_monitor = ECSMonitor(ecs_event_iterator)

        # Then
        self.assertRaises(TimeoutError, ecs_monitor.wait)

    def test_ecs_monitor_failed_tasks_error(self):
        # Given
        ecs_event_iterator = [
            InProgressEvent(0, 1, 2, 2, []),
            InProgressEvent(1, 1, 2, 2, []),
            InProgressEvent(2, 0, 2, 2, []),
            InProgressEvent(1, 0, 2, 2, [])
        ]
        ecs_monitor_module.INTERVAL = 0
        ecs_monitor = ECSMonitor(ecs_event_iterator)

        # When
        with self.assertLogs('cdflow_commands.logger', level='INFO') as logs:
            self.assertRaises(FailedTasksError, ecs_monitor.wait)

        # Then
        assert logs.output == [
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 1 running: 0 previous: 2'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 1 running: 1 previous: 2'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 2 previous: 2'),
            ('INFO:cdflow_commands.logger:ECS service tasks - '
             'desired: 2 pending: 0 running: 1 previous: 2')
        ]


class TestECSEventIterator(unittest.TestCase):

    @given(fixed_dictionaries({
        'cluster': text(),
        'environment': text(),
        'component': text(),
        'version': text()
    }))
    @example({
        'cluster': '',
        'environment': '',
        'component': 'hello/world',
        'version': '1'
    })
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
                    'events': [
                        {
                            'createdAt': datetime.datetime(
                                2017, 3, 10, 10, 27, 40, 1
                            ),
                            'id': '71e1ea54-61bd-4d5f-b6ae-ba0ba4a3c270',
                            'message': 'has reached a steady state.'
                        },
                        {
                            'createdAt': datetime.datetime(
                                2017, 3, 9, 16, 26, 49, 794
                            ),
                            'id': '851fd578-579d-4a23-8764-107f0cf1120c',
                            'message': 'registered 1 targets'
                        },
                        {
                            'createdAt': datetime.datetime(
                                2017, 3, 9, 16, 26, 37, 48000
                            ),
                            'id': '39e46d75-018e-4db4-a62d-1d76b4564132',
                            'message': 'has started 1 tasks'
                        }
                    ],
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

        # Then
        assert len(event_list) == 1
        assert event_list[0].done
        assert event_list[0].previous_running == 0
        assert event_list[0].messages == [
            'has started 1 tasks',
            'registered 1 targets',
            'has reached a steady state.'
        ]

    def test_deployment_completed_after_reaching_desired_running_count(self):
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
                pending_count = final_running_count - running_count
                yield {
                    'services': [
                        {
                            'clusterArn': 'arn:aws:ecs:eu-1:7:cstr/non-prod',
                            'deployments': [
                                {
                                    'desiredCount': final_running_count,
                                    'createdAt': datetime.datetime(
                                        2017, 3, 8, 12, 15, 9, 13000
                                    ),
                                    'id': 'ecs-svc/9223370553143707624',
                                    'runningCount': running_count,
                                    'pendingCount': pending_count,
                                    'status': 'PRIMARY',
                                    'taskDefinition': task_definition_arn,
                                },
                                {
                                    'desiredCount': final_running_count,
                                    'createdAt': datetime.datetime(
                                        2017, 3, 8, 12, 15, 9, 13000
                                    ),
                                    'id': 'ecs-svc/9223370553143707624',
                                    'pendingCount': 0,
                                    'runningCount': 0,
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
        assert event_list[0].pending == 2

        assert not event_list[1].done
        assert event_list[1].running == 1
        assert event_list[1].desired == 2
        assert event_list[1].pending == 1

        assert event_list[2].done
        assert event_list[2].running == 2
        assert event_list[2].desired == 2
        assert event_list[2].pending == 0

    def test_deployment_completed_after_previous_instances_stopped(self):
        environment = 'dummy-environment'
        component = 'dummy-component'
        version = 'dummy-version'
        cluster = 'dummy-cluster'
        boto_session = MagicMock(spec=Session)
        mock_ecs_client = Mock()
        task_definition_arn = ('arn:aws:ecs:eu-west-3:111111111111:'
                               'task-definition/{}:1'.format(component)),

        def describe_services_generator(initial_running_count):
            for running_count in reversed(range(initial_running_count + 1)):
                yield {
                    'services': [
                        {
                            'clusterArn': 'arn:aws:ecs:eu-1:7:cstr/non-prod',
                            'deployments': [
                                {
                                    'desiredCount': initial_running_count,
                                    'createdAt': datetime.datetime(
                                        2017, 1, 6, 10, 58, 9
                                    ),
                                    'id': 'ecs-svc/9223370553143707624',
                                    'runningCount': initial_running_count,
                                    'pendingCount': 0,
                                    'status': 'PRIMARY',
                                    'taskDefinition': task_definition_arn,
                                },
                                {
                                    'desiredCount': initial_running_count,
                                    'createdAt': datetime.datetime(
                                        2017, 1, 6, 10, 58, 9
                                    ),
                                    'id': 'ecs-svc/9223370553143707624',
                                    'pendingCount': 0,
                                    'runningCount': running_count,
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
        assert event_list[0].running == 2
        assert event_list[0].desired == 2
        assert event_list[0].pending == 0
        assert event_list[0].previous_running == 2

        assert not event_list[1].done
        assert event_list[1].running == 2
        assert event_list[1].desired == 2
        assert event_list[1].pending == 0
        assert event_list[1].previous_running == 1

        assert event_list[2].done
        assert event_list[2].running == 2
        assert event_list[2].desired == 2
        assert event_list[2].pending == 0
        assert event_list[2].previous_running == 0

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
                            'createdAt': datetime.datetime(
                                2017, 1, 6, 10, 58, 9
                            ),
                            'id': 'ecs-svc/9223370553143707624',
                            'runningCount': 1,
                            'pendingCount': 1,
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

    def test_memoization_on_object_instance(self):
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
                            u'createdAt': datetime.datetime(
                                2017, 3, 8, 12, 15, 9, 13000, tzinfo=tzlocal()
                            ),
                            'id': 'ecs-svc/9223370553143707624',
                            'runningCount': 1,
                            'pendingCount': 1,
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
        [e.done for e in islice(events, 1000)]

        boto_session.client.assert_called_once()
        mock_ecs_client.describe_task_definition.assert_called_once()

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

    def test_get_ecs_service_events(self):
        # Given
        since = datetime.datetime(
            2017, 3, 8, 12, 15, 0, 0, tzinfo=tzlocal()
        )
        ecs_service_events_1 = [
            {
                u'createdAt': datetime.datetime(
                    2017, 3, 8, 12, 15, 9, 13000, tzinfo=tzlocal()
                ),
                u'id': u'efbfce1c-c7d0-43be-a9a8-d18ad70e9d8b',
                u'message': u'(service aslive-grahamlyons-test) has started 2'
            },
            # the event blow should *not* be returned (it's before since)
            {
                u'createdAt': datetime.datetime(
                    2017, 3, 8, 12, 14, 30, 0, tzinfo=tzlocal()
                ),
                u'id': u'efbfce1c-c7d0-43be-a9a8-d18ad70e9d8b',
                u'message': u'old event'
            }
        ]
        ecs_service_events_2 = [
            {
                u'createdAt': datetime.datetime(
                    2017, 3, 8, 12, 15, 46, 32000, tzinfo=tzlocal()
                ),
                u'id': u'03c1bf6b-4054-4828-adc0-edce84d96c99',
                u'message': u'(service aslive-grahamlyons-test) has reached a'
            },
            {
                u'createdAt': datetime.datetime(
                    2017, 3, 8, 12, 15, 21, 649000, tzinfo=tzlocal()
                ),
                u'id': u'66364f80-7713-4260-a8d7-39ec8207f4a9',
                u'message': u'(service aslive-grahamlyons-test) registered 2 '
            }
        ]

        ecs_event_iterator = ECSEventIterator(ANY, ANY, ANY, ANY, ANY)

        # When
        events_1 = ecs_event_iterator._get_new_ecs_service_events(
            {
                'services': [
                    {
                        'events': ecs_service_events_1[:1]
                    }
                ]
            }, since
        )
        events_2 = ecs_event_iterator._get_new_ecs_service_events(
            {
                'services': [
                    {
                        'events': ecs_service_events_1[:1] +
                        ecs_service_events_2
                    }
                ]
            }, since
        )

        # Then
        assert events_1 == ecs_service_events_1[:1]
        assert events_2 == list(reversed(ecs_service_events_2))

        assert events_1 + events_2 == \
            ecs_service_events_1[:1] + list(reversed(ecs_service_events_2))


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
