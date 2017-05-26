import unittest

from cdflow_commands.release import Release
from mock import patch
from os import getcwd


class TestTerraformModulesRetrieved(unittest.TestCase):

    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copyfile')
    @patch('cdflow_commands.release.mkdtemp')
    def test_terraform_modules_fetched(self, mkdtemp, _, check_call):

        # Given
        release = Release(platform_config_path='test-platform-config-path')
        temp_dir = 'test-tmp-dir'
        mkdtemp.side_effect = [temp_dir]

        # When
        release.create()

        # Then
        check_call.assert_any_call([
            'terraform', 'get', '{}/infra'.format(getcwd())
        ], cwd=temp_dir)

    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copyfile')
    @patch('cdflow_commands.release.mkdtemp')
    def test_platform_config_added_to_release_bundle(
        self, mkdtemp, copyfile, _
    ):

        # Given
        release = Release(platform_config_path='test-platform-config-path')
        temp_dir = 'test-temp-dir'
        mkdtemp.side_effect = [temp_dir]

        # When
        release.create()

        # Then
        copyfile.assert_any_call(
            'test-platform-config-path/dev.json',
            '{}/dev.json'.format(temp_dir)
        )
        copyfile.assert_any_call(
            'test-platform-config-path/prod.json',
            '{}/prod.json'.format(temp_dir)
        )
