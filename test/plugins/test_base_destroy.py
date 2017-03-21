import unittest
from collections import namedtuple
from string import printable

from cdflow_commands.plugins.base import Destroy
from hypothesis import given
from hypothesis.strategies import dictionaries, fixed_dictionaries, text
from mock import ANY, Mock, patch

BotoCreds = namedtuple('BotoCreds', ['access_key', 'secret_key', 'token'])

CALL_KWARGS = 2


class TestDestroy(unittest.TestCase):

    @given(fixed_dictionaries({
        'component_name': text(alphabet=printable, min_size=1),
        'environment_name': text(alphabet=printable, min_size=1),
        'region': text(alphabet=printable, min_size=8, max_size=12),
    }))
    def test_plan_was_called_via_terragrunt(self, test_fixtures):
        component_name = test_fixtures['component_name']
        environment_name = test_fixtures['environment_name']

        boto_session = Mock()
        boto_session.region_name = test_fixtures['region']
        destroy = Destroy(
            boto_session, component_name, environment_name, 'dummy-bucket'
        )

        with patch('cdflow_commands.plugins.base.check_call') as check_call:
            destroy.run()
            check_call.assert_any_call([
                'terragrunt', 'plan', '-destroy',
                '-var', 'aws_region={}'.format(test_fixtures['region']),
                '/cdflow/tf-destroy'
            ], env=ANY)

    @given(fixed_dictionaries({
        'component_name': text(alphabet=printable, min_size=1),
        'environment_name': text(alphabet=printable, min_size=1),
        'region': text(alphabet=printable, min_size=8, max_size=12),
    }))
    def test_destroy_was_called_via_terragrunt(self, test_fixtures):
        component_name = test_fixtures['component_name']
        environment_name = test_fixtures['environment_name']
        boto_session = Mock()
        boto_session.region_name = test_fixtures['region']
        destroy = Destroy(
            boto_session, component_name, environment_name, 'dummy-bucket'
        )

        with patch('cdflow_commands.plugins.base.check_call') as check_call:
            destroy.run()
            check_call.assert_any_call([
                'terragrunt', 'destroy', '-force',
                '-var', 'aws_region={}'.format(test_fixtures['region']),
                '/cdflow/tf-destroy'
            ], env=ANY)

    @given(fixed_dictionaries({
        'access_key': text(alphabet=printable, min_size=1),
        'secret_key': text(alphabet=printable, min_size=1),
        'session_token': text(alphabet=printable, min_size=1),
    }))
    def test_aws_config_was_passed_into_envionrment(self, aws_config):
        boto_session = Mock()
        boto_session.region_name = 'dummy-region'
        boto_session.get_credentials.return_value = BotoCreds(
            aws_config['access_key'],
            aws_config['secret_key'],
            aws_config['session_token'],
        )
        destroy = Destroy(
            boto_session, 'dummy-component',
            'dummy-environment', 'dummy-bucket'
        )

        with patch('cdflow_commands.plugins.base.check_call') as check_call:
            destroy.run()

            env = check_call.mock_calls[0][CALL_KWARGS]['env']
            assert env['AWS_ACCESS_KEY_ID'] == aws_config['access_key']
            assert env['AWS_SECRET_ACCESS_KEY'] == aws_config['secret_key']
            assert env['AWS_SESSION_TOKEN'] == aws_config['session_token']

            env = check_call.mock_calls[1][CALL_KWARGS]['env']
            assert env['AWS_ACCESS_KEY_ID'] == aws_config['access_key']
            assert env['AWS_SECRET_ACCESS_KEY'] == aws_config['secret_key']
            assert env['AWS_SESSION_TOKEN'] == aws_config['session_token']

    @given(dictionaries(
        keys=text(alphabet=printable, min_size=1),
        values=text(alphabet=printable, min_size=1),
        min_size=1
    ))
    def test_original_environment_was_preserved(self, mock_env):
        boto_session = Mock()
        boto_session.region_name = 'dummy-region'
        boto_session.get_credentials.return_value = BotoCreds(
            'dummy-access-key',
            'dummy-secret-key',
            'dummy-session-token',
        )
        destroy = Destroy(
            boto_session, 'dummy-component',
            'dummy-environment', 'dummy-bucket'
        )

        with patch(
            'cdflow_commands.plugins.base.check_call'
        ) as check_call, patch(
            'cdflow_commands.plugins.base.os'
        ) as mock_os:
            mock_os.environ = mock_env.copy()
            destroy.run()

            env = check_call.mock_calls[0][CALL_KWARGS]['env']
            for key, value in mock_env.items():
                assert env[key] == value

            env = check_call.mock_calls[1][CALL_KWARGS]['env']
            for key, value in mock_env.items():
                assert env[key] == value

    @given(fixed_dictionaries({
        'component_name': text(alphabet=printable, min_size=1),
        'environment_name': text(alphabet=printable, min_size=1),
        's3_bucket_name': text(alphabet=printable, min_size=1),
    }))
    def test_tfstate_removed_from_s3(self, test_fixtures):
        # Given
        boto_session = Mock()
        boto_session.region_name = 'dummy-region'
        boto_session.get_credentials.return_value = BotoCreds(
            'dummy-access-key',
            'dummy-secret-key',
            'dummy-session-token',
        )
        boto_s3_client = Mock()
        boto_session.client.return_value = boto_s3_client
        destroy = Destroy(
            boto_session,
            test_fixtures['component_name'],
            test_fixtures['environment_name'],
            test_fixtures['s3_bucket_name']
        )

        # When
        with patch('cdflow_commands.plugins.base.check_call'):
            destroy.run()

        # Then
        boto_s3_client.delete_object.assert_any_call(
            Bucket=test_fixtures['s3_bucket_name'],
            Key='{}/{}/terraform.tfstate'.format(
                test_fixtures['environment_name'],
                test_fixtures['component_name']
            )
        )
