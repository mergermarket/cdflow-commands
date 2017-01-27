import unittest

from mock import patch

from infra_deployer.release import Release


class TestRelease(unittest.TestCase):

    @patch('infra_deployer.release.check_call')
    def test_builds_container(self, check_call):
        release = Release('dummy-component')
        release.create()

        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            'dummy-dev-account-id',
            'dummy-region',
            'dummy-component',
            'dev'
        )

        check_call.assert_called_once_with(
            ['docker', 'build', '-t', image_name]
        )
