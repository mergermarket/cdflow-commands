import unittest

from mock import MagicMock, Mock

from boto3 import Session


class TestECSMonitor(unittest.TestCase):

    @given(fixed_dictionaries({
        'environment': text(),
        'component': text(),
        'version': text()
    }))
    def test_monitor_exited_when_the_deployment_is_stable(
        self, deployment_data
    ):
        environment = deployment_data['environment']
        component = deployment_data['component']
        version = deployment_data['version']
        boto_session = MagicMock(spec=Session)
        mock_ecs_client = Mock()
        mock_ecs_client.describe_services.return_value = {
            'ResponseMetadata': {
                'HTTPHeaders': {
                    'connection': 'keep-alive',
                    'content-length': '23785',
                    'content-type': 'application/x-amz-json-1.1',
                    'date': 'Tue, 28 Feb 2017 16:31:06 GMT',
                    'server': 'Server',
                    'x-amzn-requestid': '4d9c8983-fdd3-11e6-99ed-6bb93e41be46'
                },
                'HTTPStatusCode': 200,
                'RequestId': '4d9c8983-fdd3-11e6-99ed-6bb93e41be46',
                'RetryAttempts': 0
            },
            'failures': [],
            'services': [
                {
                    'clusterArn': 'arn:aws:ecs:eu-1:7:cluster/non-production',
                    'createdAt': datetime.datetime(2017, 1, 6, 10, 58, 9),
                    'deploymentConfiguration': {
                        'maximumPercent': 200,
                        'minimumHealthyPercent': 100
                    },
                   'deployments': [
                        {
                            'createdAt': datetime.datetime(2017, 1, 6, 13, 57),
                            'desiredCount': 2,
                            'id': 'ecs-svc/9223370553143707624',
                            'pendingCount': 0,
                            'runningCount': 2,
                            'status': 'PRIMARY',
                            'taskDefinition': 'aslive-test:3',
                            'updatedAt': datetime.datetime(2017, 1, 6, 13, 57)
                        }
                    ],
                    'desiredCount': 2,
                    'events': [
                        {
                            'createdAt': datetime.datetime(2017, 2, 28, 15),
                            'id': '59d4860e-5734-485e-ad4c-5205193f858e',
                            'message': '(service aslive-testtf2469) '
                                      'has reached a steady state.'
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
                   'placementConstraints': [],
                   'placementStrategy': [],
                   'roleArn': '20170106105800480922659dsq',
                   'runningCount': 2,
                   'serviceArn': 'aslive-testtf2469',
                   'serviceName': 'aslive-testtf2469',
                   'status': 'ACTIVE',
                   'taskDefinition': 'aslive-test:3'
                }
            ]
        }
        boto_session.client.return_value = mock_ecs_client
        monitor = ECSMonitor(environment, component, version, boto_session)

        monitor.wait()

        boto_session.client.assert_any_call('ecs')
