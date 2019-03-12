from contextlib import ExitStack
import datetime
from io import TextIOWrapper
import json
from string import ascii_letters, digits
import unittest
from zipfile import ZipInfo

from hypothesis import given, settings
from hypothesis.strategies import dictionaries, fixed_dictionaries, lists, text
from mock import MagicMock, Mock, patch, ANY
from moto import mock_s3
from freezegun import freeze_time
import boto3

from cdflow_commands.release import (
    fetch_release, find_latest_release_version, Release,
)
from cdflow_commands.constants import ACCOUNT_SCHEME_FILE


ALNUM = ascii_letters + digits


class TestRelease(unittest.TestCase):

    @given(text())
    def test_version(self, version):
        # Given
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=[ANY],
            release_data=["1=1"], commit=ANY, version=version,
            component_name=ANY, team=ANY,
            account_scheme=account_scheme,
            multi_region=False,
        )

        # When/Then
        assert release.version == version

    @given(text())
    def test_component_name(self, component_name):
        # Given
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=[ANY],
            release_data=["1=1"], commit=ANY, version=ANY,
            component_name=component_name, team=ANY,
            account_scheme=account_scheme,
            multi_region=False,
        )

        # When/Then
        assert release.component_name == component_name


@patch.dict(
    'cdflow_commands.release.os.environ',
    values={'CDFLOW_IMAGE_DIGEST': 'hash'}
)
class TestReleaseArchive(unittest.TestCase):

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.open')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.getcwd')
    @patch('cdflow_commands.release.mkdir')
    def test_terraform_is_initialised(
        self, mkdir, getcwd, TemporaryDirectory, _, check_call, _1, _2, _3
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=[ANY],
            release_data=["1=1"],
            commit='dummy',
            version='dummy-version',
            component_name='dummy-component',
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
        )
        temp_dir = 'test-tmp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        getcwd.return_value = '/cwd'

        # When
        release.create(release_plugin)

        # Then
        mkdir.assert_called_once_with('{}/{}-{}'.format(
            temp_dir, 'dummy-component', 'dummy-version'
        ))
        check_call.assert_any_call([
            'terraform', 'init', '/cwd/infra',
        ], cwd='{}/{}-{}'.format(temp_dir, 'dummy-component', 'dummy-version'))

    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.open')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.copyfile')
    @patch('cdflow_commands.release.isfile')
    @patch('cdflow_commands.release.makedirs')
    @patch('cdflow_commands.release.isdir')
    @patch('cdflow_commands.release.listdir')
    @patch('cdflow_commands.release.TemporaryDirectory')
    def test_platform_config_added_to_release_bundle(
        self, TemporaryDirectory, listdir, isdir, makedirs, isfile,
        copyfile, _1, _2, _3, _4, _5
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}
        platform_config_paths = [
            'test-platform-config-path-a',
            'test-platform-config-path-b',
        ]
        release_data = ["ami_id=ami-a12345", "foo=bar"]
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=platform_config_paths,
            release_data=release_data, commit='dummy',
            version='dummy-version', component_name='dummy-component',
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir
        dirs = {
            "test-platform-config-path-a": ["alias1", "alias2"],
            "test-platform-config-path-b": ["alias3"],
            "test-platform-config-path-a/alias1": ["1.json", "2.json"],
            "test-platform-config-path-a/alias2": ["3.json"],
            "test-platform-config-path-b/alias3": ["4.json", "5.json"],
        }
        listdir.side_effect = lambda d: dirs[d]
        isdir.side_effect = lambda d: d in dirs
        isfile.return_value = True

        # When
        release.create(release_plugin)

        # Then
        copyfile.assert_any_call(
            'test-platform-config-path-a/alias1/1.json',
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias1/1.json',
        )
        copyfile.assert_any_call(
            'test-platform-config-path-a/alias1/2.json',
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias1/2.json',
        )
        copyfile.assert_any_call(
            'test-platform-config-path-a/alias2/3.json',
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias2/3.json',
        )
        copyfile.assert_any_call(
            'test-platform-config-path-b/alias3/4.json',
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias3/4.json',
        )
        copyfile.assert_any_call(
            'test-platform-config-path-b/alias3/5.json',
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias3/5.json',
        )
        makedirs.assert_any_call(
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias1',
            exist_ok=True
        )
        makedirs.assert_any_call(
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias2',
            exist_ok=True
        )
        makedirs.assert_any_call(
            'test-temp-dir/dummy-component-dummy-version/'
            'platform-config/alias3',
            exist_ok=True
        )

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.open')
    @patch('cdflow_commands.release.TemporaryDirectory')
    def test_account_scheme_added_to_release_bundle(
        self, TemporaryDirectory, _open, _1, _2, _3, _4, _5
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}
        platform_config_paths = ['test-platform-config-path']
        release_data = ["ami_id=ami-a12345", "foo=bar"]
        account_scheme = Mock()
        account_scheme.raw_scheme = {"test": "scheme"}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=platform_config_paths,
            release_data=release_data, commit='dummy',
            version='dummy-version', component_name='dummy-component',
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        mock_account_scheme = MagicMock(spec=TextIOWrapper)
        mock_account_scheme_open = MagicMock()
        mock_account_scheme_open.__enter__.return_value = mock_account_scheme

        generic_mock_open = MagicMock()
        generic_mock_open.__enter__.return_value = \
            MagicMock(spec=TextIOWrapper)

        _open.side_effect = lambda filename, _: \
            mock_account_scheme_open \
            if filename.endswith(ACCOUNT_SCHEME_FILE) \
            else generic_mock_open

        # When
        release.create(release_plugin)

        # Then
        _open.assert_any_call('test-temp-dir/{}-{}/{}'.format(
            'dummy-component', 'dummy-version', ACCOUNT_SCHEME_FILE
        ), 'w')
        mock_account_scheme.write.assert_called_once_with(json.dumps({
            "test": "scheme"
        }))

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.open')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.os.path')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.TemporaryDirectory')
    def test_app_config_added_to_release_bundle(
        self, TemporaryDirectory, copytree, patch_path, _, _1, _2, _3, _4
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}
        platform_config_paths = ['test-platform-config-path']
        release_data = ["ami_id=ami-a12345", "foo=bar"]
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=platform_config_paths,
            release_data=release_data,
            commit='dummy',
            version='dummy-version', component_name='dummy-component',
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir
        patch_path.exists.return_value = True

        # When
        release.create(release_plugin)

        # Then
        copytree.assert_any_call(
            'config', '{}/{}-{}/config'.format(
                temp_dir, 'dummy-component', 'dummy-version'
            )
        )

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.open')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.os.path')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.TemporaryDirectory')
    def test_app_config_add_skipped_to_release_bundle_if_not_existing(
        self, TemporaryDirectory, copytree, patch_path, _, _1, _2, _3, _4
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}
        platform_config_paths = ['test-platform-config-path']
        release_data = ["ami_id=ami-a12345", "foo=bar"]
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=platform_config_paths,
            release_data=release_data,
            commit='dummy',
            version='dummy-version', component_name='dummy-component',
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir
        patch_path.exists.return_value = False

        # When
        release.create(release_plugin)

        # Then
        for args, kwargs in copytree.call_args_list:
            for arg in args:
                self.assertNotEqual('config', arg)
        self.assertEqual(copytree.call_count, 1)

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.open')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.TemporaryDirectory')
    def test_infra_directory_added_to_release_bundle(
        self, TemporaryDirectory, copytree, _, _1, _2, _3, _4
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}
        platform_config_paths = 'test-platform-config-path'
        release_data = ["ami_id=ami-a12345", "foo=bar"]
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths=platform_config_paths,
            release_data=release_data, commit='dummy',
            version='dummy-version', component_name='dummy-component',
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
        )
        temp_dir = 'test-temp-dir'
        TemporaryDirectory.return_value.__enter__.return_value = temp_dir

        # When
        release.create(release_plugin)

        # Then
        copytree.assert_any_call(
            'infra', '{}/{}-{}/infra'.format(
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
        release_data = ["1234=2345"]
        account_scheme = Mock()
        account_scheme.raw_scheme = {}

        release_plugin = Mock()
        release_plugin.create.return_value = plugin_data

        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths='platform-config',
            release_data=release_data,
            commit=commit,
            version=version,
            component_name=component_name,
            team=team,
            account_scheme=account_scheme,
            multi_region=False,
        )

        with ExitStack() as stack:
            stack.enter_context(patch('cdflow_commands.release.mkdir'))
            stack.enter_context(patch('cdflow_commands.release.check_call'))
            stack.enter_context(patch('cdflow_commands.release.copytree'))
            stack.enter_context(patch('cdflow_commands.release.make_archive'))
            stack.enter_context(
                patch('cdflow_commands.release._copy_platform_config')
            )
            TemporaryDirectory = stack.enter_context(
                patch('cdflow_commands.release.TemporaryDirectory')
            )
            _open = stack.enter_context(patch('cdflow_commands.release.open'))

            TemporaryDirectory.return_value.__enter__.return_value = temp_dir

            mock_release_json_file = MagicMock(spec=TextIOWrapper)
            mock_release_json_open = MagicMock()
            mock_release_json_open.__enter__.return_value = \
                mock_release_json_file

            mock_account_scheme_file = MagicMock(spec=TextIOWrapper)
            mock_account_scheme_open = MagicMock()
            mock_account_scheme_open.__enter__.return_value = \
                mock_account_scheme_file

            _open.side_effect = lambda filename, _: \
                mock_release_json_open if filename.endswith('/release.json') \
                else mock_account_scheme_open

            base_release_metadata = {
                'commit': commit,
                'version': version,
                'component': component_name,
                'team': team,
            }

            release_map = dict(item.split('=', 1) for item in release_data)
            # When
            release.create(release_plugin)

            # Then
            release_plugin.create.assert_called_once_with()
            _open.assert_any_call(
                '{}/{}-{}/release.json'.format(
                    temp_dir, component_name, version
                ), 'w'
            )
            mock_release_json_file.write.assert_called_once_with(json.dumps({
                'release': dict(**base_release_metadata,
                                **release_map,
                                **plugin_data)
            }))

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.open')
    def test_release_bundle_added_to_archive(
        self, mock_open, TemporaryDirectory, make_archive, _, _1, _2, _3
    ):

        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}

        commit = 'test-git-commit'
        version = 'test-version'
        component_name = 'test-component'
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        release = Release(
            boto_session=Mock(),
            release_bucket=ANY,
            platform_config_paths='test-platform-config-path',
            release_data=["1234=5678"],
            commit=commit,
            version=version,
            component_name=component_name,
            team='dummy-team',
            account_scheme=account_scheme,
            multi_region=False,
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
        make_archive.assert_called_once_with(
            '{}/{}-{}'.format(temp_dir, component_name, version),
            'zip',
            temp_dir,
            '{}-{}'.format(component_name, version),
        )

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.open')
    def test_create_uploads_archive(
        self, mock_open, TemporaryDirectory, make_archive, copytree,
        check_call, mkdir, _
    ):
        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}

        commit = 'test-git-commit'
        version = 'test-version'
        component_name = 'test-component'
        release_bucket = 'test-release-bucket'
        mock_session = Mock()
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        account_scheme.classic_metadata_handling = True
        team_name = 'dummy-team'
        release = Release(
            boto_session=mock_session,
            release_bucket=release_bucket,
            platform_config_paths='test-platform-config-path',
            release_data=["1234=5678"],
            commit=commit,
            version=version,
            component_name=component_name,
            team=team_name,
            account_scheme=account_scheme,
            multi_region=False,
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
            make_archive_result,
            ExtraArgs={'Metadata': {
                'cdflow_image_digest': 'hash',
            }},
        )
        Object.assert_called_once_with(
            release_bucket, f'{component_name}/{component_name}-{version}.zip',
        )

    @patch('cdflow_commands.release._copy_platform_config')
    @patch('cdflow_commands.release.mkdir')
    @patch('cdflow_commands.release.check_call')
    @patch('cdflow_commands.release.copytree')
    @patch('cdflow_commands.release.make_archive')
    @patch('cdflow_commands.release.TemporaryDirectory')
    @patch('cdflow_commands.release.open')
    def test_create_uploads_archive_to_release_account(
        self, mock_open, TemporaryDirectory, make_archive, copytree,
        check_call, mkdir, _
    ):
        # Given
        release_plugin = Mock()
        release_plugin.create.return_value = {}

        commit = 'test-git-commit'
        version = 'test-version'
        component_name = 'test-component'
        release_bucket = 'test-release-bucket'
        mock_session = Mock()
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        account_scheme.classic_metadata_handling = False
        team_name = 'dummy-team'
        release = Release(
            boto_session=mock_session,
            release_bucket=release_bucket,
            platform_config_paths='test-platform-config-path',
            release_data=["1234=5678"],
            commit=commit,
            version=version,
            component_name=component_name,
            team=team_name,
            account_scheme=account_scheme,
            multi_region=False,
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
            make_archive_result,
            ExtraArgs={'Metadata': {
                'cdflow_image_digest': 'hash',
            }},
        )
        Object.assert_called_once_with(
            release_bucket,
            f'{team_name}/{component_name}/{component_name}-{version}.zip',
        )


class TestFetchRelease(unittest.TestCase):

    @given(fixed_dictionaries({
        'release_bucket': text(alphabet=ALNUM),
        'version': text(alphabet=ALNUM),
        'component_name': text(alphabet=ALNUM),
        'team_name': text(alphabet=ALNUM),
    }))
    def test_release_is_fetched_from_s3(self, fixtures):
        release_bucket = fixtures['release_bucket']
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        account_scheme.classic_metadata_handling = True
        account_scheme.release_bucket = release_bucket
        team_name = fixtures['team_name']
        component_name = fixtures['component_name']
        version = fixtures['version']
        boto_session = Mock()

        mock_object = Mock()
        boto_session.resource.return_value.Object.return_value = mock_object

        with ExitStack() as stack:
            ZipFile = stack.enter_context(
                patch('cdflow_commands.release.ZipFile')
            )
            BytesIO = stack.enter_context(
                patch('cdflow_commands.release.BytesIO')
            )
            getcwd = stack.enter_context(
                patch('cdflow_commands.release.getcwd')
            )
            chmod = stack.enter_context(
                patch('cdflow_commands.release.chmod')
            )
            TemporaryDirectory = stack.enter_context(
                patch('cdflow_commands.release.TemporaryDirectory')
            )
            time = stack.enter_context(patch('cdflow_commands.release.time'))

            mock_zipinfo = MagicMock(spec=ZipInfo)
            file_perm = 1000
            mock_zipinfo.external_attr = file_perm << 16
            ZipFile.return_value.infolist.return_value = [mock_zipinfo]

            with fetch_release(
                boto_session, account_scheme, team_name,
                component_name, version,
            ) as path_to_release:

                assert path_to_release.startswith('{}/release-{}'.format(
                    getcwd.return_value, time.return_value,
                ))

            boto_session.resource.return_value.Object.assert_called_once_with(
                release_bucket,
                f'{component_name}/{component_name}-{version}.zip',
            )

            mock_object.download_fileobj.assert_called_once_with(
                BytesIO.return_value
            )

            ZipFile.assert_called_once_with(BytesIO.return_value)

            ZipFile.return_value.infolist.assert_called_once_with()

            ZipFile.return_value.extract.assert_called_once_with(
                mock_zipinfo.filename,
                TemporaryDirectory.return_value.__enter__.return_value,
            )

            chmod.assert_called_once_with(
                ZipFile.return_value.extract.return_value,
                file_perm,
            )

    @given(fixed_dictionaries({
        'release_bucket': text(alphabet=ALNUM),
        'version': text(alphabet=ALNUM),
        'component_name': text(alphabet=ALNUM),
        'team_name': text(alphabet=ALNUM),
    }))
    def test_release_is_fetched_from_s3_in_release_account(self, fixtures):
        release_bucket = fixtures['release_bucket']
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        account_scheme.classic_metadata_handling = False
        account_scheme.release_bucket = release_bucket
        team_name = fixtures['team_name']
        component_name = fixtures['component_name']
        version = fixtures['version']
        boto_session = Mock()

        mock_object = Mock()
        boto_session.resource.return_value.Object.return_value = mock_object

        with ExitStack() as stack:
            ZipFile = stack.enter_context(
                patch('cdflow_commands.release.ZipFile')
            )
            BytesIO = stack.enter_context(
                patch('cdflow_commands.release.BytesIO')
            )
            getcwd = stack.enter_context(
                patch('cdflow_commands.release.getcwd')
            )
            chmod = stack.enter_context(
                patch('cdflow_commands.release.chmod')
            )
            TemporaryDirectory = stack.enter_context(
                patch('cdflow_commands.release.TemporaryDirectory')
            )
            time = stack.enter_context(patch('cdflow_commands.release.time'))

            mock_zipinfo = MagicMock(spec=ZipInfo)
            file_perm = 1000
            mock_zipinfo.external_attr = file_perm << 16
            ZipFile.return_value.infolist.return_value = [mock_zipinfo]

            with fetch_release(
                boto_session, account_scheme, team_name,
                component_name, version,
            ) as path_to_release:

                assert path_to_release.startswith('{}/release-{}'.format(
                    getcwd.return_value, time.return_value,
                ))

            boto_session.resource.return_value.Object.assert_called_once_with(
                release_bucket,
                f'{team_name}/{component_name}/{component_name}-{version}.zip',
            )

            mock_object.download_fileobj.assert_called_once_with(
                BytesIO.return_value
            )

            ZipFile.assert_called_once_with(BytesIO.return_value)

            ZipFile.return_value.infolist.assert_called_once_with()

            ZipFile.return_value.extract.assert_called_once_with(
                mock_zipinfo.filename,
                TemporaryDirectory.return_value.__enter__.return_value,
            )

            chmod.assert_called_once_with(
                ZipFile.return_value.extract.return_value,
                file_perm,
            )


class TestFindLatestReleaseVersion(unittest.TestCase):

    @given(fixed_dictionaries({
        'team_name': text(alphabet=ALNUM, min_size=1, max_size=2),
        'component_name': text(alphabet=ALNUM, min_size=1, max_size=2),
        'versions': lists(
            elements=text(alphabet=ALNUM, min_size=1, max_size=2),
            min_size=1,
            max_size=2,
        ),
    }))
    @settings(deadline=None)
    def test_find_latest_release_version(self, fixtures):
        team_name = fixtures['team_name']
        component_name = fixtures['component_name']
        versions = fixtures['versions']
        latest_version = versions[-1]
        release_bucket = 'bucket'
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        account_scheme.classic_metadata_handling = True
        account_scheme.release_bucket = release_bucket

        with mock_s3():
            with freeze_time('2021-01-01 01:00:01') as frozen_time:
                s3 = boto3.resource('s3')
                bucket = s3.create_bucket(Bucket=release_bucket)
                for version in versions:
                    bucket.put_object(
                        Key=(
                            f'{component_name}/'
                            f'{component_name}-{version}.zip'
                        ),
                    )
                    frozen_time.tick(delta=datetime.timedelta(hours=1))

            found_version = find_latest_release_version(
                boto3, account_scheme, team_name, component_name,
            )

            assert found_version == latest_version

    @given(fixed_dictionaries({
        'team_name': text(alphabet=ALNUM, min_size=1, max_size=3),
        'component_name': text(alphabet=ALNUM, min_size=1, max_size=3),
        'versions': lists(
            elements=text(alphabet=ALNUM, min_size=1, max_size=3),
            min_size=1,
            max_size=3,
        ),
    }))
    def test_find_latest_release_version_in_release_account(self, fixtures):
        team_name = fixtures['team_name']
        component_name = fixtures['component_name']
        versions = fixtures['versions']
        latest_version = versions[-1]
        release_bucket = 'bucket'
        account_scheme = Mock()
        account_scheme.raw_scheme = {}
        account_scheme.classic_metadata_handling = False
        account_scheme.release_bucket = release_bucket

        with mock_s3():
            with freeze_time('2021-01-01 01:00:01') as frozen_time:
                s3 = boto3.resource('s3')
                bucket = s3.create_bucket(Bucket=release_bucket)
                for version in versions:
                    bucket.put_object(
                        Key=(
                            f'{team_name}/{component_name}/'
                            f'{component_name}-{version}.zip'
                        ),
                    )
                    frozen_time.tick(delta=datetime.timedelta(hours=1))

            found_version = find_latest_release_version(
                boto3, account_scheme, team_name, component_name,
            )

            assert found_version == latest_version
