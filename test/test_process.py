import unittest

from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.process import check_call
from mock import patch
from subprocess import CalledProcessError


class TestProcess(unittest.TestCase):

    @patch('cdflow_commands.process._check_call')
    def test_check_call(self, _check_call):
        # Given When
        check_call('echo', {})

        # Then
        _check_call.assert_called_once_with('echo', {})

    @patch('cdflow_commands.process._check_call')
    def test_check_call_throws_user_facing_exception(self, _check_call):
        # Given
        _check_call.side_effect = CalledProcessError(1, 'echo')

        # When Then
        self.assertRaises(
            UserFacingError,
            check_call,
            'echo',
            {}
        )
