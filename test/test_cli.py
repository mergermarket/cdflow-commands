import unittest

from mock import patch, Mock, ANY

from cdflow_commands import cli
from cdflow_commands.exceptions import UnknownProjectTypeError, UserFacingError


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.sys')
@patch('cdflow_commands.cli.load_manifest')
class TestVerboseLogging(unittest.TestCase):

    def test_verbose_flag_in_arguments(self, load_manifest, _1, _2):
        # Given
        load_manifest.side_effect = UserFacingError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run([
                'release', '--platform-config', 'path/to/config',
                'version', '--verbose'
            ])

        # Then
        assert 'DEBUG:cdflow_commands.logger:Debug logging on' in logs.output

    def test_short_verbose_flag_in_arguments(
        self, load_manifest, _1, _2
    ):
        # Given
        load_manifest.side_effect = UserFacingError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run([
                'release', '--platform-config', 'path/to/config',
                'version', '-v'
            ])

        # Then
        assert 'DEBUG:cdflow_commands.logger:Debug logging on' in logs.output


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.sys')
@patch('cdflow_commands.cli.load_manifest')
class TestUserFacingErrorThrown(unittest.TestCase):

    def test_non_zero_exit(self, load_manifest, mock_sys, _):
        # Given
        load_manifest.side_effect = UserFacingError('Error')

        # When
        with self.assertLogs('cdflow_commands.logger', level='ERROR') as logs:
            cli.run([
                'release', '--platform-config', 'path/to/config', 'version'
            ])

        # Then
        mock_sys.exit.assert_called_once_with(1)
        expected_message = 'ERROR:cdflow_commands.logger:Error'
        assert expected_message in logs.output

    def test_files_are_always_attempted_to_be_removed(
        self, load_manifest, mock_sys, rmtree
    ):
        # Given
        load_manifest.side_effect = UserFacingError

        # When
        cli.run(['release', '--platform-config', 'path/to/config', 'version'])

        # Then
        rmtree.assert_called_once_with('.terraform/')

    def test_missing_files_are_ignored(
        self, load_manifest, mock_sys, rmtree
    ):
        # Given
        load_manifest.side_effect = UserFacingError
        rmtree.side_effect = OSError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run([
                'release', '--platform-config', 'path/to/config', 'version'
            ])

        # Then
        rmtree.assert_called_once_with('.terraform/')

        message_template = 'DEBUG:cdflow_commands.logger:No path {} to remove'
        assert message_template.format('.terraform/') in logs.output


class TestCliBuildPlugin(unittest.TestCase):

    @patch('cdflow_commands.cli.os')
    @patch('cdflow_commands.cli.check_output')
    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.cli.sys')
    @patch('cdflow_commands.cli.load_manifest')
    @patch('cdflow_commands.cli.build_account_scheme_s3')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.Release')
    @patch('cdflow_commands.cli.get_component_name')
    def test_unsupported_project_type(
        self, get_component_name, Release, assume_role,
        build_account_scheme_s3, load_manifest, sys, rmtree, check_output, os,
    ):
        # Given
        os.environ = {'JOB_NAME': 'dummy-job-name'}

        check_output.return_value = 'hash\n'.encode('utf-8')

        # When / Then
        with self.assertRaises(UnknownProjectTypeError) as context:
            cli._run([
                'release', '--platform-config', 'path/to/config', 'version'
            ])

        expected_message = 'Unknown project type: {}'.format(
            load_manifest.return_value.type
        )

        assert expected_message in str(context.exception)


class TestRoles(unittest.TestCase):

    @patch('cdflow_commands.cli.load_manifest')
    @patch('cdflow_commands.cli.run_release')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.build_account_scheme_s3')
    @patch('cdflow_commands.cli.Session')
    def test_release_assumes_release_account_role(
        self, Session, build_account_scheme_s3, assume_role, run_release,
        load_manifest
    ):

        # Given
        root_session = Mock()
        Session.return_value = root_session
        release_account_session = Mock()
        assume_role.return_value = release_account_session
        account_scheme = Mock()
        account_scheme.release_account.id = '1234567890'
        account_scheme.release_account.role = 'test-role'
        account_scheme.default_region = 'eu-west-12'
        build_account_scheme_s3.return_value = account_scheme

        # When
        cli._run([
            'release', '--platform-config', 'path/to/config', 'version'
        ])

        # Then
        assume_role.assert_called_once_with(
            root_session, '1234567890', 'test-role', 'eu-west-12'
        )
        run_release.assert_called_once_with(
            release_account_session, account_scheme, ANY,
            ANY
        )

    @patch('cdflow_commands.cli.fetch_release')
    @patch('cdflow_commands.cli.run_deploy')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.build_account_scheme_file')
    def test_deploy_assumes_infrastructure_account_role(
        self, build_account_scheme_file, assume_role, run_deploy,
        fetch_release
    ):

        # Given
        root_session = Mock()
        release_account_session = Mock()
        infrastructure_account_session = Mock()
        assume_role.return_value = infrastructure_account_session
        account_scheme = Mock()
        account_scheme.release_account.id = '1234567890'
        account_scheme.default_region = 'eu-west-12'
        account_scheme.classic_metadata_handling = False
        infrastructure_account = Mock()
        infrastructure_account.id = '0987654321'
        infrastructure_account.role = 'test-role'
        account_scheme.account_for_environment.return_value = \
            infrastructure_account
        build_account_scheme_file.return_value = account_scheme
        fetch_release.return_value.__enter__.return_value = 'dummy'

        # When
        cli.run_non_release_command(
            root_session, release_account_session, account_scheme, Mock(), {
                'deploy': True, 'destroy': False, '<environment>': 'ci',
                '<version>': '1', '--component': 'dummy'
            }
        )

        # Then
        account_scheme.account_for_environment.assert_called_once_with('ci')
        assume_role.assert_called_once_with(
            root_session, '0987654321', 'test-role', 'eu-west-12'
        )
        run_deploy.assert_called_once_with(
            ANY, account_scheme, release_account_session,
            infrastructure_account_session, ANY, ANY, ANY, ANY
        )

    @patch('cdflow_commands.cli.fetch_release')
    @patch('cdflow_commands.cli.run_deploy')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.build_account_scheme_file')
    def test_deploy_classic_metadata_handling(
        self, build_account_scheme_file, assume_role, run_deploy,
        fetch_release
    ):

        # Given
        root_session = Mock()
        release_account_session = Mock()
        infrastructure_account_session = Mock()
        assume_role.return_value = infrastructure_account_session
        account_scheme = Mock()
        account_scheme.release_account.id = '1234567890'
        account_scheme.default_region = 'eu-west-12'
        account_scheme.classic_metadata_handling = True
        infrastructure_account = Mock()
        infrastructure_account.id = '0987654321'
        infrastructure_account.role = 'test-role'
        account_scheme.account_for_environment.return_value = \
            infrastructure_account
        build_account_scheme_file.return_value = account_scheme
        fetch_release.return_value.__enter__.return_value = 'dummy'

        # When
        cli.run_non_release_command(
            root_session, release_account_session, account_scheme, Mock(), {
                'deploy': True, 'destroy': False, '<environment>': 'ci',
                '<version>': '1', '--component': 'dummy'
            }
        )

        # Then
        account_scheme.account_for_environment.assert_called_once_with('ci')
        assume_role.assert_called_once_with(
            root_session, '0987654321', 'test-role', 'eu-west-12'
        )
        run_deploy.assert_called_once_with(
            ANY, account_scheme, infrastructure_account_session,
            infrastructure_account_session, ANY, ANY, ANY, ANY
        )


class TestAccountSchemeHandling(unittest.TestCase):

    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.fetch_release')
    @patch('cdflow_commands.cli.run_deploy')
    @patch('cdflow_commands.cli.build_account_scheme_file')
    def test_deploy_uses_account_scheme_from_release(
        self, build_account_scheme_file, run_deploy, fetch_release, _1
    ):

        # Given
        project_account_scheme = Mock()
        project_account_scheme.release_account.id = '1234567890'
        release_account_scheme = Mock()
        build_account_scheme_file.return_value = release_account_scheme
        fetch_release.return_value.__enter__.return_value = 'dummy'

        # When
        cli.run_non_release_command(
            ANY, ANY, project_account_scheme, Mock(), {
                'deploy': True, 'destroy': False, '<environment>': 'ci',
                '<version>': '1', '--component': 'dummy'
            }
        )

        # Then
        release_account_scheme.account_for_environment.assert_called_once_with(
            'ci'
        )
        run_deploy.assert_called_once_with(
            ANY, release_account_scheme, ANY, ANY, ANY, ANY, ANY, ANY
        )


class TestSecretsFromInfraAccount(unittest.TestCase):

    @patch('cdflow_commands.cli.Deploy')
    @patch('cdflow_commands.cli.initialise_terraform')
    @patch('cdflow_commands.cli.get_secrets')
    def test_secrets_in_deploy_account(self, get_secrets, _, _1):
        # Given
        deploy_session = Mock()
        env = 'test-env'
        manifest = Mock()
        manifest.team = 'test-team'
        component_name = 'test-component'
        args = {'--plan-only': False}

        # When
        cli.run_deploy(
            ANY, ANY, ANY, deploy_session, manifest, args, env, component_name
        )

        # Then
        get_secrets.assert_called_once_with(
            env, manifest.team, component_name, deploy_session
        )
