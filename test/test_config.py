import json
import yaml
import unittest
from datetime import datetime
from io import TextIOWrapper
from string import ascii_letters, digits, printable
from subprocess import CalledProcessError

from cdflow_commands import config
from cdflow_commands.exceptions import UserFacingError
from hypothesis import example, given, assume
from hypothesis.strategies import composite, fixed_dictionaries, lists, text
from mock import MagicMock, Mock, mock_open, patch

ROLE_SAFE_ALPHABET = ascii_letters + digits + '+=,.@-'
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
        alphabet=ascii_letters + digits + '-',
        min_size=domain_min_characters,
        max_size=domain_min_characters + 20
    ))
    tld = draw(text(
        alphabet=ascii_letters,
        min_size=tld_min_characters,
        max_size=tld_min_characters + 5
    ))
    return '{}@{}.{}'.format(user, domain, tld)


@composite
def s3_bucket_and_key(draw):
    bucket = draw(text(alphabet=ascii_letters+digits+'-', min_size=3))
    key_parts = draw(lists(
        elements=text(alphabet=printable, min_size=1),
        min_size=1
    ))
    key = '/'.join(key_parts)
    return bucket, key


class TestLoadManifest(unittest.TestCase):

    @given(fixed_dictionaries({
        'account-scheme-url': text(),
        'team': text(),
        'type': text(),
    }))
    def test_load_manifest(self, fixtures):
        # Given
        mock_file = MagicMock(spec=TextIOWrapper)
        mock_file.read.return_value = yaml.dump(fixtures)

        with patch(
            'cdflow_commands.config.open', new_callable=mock_open, create=True
        ) as open_:
            open_.return_value.__enter__.return_value = mock_file

            # When
            manifest = config.load_manifest()

        # Then
        assert manifest.account_scheme_url == fixtures['account-scheme-url']
        assert manifest.team == fixtures['team']
        assert manifest.type == fixtures['type']


class TestLoadConfig(unittest.TestCase):

    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_service_metadata_user_facing_error(self, mock_open):
        mock_file = MagicMock(spec=TextIOWrapper)
        expected_config = {
            'FOO': 'bar',
        }
        mock_file.read.return_value = json.dumps(expected_config)
        mock_open.return_value.__enter__.return_value = mock_file
        with self.assertRaisesRegexp(
            UserFacingError,
            'Deployment failed - did you set .* in .*'
        ):
            config.load_service_metadata()

    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_service_metadata_loaded_with_default_ecs_cluster(self, mock_open):
        mock_file = MagicMock(spec=TextIOWrapper)
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
        assert metadata.ecs_cluster == 'default'
        mock_open.assert_called_once_with('service.json')

    @given(text(alphabet=ascii_letters, min_size=8, max_size=32))
    def test_service_metadata_loaded_with_specific_ecs_cluster(
        self, ecs_cluster_name
    ):
        mock_file = MagicMock(spec=TextIOWrapper)
        expected_config = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-1',
            'ACCOUNT_PREFIX': 'mmg',
            'ECS_CLUSTER': ecs_cluster_name
        }
        with patch(
            'cdflow_commands.config.open', new_callable=mock_open, create=True
        ) as mocked_open:
            mock_file.read.return_value = json.dumps(expected_config)
            mocked_open.return_value.__enter__.return_value = mock_file
            metadata = config.load_service_metadata()
            assert metadata.team == expected_config['TEAM']
            assert metadata.type == expected_config['TYPE']
            assert metadata.aws_region == expected_config['REGION']
            assert metadata.account_prefix == expected_config['ACCOUNT_PREFIX']
            assert metadata.ecs_cluster == ecs_cluster_name
            mocked_open.assert_called_once_with('service.json')

    @patch('cdflow_commands.config.open', new_callable=mock_open, create=True)
    def test_loaded_from_file(self, mock_open):
        mock_dev_file = MagicMock(spec=TextIOWrapper)
        dev_config = {
            'platform_config': {
                'account_id': 123456789
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=TextIOWrapper)
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

    @given(text(alphabet=ascii_letters))
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

    @given(text(
        alphabet=ascii_letters + digits + '-._', min_size=1, max_size=100
    ))
    def test_component_not_passed_as_argument(self, component_name):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'git@github.com:org/{}.git\n'.format(
                component_name
            ).encode('utf-8')
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(
        alphabet=ascii_letters + digits + '-._', min_size=1, max_size=100
    ))
    def test_component_not_passed_as_argument_without_extension(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'git@github.com:org/{}\n'.format(
                component_name
            ).encode('utf-8')
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(
        alphabet=ascii_letters + digits + '-._', min_size=1, max_size=100
    ))
    def test_component_not_passed_as_argument_with_backslash(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'git@github.com:org/{}/\n'.format(
                component_name
            ).encode('utf-8')
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(
        alphabet=ascii_letters + digits + '-._', min_size=1, max_size=100
    ))
    def test_component_not_passed_as_argument_with_https_origin(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            repo_template = 'https://github.com/org/{}.git\n'
            check_output.return_value = repo_template.format(
                component_name
            ).encode('utf-8')
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @given(text(
        alphabet=ascii_letters + digits + '-._', min_size=1, max_size=100
    ))
    def test_component_not_passed_as_argument_with_https_without_extension(
        self, component_name
    ):
        with patch('cdflow_commands.config.check_output') as check_output:
            check_output.return_value = 'https://github.com/org/{}\n'.format(
                component_name
            ).encode('utf-8')
            extraced_component_name = config.get_component_name(None)

            assert extraced_component_name == component_name

    @patch('cdflow_commands.config.check_output')
    def test_user_error_raised_for_no_git_remote(self, check_output):
        check_output.side_effect = CalledProcessError(1, 'git')
        self.assertRaises(
            config.NoGitRemoteError,
            config.get_component_name,
            None
        )


class TestGetPlatformConfigPath(unittest.TestCase):

    @given(fixed_dictionaries({
        'account_prefix': text(alphabet=printable),
        'aws_region': text(alphabet=printable),
    }))
    def test_get_platform_config_path(self, function_inputs):
        function_inputs['is_prod'] = False
        path = config.get_platform_config_path(
            **function_inputs
        )
        assert path == 'infra/platform-config/{}/dev/{}.json'.format(
            function_inputs['account_prefix'],
            function_inputs['aws_region'],
        )

    @given(fixed_dictionaries({
        'account_prefix': text(alphabet=printable),
        'aws_region': text(alphabet=printable),
    }))
    def test_get_platform_config_path_for_live(self, function_inputs):
        function_inputs['is_prod'] = True
        path = config.get_platform_config_path(
            **function_inputs
        )
        assert path == 'infra/platform-config/{}/prod/{}.json'.format(
            function_inputs['account_prefix'],
            function_inputs['aws_region'],
        )


class TestParseS3Url(unittest.TestCase):

    @given(s3_bucket_and_key())
    def test_gets_bucket_name_and_key(self, s3_bucket_and_key):
        expected_bucket = s3_bucket_and_key[0]
        expected_key = s3_bucket_and_key[1]
        s3_url = 's3://{}/{}'.format(expected_bucket, expected_key)

        bucket, key = config.parse_s3_url(s3_url)

        assert bucket == expected_bucket
        assert key == expected_key

    @given(text())
    def test_invalid_url_protocol_throws_exception(self, invalid_url):
        assume(not invalid_url.startswith('s3://'))

        self.assertRaises(
            config.InvalidURLError, config.parse_s3_url, invalid_url
        )

    @given(text(alphabet=printable))
    def test_invalid_url_format_throws_exception(self, invalid_url):
        assume('/' not in invalid_url)

        self.assertRaises(
            config.InvalidURLError, config.parse_s3_url,
            's3://{}'.format(invalid_url)
        )


class TestAccountSchemeHandling(unittest.TestCase):

    @given(fixed_dictionaries({
        's3_bucket_and_key': s3_bucket_and_key(),
        'account_prefix': text(alphabet=ascii_letters+digits, min_size=1),
    }))
    def test_fetch_account_scheme(self, fixtures):
        s3_resource = Mock()

        account_prefix = fixtures['account_prefix']
        bucket = fixtures['s3_bucket_and_key'][0]
        key = fixtures['s3_bucket_and_key'][1]

        mock_s3_body = Mock()
        mock_s3_body.read.return_value = '''
            {{
              "accounts": {{
                "{0}dev": {{
                  "id": "222222222222",
                  "role": "admin"
                }},
                "{0}prod": {{
                  "id": "111111111111",
                  "role": "admin"
                }}
              }},
              "release-account": "{0}dev",
              "release-bucket": "{0}-account-resources",
              "environments": {{
                "live": "{0}prod",
                "*": "{0}dev"
              }},
              "default-region": "eu-west-12"
            }}
        '''.format(account_prefix)

        s3_resource.Object.return_value.get.return_value = {
            'Body': mock_s3_body
        }

        account_scheme = config.fetch_account_scheme(
            s3_resource, bucket, key
        )

        expected_keys = sorted([
            'accounts', 'release-account', 'release-bucket',
            'environments', 'default-region'
        ])

        assert sorted(account_scheme.keys()) == expected_keys

        s3_resource.Object.assert_called_once_with(bucket, key)

    @given(fixed_dictionaries({
        's3_bucket_and_key': s3_bucket_and_key(),
        'account_prefix': text(alphabet=ascii_letters+digits, min_size=1),
    }))
    def test_build_account_scheme(self, fixtures):
        s3_resource = Mock()

        account_prefix = fixtures['account_prefix']
        s3_url = 's3://{}/{}'.format(*fixtures['s3_bucket_and_key'])

        mock_s3_body = Mock()
        mock_s3_body.read.return_value = '''
            {{
              "accounts": {{
                "{0}dev": {{
                  "id": "222222222222",
                  "role": "admin"
                }},
                "{0}prod": {{
                  "id": "111111111111",
                  "role": "admin"
                }}
              }},
              "release-account": "{0}dev",
              "release-bucket": "{0}-account-resources",
              "environments": {{
                "live": "{0}prod",
                "*": "{0}dev"
              }},
              "default-region": "eu-west-12"
            }}
        '''.format(account_prefix)

        s3_resource.Object.return_value.get.return_value = {
            'Body': mock_s3_body
        }

        account_scheme = config.build_account_scheme(s3_resource, s3_url)

        assert account_scheme.release_account.id == '222222222222'
        assert sorted(account_scheme.account_ids) == \
            sorted(['111111111111', '222222222222'])

        s3_resource.Object.assert_called_once_with(
            *fixtures['s3_bucket_and_key']
        )
