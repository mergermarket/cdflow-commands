import json
import unittest
from base64 import b64encode
from string import ascii_letters, ascii_lowercase, digits
from subprocess import CalledProcessError

from botocore.exceptions import ClientError
from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.plugins.ecs import Release, ReleaseConfig
from hypothesis import assume, given, settings
from hypothesis.strategies import text
from mock import Mock, patch

IDENTIFIER_ALPHABET = ascii_letters + digits + '-_'


class TestRelease(unittest.TestCase):

    def setUp(self):
        self._boto_ecr_client = Mock()
        self._boto_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': b64encode('{}:{}'.format(
                        'dummy-username', 'dummy-password'
                    ).encode('utf-8')),
                    'proxyEndpoint': 'dummy-proxy-endpoint'
                }
            ]
        }

    @given(text(
        alphabet=ascii_lowercase + digits + '-', min_size=1, max_size=10
    ))
    @given(text(alphabet=digits, min_size=12, max_size=12))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=10))
    @settings(max_examples=10)
    def test_builds_container(
        self, component_name, dev_account_id, aws_region
    ):
        config = ReleaseConfig(dev_account_id, 'dummy-account-id', aws_region)
        release = Release(config, self._boto_ecr_client, component_name)
        with patch('cdflow_commands.plugins.ecs.check_call') as check_call:
            release.create()

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                dev_account_id,
                aws_region,
                component_name,
                'dev'
            )

            check_call.assert_called_once_with(
                ['docker', 'build', '-t', image_name, '.']
            )

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=12))
    def test_tags_container_with_version(self, version):
        component_name = 'dummy-component'
        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'

        config = ReleaseConfig(dev_account_id, 'dummy-account-id', aws_region)
        release = Release(
            config, self._boto_ecr_client, component_name, version
        )

        with patch('cdflow_commands.plugins.ecs.check_call') as check_call:
            release.create()

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                dev_account_id,
                aws_region,
                component_name,
                version
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
        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'
        component_name = 'dummy-component'
        version = '1.2.3'

        boto_ecr_client = Mock()
        boto_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': b64encode('{}:{}'.format(
                        username, password
                    ).encode('utf-8')),
                    'proxyEndpoint': proxy_endpoint
                }
            ]
        }

        config = ReleaseConfig(dev_account_id, 'dummy-account-id', aws_region)
        release = Release(config, boto_ecr_client, component_name, version)

        with patch('cdflow_commands.plugins.ecs.check_call') as check_call:
            release.create()

            boto_ecr_client.describe_repositories.assert_called_once_with(
                repositoryNames=[component_name]
            )

            boto_ecr_client.get_authorization_token.assert_called_once()

            check_call.assert_any_call([
                'docker', 'login',
                '-u', username, '-p', password, proxy_endpoint
            ])

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                dev_account_id,
                aws_region,
                component_name,
                version
            )

            check_call.assert_any_call([
                'docker', 'push', image_name
            ])

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    def test_ecr_repo_created_when_it_does_not_exist(self, component_name):
        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'
        version = '1.2.3'

        boto_ecr_client = Mock()
        boto_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': b64encode('{}:{}'.format(
                        'dummy-username', 'dummy-password'
                    ).encode('utf-8')),
                    'proxyEndpoint': 'dummy-proxy-endpoint'
                }
            ]
        }

        boto_ecr_client.describe_repositories.side_effect = ClientError(
            {'Error': {'Code': 'RepositoryNotFoundException'}},
            None
        )

        config = ReleaseConfig(dev_account_id, 'dummy-account-id', aws_region)
        release = Release(
            config, boto_ecr_client, component_name, version
        )

        with patch('cdflow_commands.plugins.ecs.check_call'):
            release.create()

            boto_ecr_client.create_repository.assert_called_once_with(
                repositoryName=component_name
            )

    @given(text(alphabet=ascii_letters, min_size=8, max_size=16))
    def test_exception_re_raised(self, error_code):
        assume(error_code != 'RepositoryNotFoundException')

        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'
        component_name = 'dummy-component'
        version = '1.2.3'

        self._boto_ecr_client.describe_repositories.side_effect = ClientError(
            {'Error': {'Code': error_code}},
            None
        )

        config = ReleaseConfig(dev_account_id, 'dummy-account-id', aws_region)
        release = Release(
            config, self._boto_ecr_client, component_name, version
        )

        with patch('cdflow_commands.plugins.ecs.check_call'):
            self.assertRaises(ClientError, release.create)

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    @given(text(alphabet=digits, min_size=12, max_size=12))
    @settings(max_examples=50)
    def test_policy_set_on_repo(self, prod_account_id, component_name):
        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'
        version = '1.2.3'

        boto_ecr_client = Mock()
        boto_ecr_client.get_authorization_token.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': b64encode('{}:{}'.format(
                        'dummy-username', 'dummy-password'
                    ).encode('utf-8')),
                    'proxyEndpoint': 'dummy-proxy-endpoint'
                }
            ]
        }

        config = ReleaseConfig(
            dev_account_id,
            prod_account_id,
            aws_region
        )
        release = Release(
            config, boto_ecr_client, component_name, version
        )

        with patch('cdflow_commands.plugins.ecs.check_call'):
            release.create()

            boto_ecr_client.set_repository_policy.assert_called_once_with(
                repositoryName=component_name,
                policyText=json.dumps({
                    'Version': '2008-10-17',
                    'Statement': [{
                        'Sid': 'allow production',
                        'Effect': 'Allow',
                        'Principal': {
                            'AWS': 'arn:aws:iam::{}:root'.format(
                                prod_account_id
                            )
                        },
                        'Action': [
                            'ecr:GetDownloadUrlForLayer',
                            'ecr:BatchGetImage',
                            'ecr:BatchCheckLayerAvailability'
                        ]
                    }]
                }, sort_keys=True)
            )

    @patch('cdflow_commands.plugins.ecs.check_call')
    @patch('cdflow_commands.plugins.ecs.path')
    def test_runs_on_docker_build_script_if_one_is_present(
        self, os_path, check_call
    ):
        # Given
        dev_account_id = '123456789'
        aws_region = 'eu-west-12'
        component_name = 'dummy-component'
        version = '1.2.3'

        def _mock_exists(path):
            if path == './on-docker-build':
                return True
            return False

        os_path.exists = _mock_exists

        config = ReleaseConfig(
            dev_account_id,
            '987654321',
            aws_region
        )
        release = Release(
            config, self._boto_ecr_client, component_name, version
        )

        # When
        release.create()

        # Then
        check_call.assert_any_call([
            './on-docker-build',
            '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                dev_account_id,
                aws_region,
                component_name,
                version
            )
        ])

    @patch('cdflow_commands.plugins.ecs.check_call')
    @patch('cdflow_commands.plugins.ecs.path')
    def test_error_from_on_docker_build_prevents_push(
        self, os_path, check_call
    ):
        # Given
        dev_account_id = '123456789'
        aws_region = 'eu-west-12'
        component_name = 'dummy-component'
        version = '1.2.3'

        def _error_on_docker_build(command):
            if command[0] == Release.ON_BUILD_HOOK:
                raise CalledProcessError(1, ['./on-docker-build'])

        os_path.exists.return_value = True
        check_call.side_effect = _error_on_docker_build

        config = ReleaseConfig(
            dev_account_id,
            '987654321',
            aws_region
        )
        release = Release(
            config, self._boto_ecr_client, component_name, version
        )

        # When
        self.assertRaises(Exception, release.create)

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
        dev_account_id = '123456789'
        aws_region = 'eu-west-12'
        component_name = 'dummy-component'
        version = '1.2.3'

        def _error_on_docker_build(command):
            if command[0] == Release.ON_BUILD_HOOK:
                raise CalledProcessError(1, ['./on-docker-build'])

        os_path.exists.return_value = True
        check_call.side_effect = _error_on_docker_build

        config = ReleaseConfig(
            dev_account_id,
            '987654321',
            aws_region
        )
        release = Release(
            config, self._boto_ecr_client, component_name, version
        )

        # When
        self.assertRaises(UserFacingError, release.create)
