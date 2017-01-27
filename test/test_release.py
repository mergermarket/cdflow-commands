import unittest

from string import uppercase, lowercase, digits

from mock import patch
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
        release = Release(config, component_name)
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
        release = Release(config, component_name, version)

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
