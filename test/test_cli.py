import unittest

import json
from datetime import datetime
from string import letters, digits, printable

from mock import patch, Mock, MagicMock, mock_open
from hypothesis import given, example
from hypothesis.strategies import text, composite

from cdflow_commands import cli


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

    @patch('cdflow_commands.cli.open', new_callable=mock_open, create=True)
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
        metadata = cli.load_service_metadata()
        assert metadata.team == expected_config['TEAM']
        assert metadata.type == expected_config['TYPE']
        assert metadata.aws_region == expected_config['REGION']
        assert metadata.account_prefix == expected_config['ACCOUNT_PREFIX']
        mock_open.assert_called_once_with('service.json')

    @patch('cdflow_commands.cli.open', new_callable=mock_open, create=True)
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
        config = cli.load_global_config(account_prefix, aws_region)

        assert config.dev_account_id == 123456789
        assert config.prod_account_id == 987654321

        file_path_template = 'infra/platform-config/{}/{}/{}.json'
        mock_open.assert_any_call(
            file_path_template.format(account_prefix, 'dev', aws_region)
        )
        mock_open.assert_any_call(
            file_path_template.format(account_prefix, 'prod', aws_region)
        )


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.load_global_config')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.Release')
    @patch('cdflow_commands.cli.ReleaseConfig')
    def test_release_is_configured(
        self, ReleaseConfig, Release, assume_role, load_global_config
    ):
        mock_config = Mock()
        ReleaseConfig.return_value = mock_config

        mock_boto_session = Mock()
        assume_role.return_value = mock_boto_session
        mock_ecr_client = Mock()
        mock_boto_session.client.return_value = mock_ecr_client

        dev_account_id = 1
        prod_account_id = 2
        aws_region = 'eu-west-8'
        mock_global_config = Mock()
        mock_global_config.dev_account_id = dev_account_id
        mock_global_config.prod_account_id = prod_account_id
        mock_global_config.aws_region = aws_region
        load_global_config.return_value = mock_global_config

        component_name = 'dummy-component'
        version = '1.2.3'
        cli.run(['release', version, '-c', component_name])

        ReleaseConfig.assert_called_once_with(
            dev_account_id, prod_account_id, aws_region
        )

        Release.assert_called_once_with(
            mock_config, mock_ecr_client, component_name, version
        )


class TestAssumeRole(unittest.TestCase):

    @patch('cdflow_commands.cli.Session')
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
        session = cli.assume_role(mock_root_session, account_id, session_name)
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
        role_session_name = cli.get_role_session_name(env)

        assert role_session_name == job_name

    @given(text(alphabet=ROLE_UNSAFE_ALPHABET, min_size=8, max_size=64))
    def test_get_session_name_from_unsafe_job_name(self, job_name):
        env = {
            'JOB_NAME': job_name
        }
        role_session_name = cli.get_role_session_name(env)

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
        role_session_name = cli.get_role_session_name(env)

        assert len(role_session_name) <= 64

    @given(text(alphabet=ROLE_SAFE_ALPHABET, min_size=0, max_size=5))
    def test_user_error_raised_for_too_short_job_name(self, job_name):
        env = {
            'JOB_NAME': job_name
        }
        self.assertRaises(
            cli.JobNameTooShortError,
            cli.get_role_session_name,
            env
        )

    @given(email())
    @example('user@example.co.uk')
    def test_get_session_name_from_email(self, email):
        env = {
            'EMAIL': email
        }
        role_session_name = cli.get_role_session_name(env)

        for character in ROLE_UNSAFE_CHARACTERS:
            assert character not in role_session_name

    @given(email(min_size=100))
    def test_get_session_name_from_unsafe_email_truncated(self, email):
        env = {
            'EMAIL': email
        }
        role_session_name = cli.get_role_session_name(env)

        assert len(role_session_name) <= 64

    @given(text(alphabet=letters))
    @example(r'Abc.example.com')
    @example(r'john.doe@example..com')
    def test_invalid_email_address(self, email):
        env = {
            'EMAIL': email
        }
        self.assertRaises(
            cli.InvalidEmailError,
            cli.get_role_session_name,
            env
        )

    def test_user_error_when_no_job_name_or_email(self):
        self.assertRaises(
            cli.NoJobNameOrEmailError,
            cli.get_role_session_name,
            {}
        )
