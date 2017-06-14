import unittest

from cdflow_commands.release import Release
from mock import MagicMock, Mock, mock_open, patch, ANY
from io import BytesIO, TextIOWrapper
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
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.getcwd')
    @patch('cdflow_commands.release.mkdir')
    def test_terraform_modules_fetched(
        self, mkdir, getcwd, TemporaryDirectory, _, check_call, _1, _2
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = []
        release = Release(
            platform_config_path=ANY,
            commit='dummy',
            version='dummy-version',
            component_name='dummy-component',
        )
        temp_dir = 'test-tmp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        getcwd.return_value = '/cwd'

        # When
        with BytesIO() as f:
            release.create(release_plugin, f)

        # Then
        mkdir.assert_called_once_with('{}/{}-{}'.format(
            temp_dir, 'dummy-component', 'dummy-version'
        ))
        check_call.assert_any_call([
            'terraform', 'get', '/cwd/infra',
        ], cwd='{}/{}-{}'.format(temp_dir, 'dummy-component', 'dummy-version'))

    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.TemporaryDirectory')
    def test_platform_config_added_to_release_bundle(
        self, TemporaryDirectory, copytree, _, _1, _2, _3
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = []
        platform_config_path = 'test-platform-config-path'
        release = Release(
            platform_config_path, commit='dummy',
            version='dummy-version', component_name='dummy-component',
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        # When
        with BytesIO() as f:
            release.create(release_plugin, f)

        # Then
        copytree.assert_any_call(
            platform_config_path, '{}/{}-{}/platform-config'.format(
                temp_dir, 'dummy-component', 'dummy-version'
            )
        )

    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    def test_release_added_to_release_bundle(
        self, mock_open, TemporaryDirectory, _, _1, _2, _3
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
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        mock_file = MagicMock(spec=TextIOWrapper)
        mock_open.return_value.__enter__.return_value = mock_file

        # When
        with BytesIO() as f:
            release.create(release_plugin, f)

        # Then
        release_plugin.create.assert_called_once_with()
        mock_open.assert_called_once_with(
            '{}/{}-{}/release.json'.format(
                temp_dir, component_name, version
            ), 'w'
        )
        mock_file.write.assert_called_once_with(json.dumps({
            'release': {
                'commit': commit,
                'version': version,
                'component-name': component_name,
                'artefacts': artefacts
            }
        }))

    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    def test_release_bundle_added_to_archive(
        self, mock_open, TemporaryDirectory, make_archive, _, _1, _2
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
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        mock_file = MagicMock(spec=TextIOWrapper)
        mock_open.return_value.__enter__.return_value = mock_file

        # When
        with BytesIO() as f:
            release.create(release_plugin, f)

        # Then
        make_archive.assert_called_once_with(
            '{}/{}-{}'.format(temp_dir, component_name, version),
            'zip',
            temp_dir,
            '{}-{}'.format(component_name, version),
        )
