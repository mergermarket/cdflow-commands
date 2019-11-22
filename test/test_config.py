import yaml
import json
import unittest
from datetime import datetime
from io import TextIOWrapper
import re
from string import ascii_letters, digits, printable
from subprocess import CalledProcessError

from cdflow_commands import config
from cdflow_commands.account import Account
from hypothesis import given, assume
from hypothesis.strategies import composite, fixed_dictionaries, lists, text
from mock import MagicMock, Mock, mock_open, patch

ROLE_SAFE_ALPHABET = ascii_letters + digits + '+=,.@-'
ROLE_UNSAFE_CHARACTERS = r'\/!$%^&*()#'
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
        assert manifest.tfstate_filename == 'terraform.tfstate'
        assert not manifest.multi_region

    def test_tfstate_filename(self):
        # Given
        mock_file = MagicMock(spec=TextIOWrapper)
        mock_file.read.return_value = yaml.dump({
            'account-scheme-url': 'dummy',
            'team': 'dummy',
            'type': 'dummy',
            'tfstate-filename': 'test-tfstate-filename'
        })

        with patch(
            'cdflow_commands.config.open', new_callable=mock_open, create=True
        ) as open_:
            open_.return_value.__enter__.return_value = mock_file

            # When
            manifest = config.load_manifest()

        # Then
        assert manifest.tfstate_filename == 'test-tfstate-filename'

    def test_multi_region(self):
        # Given
        mock_file = MagicMock(spec=TextIOWrapper)
        mock_file.read.return_value = yaml.dump({
            'account-scheme-url': 'dummy',
            'team': 'dummy',
            'type': 'dummy',
            'multi-region': True
        })

        with patch(
            'cdflow_commands.config.open', new_callable=mock_open, create=True
        ) as open_:
            open_.return_value.__enter__.return_value = mock_file

            # When
            manifest = config.load_manifest()

        # Then
        assert manifest.multi_region


class TestAssumeRole(unittest.TestCase):

    @patch('cdflow_commands.config.Session')
    def test_role_is_assumed(self, MockSession):

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'

        mock_session = Mock()
        MockSession.return_value = mock_session

        mock_sts = Mock()
        user_id = 'foo'
        mock_sts.get_caller_identity.return_value = {
            u'UserId': user_id,
            'Arn': f'role/{user_id}'
        }
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
        role_name = 'test-role-name'
        region = 'us-east-99'
        account = Account('account-alias', account_id, role_name, region)
        session = config.assume_role(mock_root_session, account)

        assert session is mock_session

        mock_root_session.client.assert_called_once_with('sts')
        mock_sts.assume_role.assert_called_once_with(
            DurationSeconds=14400,
            RoleArn='arn:aws:iam::{}:role/{}'.format(account_id, role_name),
            RoleSessionName=user_id,
        )

        MockSession.assert_called_once_with(
            'dummy-access-key-id',
            'dummy-secret-access-key',
            'dummy-session-token',
            region,
        )

    @patch('cdflow_commands.config.Session')
    def test_assumed_role_has_correct_session_duration(self, MockSession):

        mock_root_session = Mock()
        mock_root_session.region_name = 'eu-west-12'

        mock_session = Mock()
        MockSession.return_value = mock_session

        mock_sts = Mock()
        user_id = 'foo'
        mock_sts.get_caller_identity.return_value = {
            u'UserId': user_id,
            'Arn': f'arn:aws:sts::123456789:assumed-role/admin/{user_id}'
        }
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
        role_name = 'test-role-name'
        region = 'us-east-99'
        account = Account('account-alias', account_id, role_name, region)
        session = config.assume_role(mock_root_session, account)

        assert session is mock_session

        mock_root_session.client.assert_called_once_with('sts')
        mock_sts.assume_role.assert_called_once_with(
            DurationSeconds=3600,
            RoleArn='arn:aws:iam::{}:role/{}'.format(account_id, role_name),
            RoleSessionName=user_id,
        )


class TestGetRoleSessionName(unittest.TestCase):

    @given(text(alphabet=ROLE_SAFE_ALPHABET, min_size=8, max_size=64))
    def test_get_session_name_from_sts(self, user_id):
        sts_client = Mock()
        sts_client.get_caller_identity.return_value = {
            u'Account': '111111111111',
            u'UserId': user_id,
            'ResponseMetadata': {
                'RetryAttempts': 0,
                'HTTPStatusCode': 200,
                'RequestId': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                'HTTPHeaders': {
                    'x-amzn-requestid': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                    'date': 'Wed, 13 Sep 2000 12:00:59 GMT',
                    'content-length': '458',
                    'content-type': 'text/xml'
                }
            },
            u'Arn': 'arn:aws:sts::111111111111:assumed-role/admin/u@domain.com'
        }

        role_session_name = config.get_role_session_name(sts_client)

        assert role_session_name == user_id

    @given(text(min_size=8, max_size=64))
    def test_get_safe_session_name(self, user_id):
        sts_client = Mock()
        sts_client.get_caller_identity.return_value = {
            u'Account': '111111111111',
            u'UserId': user_id,
            'ResponseMetadata': {
                'RetryAttempts': 0,
                'HTTPStatusCode': 200,
                'RequestId': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                'HTTPHeaders': {
                    'x-amzn-requestid': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                    'date': 'Wed, 13 Sep 2000 12:00:59 GMT',
                    'content-length': '458',
                    'content-type': 'text/xml'
                }
            },
            u'Arn': 'arn:aws:sts::111111111111:assumed-role/admin/u@domain.com'
        }

        role_session_name = config.get_role_session_name(sts_client)

        assert not re.search(config.ILLEGAL_CHARACTERS, role_session_name)


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
              "default-region": "eu-west-12",
              "terraform-backend-s3-bucket": "tfstate-bucket",
              "terraform-backend-s3-dynamodb-table": "tflocks-table"
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
            'environments', 'default-region', 'terraform-backend-s3-bucket',
            'terraform-backend-s3-dynamodb-table'
        ])

        assert sorted(account_scheme.keys()) == expected_keys

        s3_resource.Object.assert_called_once_with(bucket, key)

    @given(fixed_dictionaries({
        's3_bucket_and_key': s3_bucket_and_key(),
        'account_prefix': text(alphabet=ascii_letters+digits, min_size=1),
    }))
    def test_build_account_scheme_s3(self, fixtures):
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
              "default-region": "eu-west-12",
              "terraform-backend-s3-bucket": "tfstate-bucket",
              "terraform-backend-s3-dynamodb-table": "tflocks-table"
            }}
        '''.format(account_prefix)

        s3_resource.Object.return_value.get.return_value = {
            'Body': mock_s3_body
        }

        account_scheme, old_scheme = config.build_account_scheme_s3(
            s3_resource, s3_url, 'a-team', 'component-name',
        )

        assert not old_scheme

        assert account_scheme.release_account.id == '222222222222'
        assert sorted(account_scheme.account_ids) == \
            sorted(['111111111111', '222222222222'])

        s3_resource.Object.assert_called_once_with(
            *fixtures['s3_bucket_and_key']
        )

    @given(fixed_dictionaries({
        'filename': text(min_size=1),
        'account_prefix': text(alphabet=ascii_letters+digits, min_size=1),
    }))
    def test_build_account_scheme_file(self, fixtures):

        mock_account_scheme_file = MagicMock(spec=TextIOWrapper)

        account_prefix = fixtures['account_prefix']
        mock_account_scheme_file.read.return_value = '''
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
              "default-region": "eu-west-12",
              "terraform-backend-s3-bucket": "tfstate-bucket",
              "terraform-backend-s3-dynamodb-table": "tflocks-table"
            }}
        '''.format(account_prefix)

        with patch(
            'cdflow_commands.config.open', new_callable=mock_open, create=True
        ) as mocked_open:
            mocked_open.return_value.__enter__.return_value = \
                mock_account_scheme_file

            account_scheme = config.build_account_scheme_file(
                fixtures['filename'], 'a-team'
            )

            assert account_scheme.release_account.id == '222222222222'
            assert sorted(account_scheme.account_ids) == \
                sorted(['111111111111', '222222222222'])
            mocked_open.assert_called_once_with(fixtures['filename'])


class TestForwardAccountScheme(unittest.TestCase):

    def setUp(self):
        self.s3_resource = Mock()

        self.first_s3_bucket = 'firstbucket'
        self.first_s3_key = 'firstkey'
        self.s3_url = f's3://{self.first_s3_bucket}/{self.first_s3_key}'

        self.whitelisted_team = 'team-foo'
        self.whitelisted_component = 'my-component'

        first_mock_s3_body = Mock()
        first_mock_s3_body.read.return_value = json.dumps({
          'accounts': {
            'myorgdev': {
              'id': '222222222222',
              'role': 'admin'
            },
            'myorgprod': {
              'id': '111111111111',
              'role': 'admin'
            }
          },
          'classic-metadata-handling': True,
          'upgrade-account-scheme': {
            'new-url': 's3://second_s3_bucket/second_s3_key',
            'team-whitelist': [self.whitelisted_team],
            'component-whitelist': [self.whitelisted_component],
          },
          'release-account': 'myorgdev',
          'release-bucket': 'myorg-account-resources',
          'environments': {
            'live': 'myorgprod',
            '*': 'myorgdev'
          },
          'default-region': 'eu-west-12',
          'terraform-backend-s3-bucket': 'tfstate-bucket',
          'terraform-backend-s3-dynamodb-table': 'tflocks-table'
        })

        second_mock_s3_body = Mock()
        second_mock_s3_body.read.return_value = json.dumps({
            'accounts': {
                '{team}-release-account-{team}': {
                    'id': '123456789',
                    'role': '{team}-role-{team}',
                }
            },
            'release-bucket': '{team}-release-bucket-{team}',
            'lambda-bucket': '{team}-lambda-bucket-{team}',
            'release-account': '{team}-release-account-{team}',
            'default-region': '{team}-region-{team}',
            'environments': {},
            'terraform-backend-s3-bucket': '{team}-backend-bucket-{team}',
            'terraform-backend-s3-dynamodb-table':
            '{team}-backend-dynamo-{team}',
        })

        self.s3_resource.Object.return_value.get.side_effect = (
            {'Body': first_mock_s3_body},
            {'Body': second_mock_s3_body}
        )

    def test_forwards_to_new_account_scheme_when_new_url_listed(self):
        account_scheme, old_scheme = config.build_account_scheme_s3(
            self.s3_resource, self.s3_url, self.whitelisted_team,
            self.whitelisted_component,
        )

        assert account_scheme.release_account.id == '123456789'
        assert account_scheme.account_ids == ['123456789']

        assert old_scheme.release_account.id == '222222222222'
        assert sorted(old_scheme.account_ids) == [
            '111111111111', '222222222222',
        ]

        self.s3_resource.Object.assert_any_call(
            self.first_s3_bucket, self.first_s3_key
        )
        self.s3_resource.Object.assert_any_call(
            'second_s3_bucket', 'second_s3_key'
        )

    def test_logs_warning_message_to_user(self):
        with self.assertLogs('cdflow_commands.logger', level='WARN') as logs:
            config.build_account_scheme_s3(
                self.s3_resource, self.s3_url, self.whitelisted_team,
                self.whitelisted_component,
            )

        assert (
            'WARNING:cdflow_commands.logger:'
            'Account scheme is being upgraded. Manually update '
            'account_scheme_url in cdflow.yml to '
            's3://second_s3_bucket/second_s3_key'
        ) in logs.output

    def test_doesnt_upgrade_if_team_and_component_arent_whitelisted(self):
        account_scheme, old_scheme = config.build_account_scheme_s3(
            self.s3_resource, self.s3_url, 'not-whitelisted-team',
            'not-whitelisted-component',
        )

        assert account_scheme.release_account.id == '222222222222'
        assert sorted(account_scheme.account_ids) == \
            sorted(['111111111111', '222222222222'])

        assert not old_scheme

        self.s3_resource.Object.assert_called_once_with(
            self.first_s3_bucket, self.first_s3_key
        )

    def test_upgrades_if_just_component_is_whitelisted(self):
        account_scheme, old_scheme = config.build_account_scheme_s3(
            self.s3_resource, self.s3_url, 'not-whitelisted-team',
            self.whitelisted_component,
        )

        assert account_scheme.release_account.id == '123456789'
        assert account_scheme.account_ids == ['123456789']

        assert old_scheme.release_account.id == '222222222222'
        assert sorted(old_scheme.account_ids) == [
            '111111111111', '222222222222',
        ]

        self.s3_resource.Object.assert_any_call(
            self.first_s3_bucket, self.first_s3_key
        )
        self.s3_resource.Object.assert_any_call(
            'second_s3_bucket', 'second_s3_key'
        )

    def test_upgrades_if_just_team_is_whitelisted(self):
        account_scheme, old_scheme = config.build_account_scheme_s3(
            self.s3_resource, self.s3_url, self.whitelisted_team,
            'not-whitelisted-component',
        )

        assert account_scheme.release_account.id == '123456789'
        assert account_scheme.account_ids == ['123456789']

        assert old_scheme.release_account.id == '222222222222'
        assert sorted(old_scheme.account_ids) == [
            '111111111111', '222222222222',
        ]

        self.s3_resource.Object.assert_any_call(
            self.first_s3_bucket, self.first_s3_key
        )
        self.s3_resource.Object.assert_any_call(
            'second_s3_bucket', 'second_s3_key'
        )


class TestEnvWithAWSCredentials(unittest.TestCase):

    @given(fixed_dictionaries({
        'access_key': text(),
        'secret_key': text(),
        'token': text(),
        'region': text(),
    }))
    def test_env_with_aws_credentials(self, fixtures):

        # Given
        session = Mock()
        credentials = Mock()
        session.get_credentials.return_value = credentials
        credentials.access_key = fixtures['access_key']
        credentials.secret_key = fixtures['secret_key']
        credentials.token = fixtures['token']
        session.region_name = fixtures['region']
        env = {'existing': 'value'}

        # When
        result = config.env_with_aws_credetials(env, session)

        # Then
        self.assertEqual(env, {'existing': 'value'})
        self.assertEqual(result, {
            'existing': 'value',
            'AWS_ACCESS_KEY_ID': fixtures['access_key'],
            'AWS_SECRET_ACCESS_KEY': fixtures['secret_key'],
            'AWS_SESSION_TOKEN': fixtures['token'],
            'AWS_DEFAULT_REGION': fixtures['region'],
        })

    @given(fixed_dictionaries({
        'access_key': text(),
        'secret_key': text(),
        'region': text(),
    }))
    def test_env_with_aws_credentials_root_account(self, fixtures):

        # Given
        session = Mock()
        credentials = Mock()
        session.get_credentials.return_value = credentials
        credentials.access_key = fixtures['access_key']
        credentials.secret_key = fixtures['secret_key']
        credentials.token = None
        session.region_name = fixtures['region']
        env = {'existing': 'value'}

        # When
        result = config.env_with_aws_credetials(env, session)

        # Then
        self.assertEqual(env, {'existing': 'value'})
        self.assertEqual(result, {
            'existing': 'value',
            'AWS_ACCESS_KEY_ID': fixtures['access_key'],
            'AWS_SECRET_ACCESS_KEY': fixtures['secret_key'],
            'AWS_DEFAULT_REGION': fixtures['region'],
        })
