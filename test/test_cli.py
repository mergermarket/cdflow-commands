import unittest

from cdflow_commands import cli
from cdflow_commands.exceptions import UnknownProjectTypeError, UserFacingError
from mock import patch


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.sys')
@patch('cdflow_commands.cli.load_service_metadata')
class TestVerboseLogging(unittest.TestCase):

    def test_verbose_flag_in_arguments(self, load_service_metadata, _1, _2):
        # Given
        load_service_metadata.side_effect = UserFacingError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run(['release', 'version', '--verbose'])

        # Then
        assert 'DEBUG:cdflow_commands.logger:Debug logging on' in logs.output

    def test_short_verbose_flag_in_arguments(
        self, load_service_metadata, _1, _2
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run(['release', 'version', '-v'])

        # Then
        assert 'DEBUG:cdflow_commands.logger:Debug logging on' in logs.output


@patch('cdflow_commands.cli.rmtree')
@patch('cdflow_commands.cli.sys')
@patch('cdflow_commands.cli.load_service_metadata')
class TestUserFacingErrorThrown(unittest.TestCase):

    def test_non_zero_exit(self, load_service_metadata, mock_sys, _):
        # Given
        load_service_metadata.side_effect = UserFacingError('Error')

        # When
        with self.assertLogs('cdflow_commands.logger', level='ERROR') as logs:
            cli.run(['release', 'version'])

        # Then
        mock_sys.exit.assert_called_once_with(1)
        expected_message = 'ERROR:cdflow_commands.logger:Error'
        assert expected_message in logs.output

    def test_files_are_always_attempted_to_be_removed(
        self, load_service_metadata, mock_sys, rmtree
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError

        # When
        cli.run(['release', 'version'])

        # Then
        rmtree.assert_called_once_with('.terraform/')

    def test_missing_files_are_ignored(
        self, load_service_metadata, mock_sys, rmtree
    ):
        # Given
        load_service_metadata.side_effect = UserFacingError
        rmtree.side_effect = OSError

        # When
        with self.assertLogs('cdflow_commands.logger', level='DEBUG') as logs:
            cli.run(['release', 'version'])

        # Then
        rmtree.assert_called_once_with('.terraform/')

        message_template = 'DEBUG:cdflow_commands.logger:No path {} to remove'
        assert message_template.format('.terraform/') in logs.output


class TestCliBuildPlugin(unittest.TestCase):
    def test_unsupported_project_type(self):
        # Given
        project_type = 'unknown'

        # When / Then
        with self.assertRaises(UnknownProjectTypeError) as context:
            cli.build_plugin(project_type)

        self.assertTrue(
            'Unsupported project type specified in service.json' in str(
                context.exception
            )
        )
