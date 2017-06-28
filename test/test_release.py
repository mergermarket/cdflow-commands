from contextlib import ExitStack
from io import TextIOWrapper
import json
from string import ascii_letters, digits
import unittest

from hypothesis import given
from hypothesis.strategies import dictionaries, fixed_dictionaries, text
from mock import MagicMock, Mock, mock_open, patch, ANY

from cdflow_commands.release import Release


ALNUM = ascii_letters + digits


class TestRelease(unittest.TestCase):

    @given(text())
    def test_version(self, version):
        # Given
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_path=ANY, commit=ANY, version=version,
            component_name=ANY, team=ANY
        )

        # When/Then
        assert release.version == version

    @given(text())
    def test_component_name(self, component_name):
        # Given
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_path=ANY, commit=ANY, version=ANY,
            component_name=component_name, team=ANY
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
        release_plugin.create.return_value = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_path=ANY,
            commit='dummy',
            version='dummy-version',
            component_name='dummy-component',
            team='dummy-team',
        )
        temp_dir = 'test-tmp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        getcwd.return_value = '/cwd'

        # When
        release.create_archive(release_plugin)

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
        release_plugin.create.return_value = {}
        platform_config_path = 'test-platform-config-path'
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_path=platform_config_path, commit='dummy',
            version='dummy-version', component_name='dummy-component',
            team='dummy-team',
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        # When
        release.create_archive(release_plugin)

        # Then
        copytree.assert_any_call(
            platform_config_path, '{}/{}-{}/platform-config'.format(
                temp_dir, 'dummy-component', 'dummy-version'
            )
        )

    @given(fixed_dictionaries({
        'plugin_data': dictionaries(keys=text(), values=text()),
        'commit': text(),
        'version': text(alphabet=ALNUM),
        'component_name': text(alphabet=ALNUM),
        'team': text(),
        'temp_dir': text(),
    }))
    def test_release_added_to_release_bundle(self, fixtures):
        # Given
        component_name = fixtures['component_name']
        commit = fixtures['commit']
        version = fixtures['version']
        team = fixtures['team']
        plugin_data = fixtures['plugin_data']
        temp_dir = fixtures['temp_dir']

        release_plugin = Mock()
        release_plugin.create.return_value = plugin_data

        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_path='platform-config',
            commit=commit,
            version=version,
            component_name=component_name,
            team=team
        )

        with ExitStack() as stack:
            stack.enter_context(patch('cdflow_commands.release.mkdir'))
            stack.enter_context(patch('cdflow_commands.release.check_call'))
            stack.enter_context(patch('cdflow_commands.release.copytree'))
            stack.enter_context(patch('cdflow_commands.release.make_archive'))
            TemporaryDirectory = stack.enter_context(
                patch('cdflow_commands.release.TemporaryDirectory')
            )
            _open = stack.enter_context(
                patch(
                    'cdflow_commands.release.open',
                    new_callable=mock_open, create=True
                )
            )

            TemporaryDirectory.return_value.__enter__.return_value = temp_dir

            mock_file = MagicMock(spec=TextIOWrapper)
            _open.return_value.__enter__.return_value = mock_file

            base_release_metadata = {
                'commit': commit,
                'version': version,
                'component-name': component_name,
                'team': team,
            }

            # When
            release.create_archive(release_plugin)

            # Then
            release_plugin.create.assert_called_once_with()
            _open.assert_called_once_with(
                '{}/{}-{}/release.json'.format(
                    temp_dir, component_name, version
                ), 'w'
            )
            mock_file.write.assert_called_once_with(json.dumps({
                'release': dict(**base_release_metadata, **plugin_data)
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
        release_plugin.create.return_value = {}

        commit = 'test-git-commit'
        version = 'test-version'
        component_name = 'test-component'
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_path='test-platform-config-path',
            commit=commit,
            version=version,
            component_name=component_name,
            team='dummy-team',
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        mock_file = MagicMock(spec=TextIOWrapper)
        mock_open.return_value.__enter__.return_value = mock_file

        make_archive_result = '/path/to/dummy.zip'
        make_archive.return_value = make_archive_result

        # When
        path_to_archive = release.create_archive(release_plugin)

        # Then
        assert path_to_archive == make_archive_result
        make_archive.assert_called_once_with(
            '{}/{}-{}'.format(temp_dir, component_name, version),
            'zip',
            temp_dir,
            '{}-{}'.format(component_name, version),
        )

    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.open', new_callable=mock_open, create=True)
    def test_create_uploads_archive(
        self, mock_open, TemporaryDirectory, make_archive, _, _1, _2
    ):
        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}

        commit = 'test-git-commit'
        version = 'test-version'
        component_name = 'test-component'
        release_bucket = 'test-release-bucket'
        mock_session = Mock()
        release = Release(
            boto_session=mock_session,
            release_bucket=release_bucket,
            platform_config_path='test-platform-config-path',
            commit=commit,
            version=version,
            component_name=component_name,
            team='dummy-team',
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        mock_file = MagicMock(spec=TextIOWrapper)
        mock_open.return_value.__enter__.return_value = mock_file

        make_archive_result = '/path/to/dummy.zip'
        make_archive.return_value = make_archive_result

        # When
        release.create(release_plugin)

        # Then
        Object = mock_session.resource.return_value.Object
        Object.return_value.upload_file.assert_called_once_with(
            make_archive_result
        )
        Object.assert_called_once_with(
            release_bucket, '{}/{}-{}.zip'.format(
                component_name, component_name, version
            )
        )
