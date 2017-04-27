import unittest
import json

from io import TextIOWrapper
from datetime import datetime
from cdflow_commands import cli
from mock import Mock, MagicMock, patch, mock_open


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.config.Session')
    @patch('cdflow_commands.cli.Session')
    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_release_package_is_created(
        self, mock_open, mock_os, session_from_cli, session_from_config
    ):
        mock_metadata_file = MagicMock(spec=TextIOWrapper)
        metadata = {
            'TEAM': 'dummy-team',
            'TYPE': 'lambda',
            'REGION': 'eu-west-12',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_metadata_file.read.return_value = json.dumps(metadata)
        mock_dev_file = MagicMock(spec=TextIOWrapper)
        dev_config = {
            'platform_config': {
                'account_id': 123456789,
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=TextIOWrapper)
        prod_config = {
            'platform_config': {
                'account_id': 987654321,
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_metadata_file, mock_dev_file, mock_prod_file)
        )

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'
        session_from_cli.return_value = mock_root_session

        mock_ecr_client = Mock()
        mock_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': 'dXNlcm5hbWU6cGFzc3dvcmQ=',
                    'proxyEndpoint': 'dummy-endpoint'
                }
            ]
        }

        mock_session = Mock()
        mock_session.client.return_value = mock_ecr_client
        session_from_config.return_value = mock_session

        mock_sts = Mock()
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'dummy-access-key-id',
                'SecretAccessKey': 'dummy-secret-access-key',
                'SessionToken': 'dummy-session-token',
                'Expiration': datetime(2015, 1, 1)
            },
            'AssumedRoleUser': {
                'AssumedRoleId': 'dummy-assumed-role-id',
                'Arn': 'dummy-arn'
            },
            'PackedPolicySize': 123
        }
        mock_root_session.client.return_value = mock_sts

        mock_os.environ = {
            'JOB_NAME': 'dummy-job-name'
        }

        component_name = 'dummy-component'
        version = '6.1.7'
        cli.run(['release', version, '-c', component_name])
