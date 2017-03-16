import unittest
from string import ascii_letters, digits, printable

from mock import patch
from hypothesis import given, assume
from hypothesis.strategies import text, fixed_dictionaries, dictionaries

from boto3.session import Session
from botocore.exceptions import ClientError

from cdflow_commands.secrets import get_secrets

CALL_KWARGS = 2
IDENTIFIERS = ascii_letters + digits + '-_'


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
            'cdflow_commands.secrets.credstash'
        ) as mock_credstash:
            secret_key_1 = ("deploy.{env_name}.{component_name}.{secret}"
                            .format(**inputs))
            secret_key_2 = ("deploy.{env_name}.{component_name}.{other_secret}"
                            .format(**inputs))
            mock_credstash.listSecrets.return_value = [
                {
                    u'version': u'0000000000000000001',
                    u'name': ("{prefix}.{env_name}.{component_name}.{secret}"
                              .format(**inputs))
                },
                {
                    u'version': u'0000000000000000002',
                    u'name': secret_key_1
                },
                {
                    u'version': u'0000000000000000002',
                    u'name': ("deploy.{other_env_name}.{component_name}."
                              "{secret}".format(**inputs))
                },
                {
                    u'version': u'0000000000000000002',
                    u'name': secret_key_2
                },
                {
                    u'version': u'0000000000000000002',
                    u'name': ("deploy.{env_name}.{other_component_name}."
                              "{secret}".format(**inputs))
                }
            ]

            def _get_secret(name, *args, **kwargs):
                if name == secret_key_1:
                    return inputs['secret_value']
                if name == secret_key_2:
                    return inputs['other_secret_value']

            mock_credstash.getSecret = _get_secret

            boto_session = Session(
                inputs['access_key_id'],
                inputs['secret_access_key'],
                inputs['session_token'],
                inputs['aws_region']
            )

            expected_secrets = {
                inputs['secret']: inputs['secret_value'],
                inputs['other_secret']: inputs['other_secret_value']
            }

            # When
            credentials = get_secrets(
                inputs['env_name'],
                inputs['team'],
                inputs['component_name'],
                boto_session
            )

            # Then
            assert credentials == expected_secrets

    def test_missing_credtash_table_is_handled_gracefully(self):
        boto_session = Session(
            'dummy-access_key_id',
            'dummy-secret_access_key',
            'dummy-session_token',
            'dummy-aws_region'
        )

        with patch('cdflow_commands.secrets.credstash') as credstash:
            credstash.listSecrets.side_effect = ClientError(
                {'Error': {'Code': 'ResourceNotFoundException'}},
                'Operation'
            )

            secrets = get_secrets(
                'dummy-env',
                'dummy-team',
                'dummy-component',
                boto_session
            )

            assert {} == secrets

    def test_other_exception_surfaced(self):
        boto_session = Session(
            'dummy-access_key_id',
            'dummy-secret_access_key',
            'dummy-session_token',
            'dummy-aws_region'
        )

        with patch('cdflow_commands.secrets.credstash') as credstash:
            credstash.listSecrets.side_effect = ClientError(
                {'Error': {'Code': 'OtherException'}},
                'Operation'
            )

            self.assertRaises(
                ClientError, get_secrets,
                'dummy-env', 'dummy-team', 'dummy-component', boto_session
            )
