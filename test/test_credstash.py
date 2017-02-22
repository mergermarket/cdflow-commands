import unittest
from textwrap import dedent
from string import ascii_letters, digits, printable
from mock import patch, ANY
from hypothesis import given, assume
from hypothesis.strategies import text, fixed_dictionaries, dictionaries
from boto3.session import Session

from cdflow_commands.credstash import get_secrets

CALL_KWARGS = 2
IDENTIFIERS = ascii_letters + digits + '-._'


class TestGetBuildSecretsFromCredstash(unittest.TestCase):
    inputs = fixed_dictionaries({
        'prefix': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'team': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'env_name': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'other_env_name': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'component_name': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'other_component_name': text(
            alphabet=IDENTIFIERS, min_size=1, max_size=9
        ),
        'secret': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'secret_value': text(alphabet=printable, min_size=1, max_size=9),
        'other_secret': text(alphabet=IDENTIFIERS, min_size=1, max_size=9),
        'other_secret_value': text(alphabet=printable, min_size=1, max_size=9),
        'access_key_id': text(alphabet=printable, min_size=20, max_size=20),
        'secret_access_key': text(
            alphabet=printable, min_size=40, max_size=40
        ),
        'session_token': text(alphabet=printable, min_size=20, max_size=20),
        'aws_region': text(alphabet=printable, min_size=5, max_size=12),
        'env': dictionaries(
            keys=text(alphabet=printable), values=text(alphabet=printable)
        )
    })

    @given(inputs)
    def test_secrets_fetched(self, inputs):

        # Given
        assume(inputs['prefix'] != 'deploy')
        assume(inputs['component_name'] != inputs['other_component_name'])
        assume(inputs['env_name'] != inputs['other_env_name'])
        assume(inputs['secret'] != inputs['other_secret'])
        assume(inputs['secret_value'] != 'dummy')
        assume(inputs['other_secret_value'] != 'dummy')
        with patch(
            'cdflow_commands.credstash.check_output'
        ) as check_output, patch(
            'cdflow_commands.credstash.os'
        ) as mock_os:
            # second and forth are valid, others are decoys
            return_values = []

            return_values.append(dedent("""
                {prefix}.{env_name}.{component_name}.{secret} -- decoy
                deploy.{env_name}.{component_name}.{secret} -- valid
                deploy.{other_env_name}.{component_name}.{secret} -- decoy
                deploy.{env_name}.{component_name}.{other_secret} -- valid
                deploy.{env_name}.{other_component_name}.{secret} -- decoy
            """.format(**inputs)).strip() + '\n')

            return_values.append(
                inputs['secret_value'] + '\n'
            )
            return_values.append(
                inputs['other_secret_value'] + '\n'
            )
            check_output.side_effect = return_values

            boto_session = Session(
                inputs['access_key_id'],
                inputs['secret_access_key'],
                inputs['session_token'],
                inputs['aws_region']
            )
            mock_os.environ = inputs['env'].copy()

            # When
            credentials = get_secrets(
                inputs['env_name'],
                inputs['team'],
                inputs['component_name'],
                boto_session
            )

            # Then
            self.assertDictEqual({
                inputs['secret']: inputs['secret_value'],
                inputs['other_secret']: inputs['other_secret_value']
            }, credentials)

            check_output.assert_any_call([
                'credstash',
                '-t', 'credstash-{}'.format(inputs['team']),
                '-r', inputs['aws_region'],
                'list'
            ], env=ANY)

            check_output.assert_any_call([
                'credstash',
                '-t', 'credstash-{}'.format(inputs['team']),
                '-r', inputs['aws_region'],
                'get',
                'deploy.{env_name}.{component_name}.{secret}'.format(**inputs)
            ], env=ANY)

            check_output.assert_any_call([
                'credstash',
                '-t', 'credstash-{}'.format(inputs['team']),
                '-r', inputs['aws_region'],
                'get',
                'deploy.{env_name}.{component_name}.{other_secret}'.format(
                    **inputs
                )
            ], env=ANY)

            aws_env_vars = {
                'AWS_ACCESS_KEY_ID': inputs['access_key_id'],
                'AWS_SECRET_ACCESS_KEY': inputs['secret_access_key'],
                'AWS_SESSION_TOKEN': inputs['session_token']
            }
            expected_env = {**inputs['env'], **aws_env_vars}

            env = check_output.mock_calls[0][CALL_KWARGS]['env']
            self.assertDictEqual(expected_env, env)
            assert(env == check_output.mock_calls[1][CALL_KWARGS]['env'])
            assert(env == check_output.mock_calls[2][CALL_KWARGS]['env'])

            self.assertDictEqual(inputs['env'], mock_os.environ)
