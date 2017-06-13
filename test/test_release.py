import unittest

from cdflow_commands.release import Release
from os import getcwd
from mock import MagicMock, Mock, mock_open, patch, ANY
from io import TextIOWrapper
import json

from hypothesis import given
from hypothesis.strategies import text


class TestRelease(unittest.TestCase):

    @given(text())
    def test_version(self, version):
        # Given
        release = Release(
            platform_config_path=ANY, commit=ANY, version=version,
            component_name=ANY
        )

        # When/Then
        assert release.version == version

    @given(text())
    def test_component_name(self, component_name):
        # Given
        release = Release(
            platform_config_path=ANY, commit=ANY, version=ANY,
            component_name=component_name
        )

        # When/Then
        assert release.component_name == component_name


class TestReleaseArchive(unittest.TestCase):

    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copyfile')
    @patch('cdflow_commands.release.mkdtemp')
    def test_terraform_modules_fetched(self, mkdtemp, _, check_call, _1):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = []
        release = Release(
            platform_config_path=ANY,
            commit='dummy', version='dummy', component_name='dummy',
        )
        temp_dir = 'test-tmp-dir'
        mkdtemp.side_effect = [temp_dir]

        # When
        release.create(release_plugin)

        # Then
        check_call.assert_any_call([
            'terraform', 'get', '{}/infra'.format(getcwd())
        ], cwd=temp_dir)

    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copyfile')
    @patch('cdflow_commands.release.mkdtemp')
    def test_platform_config_added_to_release_bundle(
        self, mkdtemp, copyfile, _, _1
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = []
        platform_config_path = 'test-platform-config-path'
        release = Release(
            platform_config_path,
            commit='dummy', version='dummy', component_name='dummy',
        )
        temp_dir = 'test-temp-dir'
        mkdtemp.side_effect = [temp_dir]

        # When
        release.create(release_plugin)

        # Then
        copyfile.assert_any_call(
            '{}/dev.json'.format(platform_config_path),
            '{}/dev.json'.format(temp_dir)
        )
        copyfile.assert_any_call(
            '{}/prod.json'.format(platform_config_path),
            '{}/prod.json'.format(temp_dir)
        )

    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copyfile')
    @patch('cdflow_commands.release.mkdtemp')
    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    def test_release_added_to_archive(
        self, mock_open, mkdtemp, _, _1
    ):

        # Given
        release_plugin = Mock()
        artefacts = [
            {'test': 'artefact'}
        ]
        release_plugin.create.return_value = artefacts

        commit = 'test-git-commit'
        version = 'test-version'
        component_name = 'test-component'
        release = Release(
            platform_config_path='test-platform-config-path',
            commit=commit,
            version=version,
            component_name=component_name,
        )
        temp_dir = 'test-temp-dir'
        mkdtemp.side_effect = [temp_dir]
        mock_file = MagicMock(spec=TextIOWrapper)
        mock_open.return_value.__enter__.return_value = mock_file

        # When
        release.create(release_plugin)

        # Then
        release_plugin.create.assert_called_once_with()
        mock_open.assert_called_once_with(
            '{}/release.json'.format(temp_dir), 'w'
        )
        mock_file.write.assert_called_once_with(json.dumps({
            'release': {
                'commit': commit,
                'version': version,
                'component-name': component_name,
                'artefacts': artefacts
            }
        }))
