import unittest
import json
from base64 import b64encode
from string import ascii_letters, digits
from subprocess import CalledProcessError

from botocore.exceptions import ClientError
from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.plugins.ecs import ReleasePlugin
from cdflow_commands.account import AccountScheme
from hypothesis import assume, given, settings
from hypothesis.strategies import text, lists
from mock import Mock, patch

from test.test_account import account

IDENTIFIER_ALPHABET = ascii_letters + digits + '-_'


class TestRelease(unittest.TestCase):

    def _set_mock_get_authorization_token(
        self, username='dummy-username', password='dummy-password',
        proxy_endpoint='dummy-proxy-endpoint'
    ):
        self._ecr_client.get_authorization_token = Mock()
        self._ecr_client.get_authorization_token.return_value = {
            'authorizationData': [{
                'authorizationToken': b64encode(
                    '{}:{}'.format(username, password).encode('utf-8')
                ),
                'proxyEndpoint': proxy_endpoint
            }]
        }

    def setUp(self):
        boto_session = Mock()
        self._ecr_client = Mock()
        boto_session.client.return_value = self._ecr_client
        self._set_mock_get_authorization_token()
        self._release = Mock()

        self._release.boto_session = boto_session

        self._component_name = 'dummy-component'
        self._release.component_name = self._component_name

        self._version = '1.2.3'
        self._release.version = self._version

        self._region = 'dummy-region'
        self._account_id = 'dummy-account-id'
        account_scheme = AccountScheme.create({
            'accounts': {
                'dummy': {
                    'id': self._account_id,
                    'role': 'dummy'
                }
            },
            'release-account': 'dummy',
            'default-region': self._region,
        })

        self._plugin = ReleasePlugin(self._release, account_scheme)

    @given(text(alphabet=digits, min_size=12, max_size=12))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=10))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=10))
    @settings(max_examples=10)
    def test_builds_container(
        self, component_name, region, account_id
    ):
        # Given
        release = self._release
        release.component_name = component_name
        release.version = None

        account_scheme = AccountScheme.create({
            'accounts': {
                'dummy': {
                    'id': account_id,
                    'role': 'dummy'
                }
            },
            'release-account': 'dummy',
            'default-region': region,
        })

        plugin = ReleasePlugin(release, account_scheme)

        with patch('cdflow_commands.plugins.ecs.check_call') as check_call:
            # When
            plugin.create()

            # Then
            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                account_id, region, component_name, 'dev'
            )

            check_call.assert_called_once_with(
                ['docker', 'build', '-t', image_name, '.']
            )

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=12))
    def test_tags_container_with_version(self, version):
        # Given
        release = self._release
        release.version = version

        with patch('cdflow_commands.plugins.ecs.check_call') as check_call:
            # When
            self._plugin.create()

            # Then
            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                self._account_id, self._region, self._component_name, version
            )

            check_call.assert_any_call(
                ['docker', 'build', '-t', image_name, '.']
            )

    @given(text(alphabet=IDENTIFIER_ALPHABET + ':/', min_size=8, max_size=16))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    @settings(max_examples=10)
    def test_build_with_version_pushes_to_ecr_repo(
        self, proxy_endpoint, username, password
    ):
        # Given
        self._ecr_client.describe_repositories = Mock()
        self._set_mock_get_authorization_token(
            username, password, proxy_endpoint
        )

        with patch('cdflow_commands.plugins.ecs.check_call') as check_call:
            # When
            self._plugin.create()

            # Then
            self._ecr_client.describe_repositories.assert_called_once_with(
                repositoryNames=[self._component_name]
            )

            self._ecr_client.get_authorization_token.assert_called_once()

            check_call.assert_any_call([
                'docker', 'login',
                '-u', username, '-p', password, proxy_endpoint
            ])

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                self._account_id, self._region, self._component_name,
                self._version
            )

            check_call.assert_any_call([
                'docker', 'push', image_name
            ])

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    def test_ecr_repo_created_when_it_does_not_exist(self, component_name):
        # Given
        self._release.component_name = component_name
        self._ecr_client.create_repository = Mock()
        self._ecr_client.describe_repositories.side_effect = ClientError(
            {'Error': {'Code': 'RepositoryNotFoundException'}},
            None
        )

        with patch('cdflow_commands.plugins.ecs.check_call'):
            # When
            self._plugin.create()

            # Then
            self._ecr_client.create_repository.assert_called_once_with(
                repositoryName=component_name
            )

    @given(text(alphabet=ascii_letters, min_size=8, max_size=16))
    def test_exception_re_raised(self, error_code):
        # Given
        assume(error_code != 'RepositoryNotFoundException')

        self._ecr_client.describe_repositories.side_effect = ClientError(
            {'Error': {'Code': error_code}},
            None
        )

        with patch('cdflow_commands.plugins.ecs.check_call'):
            # When & Then
            self.assertRaises(ClientError, self._plugin.create)

    def test_no_policy_with_no_extra_deploy_accounts(self):
        # Given
        self._release.deploy_account_ids = [
            self._account_id
        ]
        self._ecr_client.set_repository_policy = Mock()

        with patch('cdflow_commands.plugins.ecs.check_call'):
            # When
            self._plugin.create()

            # Then
            assert not self._ecr_client.set_repository_policy.called

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    @given(lists(
        elements=account(), min_size=2, max_size=4,
        unique_by=lambda account: account['alias']
    ))
    @settings(max_examples=50)
    def test_policy_set_on_repo(self, component_name, accounts):
        # unique_by above only supports a single hashable type, so we have to
        # ensure uniqueness of account ids here - this is needed because the
        # under test should only creates one statement for each unique account
        # id
        account_ids = [account['id'] for account in accounts]
        assume(len(set(account_ids)) == len(account_ids))

        self._release.component_name = component_name
        account_scheme = AccountScheme.create({
            'accounts': {
                account['alias']: {
                    'id': account['id'],
                    'role': account['role']
                }
                for account in accounts
            },
            'release-account': accounts[0]['alias'],
            'default-region': self._region,
        })
        plugin = ReleasePlugin(self._release, account_scheme)
        self._ecr_client.set_repository_policy = Mock()

        with patch('cdflow_commands.plugins.ecs.check_call'):
            plugin.create()

            expected_account_ids = sorted(
                [account['id'] for account in accounts[1:]]
            )
            self._ecr_client.set_repository_policy.assert_called_once_with(
                repositoryName=component_name,
                policyText=json.dumps({
                    'Version': '2008-10-17',
                    'Statement': [{
                        'Sid': 'allow {}'.format(account_id),
                        'Effect': 'Allow',
                        'Principal': {
                            'AWS': 'arn:aws:iam::{}:root'.format(account_id)
                        },
                        'Action': [
                            'ecr:GetDownloadUrlForLayer',
                            'ecr:BatchGetImage',
                            'ecr:BatchCheckLayerAvailability'
                        ]
                    } for account_id in expected_account_ids]
                }, sort_keys=True)
            )

    @patch('cdflow_commands.plugins.ecs.check_call')
    @patch('cdflow_commands.plugins.ecs.path')
    def test_runs_on_docker_build_script_if_one_is_present(
        self, os_path, check_call
    ):
        # Given
        def _mock_exists(path):
            if path == './on-docker-build':
                return True
            return False

        os_path.exists = _mock_exists

        # When
        self._plugin.create()

        # Then
        check_call.assert_any_call([
            './on-docker-build',
            '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                self._account_id,
                self._region,
                self._component_name,
                self._version
            )
        ])

    @patch('cdflow_commands.plugins.ecs.check_call')
    @patch('cdflow_commands.plugins.ecs.path')
    def test_error_from_on_docker_build_prevents_push(
        self, os_path, check_call
    ):
        # Given
        def _error_on_docker_build(command):
            if command[0] == ReleasePlugin.ON_BUILD_HOOK:
                raise CalledProcessError(1, ['./on-docker-build'])

        os_path.exists.return_value = True
        check_call.side_effect = _error_on_docker_build

        # When
        self.assertRaises(Exception, self._plugin.create)

        # Then
        call_arguments = [call[1][0] for call in check_call.mock_calls]
        for arguments in call_arguments:
            assert ['docker', 'push'] != arguments[:2]

    @patch('cdflow_commands.plugins.ecs.check_call')
    @patch('cdflow_commands.plugins.ecs.path')
    def test_error_from_on_docker_build_becomes_a_user_error(
        self, os_path, check_call
    ):
        # Given
        def _error_on_docker_build(command):
            if command[0] == ReleasePlugin.ON_BUILD_HOOK:
                raise CalledProcessError(1, ['./on-docker-build'])

        os_path.exists.return_value = True
        check_call.side_effect = _error_on_docker_build

        # When & Then
        self.assertRaises(UserFacingError, self._plugin.create)
