import unittest

from cdflow_commands.config import GlobalConfig
from cdflow_commands.plugins.aws_lambda import LambdaPlugin
from mock import Mock, ANY, patch


class TestLambdaPlugin(unittest.TestCase):

    @patch('cdflow_commands.plugins.aws_lambda.os')
    @patch('cdflow_commands.plugins.aws_lambda.assume_role')
    @patch('cdflow_commands.plugins.aws_lambda.Deploy')
    def test_plugin_runs_deploy(self, mock_deploy, assume_role, mock_os):

        assume_role.return_value = Mock()

        mock_os.environ = {
            'JOB_NAME': 'dummy-job-name'
        }
        global_config = GlobalConfig(
            'account_id_for_dev', 'account_id_for_prod'
        )

        lambda_plugin = LambdaPlugin(
            'ci', 'dummy-component', '6.1.7', ANY, global_config, ANY
        )
        # When
        lambda_plugin.deploy()

        # Then
        mock_deploy().run.assert_called_once()
