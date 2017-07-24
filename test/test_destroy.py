import unittest
from collections import namedtuple
from contextlib import ExitStack

from hypothesis import given
from hypothesis.strategies import fixed_dictionaries, text
from mock import Mock, patch

from cdflow_commands.destroy import Destroy
from cdflow_commands.constants import (
    TERRAFORM_BINARY, TERRAFORM_DESTROY_DEFINITION,
)


BotoCredentials = namedtuple(
    'BotoCredentials', ['access_key', 'secret_key', 'token'],
)


class TestDestroy(unittest.TestCase):

    @given(fixed_dictionaries({
        'component_name': text(),
        'environment': text(),
        'bucket_name': text(),
        'aws_access_key_id': text(),
        'aws_secret_access_key': text(),
        'aws_session_token': text(),
    }))
    def test_destroy_calls_terraform_plan(self, fixtures):
        component_name = fixtures['component_name']
        environment = fixtures['environment']
        bucket_name = fixtures['bucket_name']
        aws_access_key_id = fixtures['aws_access_key_id']
        aws_secret_access_key = fixtures['aws_secret_access_key']
        aws_session_token = fixtures['aws_session_token']
        session = Mock()

        session.get_credentials.return_value = BotoCredentials(
            aws_access_key_id, aws_secret_access_key, aws_session_token
        )

        destroy = Destroy(session, component_name, environment, bucket_name)

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

        check_call.assert_any_call([
            TERRAFORM_BINARY, 'plan',
            '-destroy',
            '-var', 'aws_region={}'.format(session.region_name),
            '-out', 'plan-{}'.format(time.return_value),
            TERRAFORM_DESTROY_DEFINITION,
        ], env={
            'AWS_ACCESS_KEY_ID': aws_access_key_id,
            'AWS_SECRET_ACCESS_KEY': aws_secret_access_key,
            'AWS_SESSION_TOKEN': aws_session_token,
        })
