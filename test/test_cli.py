import unittest

from mock import patch

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

    @patch('cdflow_commands.cli.check_output')
    @patch('cdflow_commands.cli.rmtree')
    @patch('cdflow_commands.cli.sys')
    @patch('cdflow_commands.cli.load_manifest')
    @patch('cdflow_commands.cli.build_account_scheme')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.Release')
    @patch('cdflow_commands.cli.get_component_name')
    def test_unsupported_project_type(
        self, get_component_name, Release, assume_role, build_account_scheme,
        load_manifest, sys, rmtree, check_output, 
    ):
        # Given
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
