import unittest

from string import uppercase, lowercase, digits
from base64 import b64encode

from mock import patch, Mock
from hypothesis import given, settings
from hypothesis.strategies import text

from infra_deployer.release import Release, ReleaseConfig


IDENTIFIER_ALPHABET = uppercase + lowercase + digits + '-_'


class TestRelease(unittest.TestCase):

    @given(text(alphabet=lowercase + digits + '-', min_size=1, max_size=10))
    @given(text(alphabet=digits, min_size=12, max_size=12))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=10))
    @settings(max_examples=10)
    def test_builds_container(
        self, component_name, dev_account_id, aws_region
    ):
        config = ReleaseConfig(dev_account_id, aws_region)
        boto_ecr_client = Mock()
        release = Release(config, boto_ecr_client, component_name)
        with patch('infra_deployer.release.check_call') as check_call:
            release.create()

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                dev_account_id,
                aws_region,
                component_name,
                'dev'
            )

            check_call.assert_called_once_with(
                ['docker', 'build', '-t', image_name]
            )

    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=1, max_size=12))
    def test_tags_container_with_version(self, version):
        component_name = 'dummy-component'
        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'

        config = ReleaseConfig(dev_account_id, aws_region)
        boto_ecr_client = Mock()
        release = Release(config, boto_ecr_client, component_name, version)

        with patch('infra_deployer.release.check_call') as check_call:
            release.create()

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                dev_account_id,
                aws_region,
                component_name,
                version
            )

            check_call.assert_called_once_with(
                ['docker', 'build', '-t', image_name]
            )

    @given(text(alphabet=IDENTIFIER_ALPHABET + ':/', min_size=8, max_size=16))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    @given(text(alphabet=IDENTIFIER_ALPHABET, min_size=8, max_size=16))
    @settings(max_examples=10)
    def test_build_with_version_pushes_to_repo(
        self, proxy_endpoint, username, password
    ):
        dev_account_id = 'dummy-account-id'
        aws_region = 'dummy-region'
        component_name = 'dummy-component'
        version = '1.2.3'

        boto_ecr_client = Mock()
        boto_ecr_client.get_authorization_details.return_value = {
            'authorizationData': [
                {
                    'authorizationToken': b64encode('{}:{}'.format(
                        username, password
                    )),
                    'proxyEndpoint': proxy_endpoint
                }
            ]
        }

        config = ReleaseConfig(dev_account_id, aws_region)
        release = Release(config, boto_ecr_client, component_name, version)

        with patch('infra_deployer.release.check_call') as check_call:
            release.create()

            boto_ecr_client.describe_repositories.assert_called_once_with(
                repositoryNames=[component_name]
            )

            boto_ecr_client.get_authorization_details.assert_called_once()

            check_call.assert_any_call([
                'docker', 'login',
                '-u', username, '-p', password, proxy_endpoint
            ])
