import unittest

from string import uppercase, lowercase, digits

from mock import patch
from hypothesis import given
from hypothesis.strategies import text

from infra_deployer.release import Release


COMPONENT_NAME_CHARACTERS = uppercase+lowercase+digits+'-_'


class TestRelease(unittest.TestCase):

    @given(text(alphabet=COMPONENT_NAME_CHARACTERS, min_size=1, max_size=10))
    def test_builds_container(self, component_name):
        release = Release(component_name)
        with patch('infra_deployer.release.check_call') as check_call:
            release.create()

            image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
                'dummy-dev-account-id',
                'dummy-region',
                component_name,
                'dev'
            )

            check_call.assert_called_once_with(
                ['docker', 'build', '-t', image_name]
            )
