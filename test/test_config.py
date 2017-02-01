import unittest

import json
from datetime import datetime
from string import letters, digits, printable

from mock import patch, Mock, MagicMock, mock_open
from hypothesis import given, example
from hypothesis.strategies import text, composite

from cdflow_commands import config


ROLE_SAFE_ALPHABET = letters + digits + '+=,.@-'
ROLE_UNSAFE_CHARACTERS = '\/!$%^&*()#'
ROLE_UNSAFE_ALPHABET = ROLE_SAFE_ALPHABET + ROLE_UNSAFE_CHARACTERS


@composite
def email(draw, min_size=7):
    min_generated_characters = min_size - 2
    user_min_characters = int(min_generated_characters / 3)
    domain_min_characters = int(
        min_generated_characters - user_min_characters
    ) / 2
    tld_min_characters = min_generated_characters - domain_min_characters

    user = draw(text(
        alphabet=printable,
        min_size=user_min_characters,
        max_size=user_min_characters + 40
    ))
    domain = draw(text(
        alphabet=letters + digits + '-',
        min_size=domain_min_characters,
        max_size=domain_min_characters + 20
    ))
    tld = draw(text(
        alphabet=letters,
        min_size=tld_min_characters,
        max_size=tld_min_characters + 5
    ))
    return '{}@{}.{}'.format(user, domain, tld)


class TestLoadConfig(unittest.TestCase):

    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_service_metadata_loaded(self, mock_open):
        mock_file = MagicMock(spec=file)
        expected_config = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-1',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_file.read.return_value = json.dumps(expected_config)
        mock_open.return_value.__enter__.return_value = mock_file
        metadata = config.load_service_metadata()
        assert metadata.team == expected_config['TEAM']
        assert metadata.type == expected_config['TYPE']
        assert metadata.aws_region == expected_config['REGION']
        assert metadata.account_prefix == expected_config['ACCOUNT_PREFIX']
        mock_open.assert_called_once_with('service.json')

    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_loaded_from_file(self, mock_open):
        mock_dev_file = MagicMock(spec=file)
        dev_config = {
            'platform_config': {
                'account_id': 123456789
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=file)
        prod_config = {
            'platform_config': {
                'account_id': 987654321
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_dev_file, mock_prod_file)
        )

        account_prefix = 'mmg'
        aws_region = 'eu-west-5'
        global_config = config.load_global_config(account_prefix, aws_region)

        assert global_config.dev_account_id == 123456789
        assert global_config.prod_account_id == 987654321

        file_path_template = 'infra/platform-config/{}/{}/{}.json'
        mock_open.assert_any_call(
            file_path_template.format(account_prefix, 'dev', aws_region)
        )
        mock_open.assert_any_call(
            file_path_template.format(account_prefix, 'prod', aws_region)
        )


class TestAssumeRole(unittest.TestCase):

    @patch('cdflow_commands.config.Session')
    def test_role_is_assumed(self, MockSession):

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'

        mock_session = Mock()
        MockSession.return_value = mock_session

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

        account_id = 123456789
        session_name = 'dummy-session-name'
        session = config.assume_role(
            mock_root_session, account_id, session_name
        )
        assert session is mock_session

        mock_root_session.client.assert_called_once_with('sts')
        mock_sts.assume_role.assert_called_once_with(
            RoleArn='arn:aws:iam::{}:role/admin'.format(account_id),
            RoleSessionName=session_name,
        )
        MockSession.assert_called_once_with(
            'dummy-access-key-id',
            'dummy-secret-access-key',
            'dummy-session-token',
            'eu-west-12',
        )


class TestGetRoleSessionName(unittest.TestCase):

    @given(text(alphabet=ROLE_SAFE_ALPHABET, min_size=8, max_size=64))
    def test_get_session_name_from_safe_job_name(self, job_name):
        env = {
            'JOB_NAME': job_name
        }
        role_session_name = config.get_role_session_name(env)

        assert role_session_name == job_name

    @given(text(alphabet=ROLE_UNSAFE_ALPHABET, min_size=8, max_size=64))
    def test_get_session_name_from_unsafe_job_name(self, job_name):
        env = {
            'JOB_NAME': job_name
        }
        role_session_name = config.get_role_session_name(env)

        for character in ROLE_UNSAFE_CHARACTERS:
            assert character not in role_session_name

    @given(text(alphabet=ROLE_UNSAFE_ALPHABET, min_size=8, max_size=100))
    @example(
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    )
    def test_get_session_name_from_unsafe_job_name_truncated(self, job_name):
        env = {
            'JOB_NAME': job_name
        }
        role_session_name = config.get_role_session_name(env)

        assert len(role_session_name) <= 64

    @given(text(alphabet=ROLE_SAFE_ALPHABET, min_size=0, max_size=5))
    def test_user_error_raised_for_too_short_job_name(self, job_name):
        env = {
            'JOB_NAME': job_name
        }
        self.assertRaises(
            config.JobNameTooShortError,
            config.get_role_session_name,
            env
        )

    @given(email())
    @example('user@example.co.uk')
    def test_get_session_name_from_email(self, email):
        env = {
            'EMAIL': email
        }
        role_session_name = config.get_role_session_name(env)

        for character in ROLE_UNSAFE_CHARACTERS:
            assert character not in role_session_name

    @given(email(min_size=100))
    def test_get_session_name_from_unsafe_email_truncated(self, email):
        env = {
            'EMAIL': email
        }
        role_session_name = config.get_role_session_name(env)

        assert len(role_session_name) <= 64

    @given(text(alphabet=letters))
    @example(r'Abc.example.com')
    @example(r'john.doe@example..com')
    def test_invalid_email_address(self, email):
        env = {
            'EMAIL': email
        }
        self.assertRaises(
            config.InvalidEmailError,
            config.get_role_session_name,
            env
        )

    def test_user_error_when_no_job_name_or_email(self):
        self.assertRaises(
            config.NoJobNameOrEmailError,
            config.get_role_session_name,
            {}
        )


class TestGetComponentName(unittest.TestCase):

    def test_component_passed_as_argument(self):
        component_name = config.get_component_name('dummy-name')
        assert component_name == 'dummy-name'

    @given(text(alphabet=letters + digits + '-._', min_size=1, max_size=100))
    def test_component_not_passed_as_argument(self, component_name):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'git@github.com:org/{}.git\n'.format(
                component_name
            )
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(alphabet=letters + digits + '-._', min_size=1, max_size=100))
    def test_component_not_passed_as_argument_without_extension(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'git@github.com:org/{}\n'.format(
                component_name
            )
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(alphabet=letters + digits + '-._', min_size=1, max_size=100))
    def test_component_not_passed_as_argument_with_https_origin(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            repo_template = 'https://github.com/org/{}.git\n'
            check_output.return_value = repo_template.format(
                component_name
            )
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(alphabet=letters + digits + '-._', min_size=1, max_size=100))
    def test_component_not_passed_as_argument_with_https_without_extension(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'https://github.com/org/{}\n'.format(
                component_name
            )
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name
