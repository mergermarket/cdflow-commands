import unittest
from collections import namedtuple
from contextlib import ExitStack

from hypothesis import given
from hypothesis.strategies import fixed_dictionaries, text
from mock import Mock, patch

from cdflow_commands.destroy import Destroy
from cdflow_commands.constants import (
    CDFLOW_BASE_PATH, TERRAFORM_BINARY, TERRAFORM_DESTROY_DEFINITION,
)


BotoCredentials = namedtuple(
    'BotoCredentials', ['access_key', 'secret_key', 'token'],
)


class TestDestroy(unittest.TestCase):

    @given(fixed_dictionaries({
        'aws_access_key_id': text(),
        'aws_secret_access_key': text(),
        'aws_session_token': text(),
        'region': text(),
    }))
    def test_destroy_calls_terraform_plan(self, fixtures):
        aws_access_key_id = fixtures['aws_access_key_id']
        aws_secret_access_key = fixtures['aws_secret_access_key']
        aws_session_token = fixtures['aws_session_token']
        session = Mock()
        session.region_name = fixtures['region']

        session.get_credentials.return_value = BotoCredentials(
            aws_access_key_id, aws_secret_access_key, aws_session_token
        )

        destroy = Destroy(session)

        with ExitStack() as stack:
            check_call = stack.enter_context(
                patch('cdflow_commands.destroy.check_call')
            )
            time = stack.enter_context(
                patch('cdflow_commands.destroy.time')
            )
            stack.enter_context(
                patch.dict(
                    'cdflow_commands.destroy.os.environ',
                    values={}, clear=True,
                )
            )

            destroy.run()

        check_call.assert_any_call(
            [
                TERRAFORM_BINARY, 'plan',
                '-destroy',
                '-out', 'plan-{}'.format(time.return_value),
                TERRAFORM_DESTROY_DEFINITION,
            ],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token,
                'AWS_DEFAULT_REGION': fixtures['region'],
            },
            cwd=CDFLOW_BASE_PATH,
        )

    @given(fixed_dictionaries({
        'aws_access_key_id': text(),
        'aws_secret_access_key': text(),
        'aws_session_token': text(),
        'region': text(),
    }))
    def test_terraform_destroy_is_called(self, fixtures):
        aws_access_key_id = fixtures['aws_access_key_id']
        aws_secret_access_key = fixtures['aws_secret_access_key']
        aws_session_token = fixtures['aws_session_token']
        session = Mock()
        session.region_name = fixtures['region']

        session.get_credentials.return_value = BotoCredentials(
            aws_access_key_id, aws_secret_access_key, aws_session_token
        )

        destroy = Destroy(session)

        with ExitStack() as stack:
            check_call = stack.enter_context(
                patch('cdflow_commands.destroy.check_call')
            )
            time = stack.enter_context(
                patch('cdflow_commands.destroy.time')
            )
            stack.enter_context(
                patch.dict(
                    'cdflow_commands.destroy.os.environ',
                    values={}, clear=True,
                )
            )

            destroy.run()

        check_call.assert_any_call(
            [TERRAFORM_BINARY, 'apply', 'plan-{}'.format(time.return_value)],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token,
                'AWS_DEFAULT_REGION': fixtures['region'],
            },
            cwd=CDFLOW_BASE_PATH,
        )

    @given(fixed_dictionaries({
        'aws_access_key_id': text(),
        'aws_secret_access_key': text(),
        'aws_session_token': text(),
        'region': text(),
    }))
    def test_plan_only_flag_does_not_run_destroy(self, fixtures):
        aws_access_key_id = fixtures['aws_access_key_id']
        aws_secret_access_key = fixtures['aws_secret_access_key']
        aws_session_token = fixtures['aws_session_token']
        session = Mock()
        session.region_name = fixtures['region']

        session.get_credentials.return_value = BotoCredentials(
            aws_access_key_id, aws_secret_access_key, aws_session_token
        )

        destroy = Destroy(session)

        with ExitStack() as stack:
            check_call = stack.enter_context(
                patch('cdflow_commands.destroy.check_call')
            )
            time = stack.enter_context(
                patch('cdflow_commands.destroy.time')
            )
            stack.enter_context(
                patch.dict(
                    'cdflow_commands.destroy.os.environ',
                    values={}, clear=True,
                )
            )

            destroy.run(plan_only=True)

        check_call.assert_called_once_with(
            [
                TERRAFORM_BINARY, 'plan',
                '-destroy',
                '-out', 'plan-{}'.format(time.return_value),
                TERRAFORM_DESTROY_DEFINITION,
            ],
            env={
                'AWS_ACCESS_KEY_ID': aws_access_key_id,
                'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
                'AWS_SESSION_TOKEN': aws_session_token,
                'AWS_DEFAULT_REGION': fixtures['region'],
            },
            cwd=CDFLOW_BASE_PATH,
        )
