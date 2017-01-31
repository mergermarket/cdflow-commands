import unittest

import json

from mock import patch, Mock, MagicMock, mock_open

from cdflow_commands import cli


class TestLoadConfig(unittest.TestCase):

    @patch('cdflow_commands.cli.open', new_callable=mock_open, create=True)
    def test_service_metadata_loaded(self, mock_open):
        mock_file = MagicMock(spec=file)
        expected_config = {
            'TEAM': 'dummy-team',
            'TYPE': 'docker',
            'REGION': 'eu-west-1',
            'ACCOUNT_PREFIX': 'mmg'
        }
        mock_file.read.return_value = json.dumps(expected_config)
        mock_open.return_value.__enter__.return_value = mock_file
        metadata = cli.load_service_metadata()
        assert metadata.team == expected_config['TEAM']
        assert metadata.type == expected_config['TYPE']
        assert metadata.aws_region == expected_config['REGION']
        assert metadata.account_prefix == expected_config['ACCOUNT_PREFIX']
        mock_open.assert_called_once_with('service.json')

    @patch('cdflow_commands.cli.open', new_callable=mock_open, create=True)
    def test_loaded_from_file(self, mock_open):
        mock_dev_file = MagicMock(spec=file)
        dev_config = {
            'platform_config': {
                'account_id': 123456789
            }
        }
        mock_dev_file.read.return_value = json.dumps(dev_config)

        mock_prod_file = MagicMock(spec=file)
        prod_config = {
            'platform_config': {
                'account_id': 987654321
            }
        }
        mock_prod_file.read.return_value = json.dumps(prod_config)

        mock_open.return_value.__enter__.side_effect = (
            f for f in (mock_dev_file, mock_prod_file)
        )

        account_prefix = 'mmg'
        aws_region = 'eu-west-5'
        config = cli.load_global_config(account_prefix, aws_region)

        assert config.dev_account_id == 123456789
        assert config.prod_account_id == 987654321

        file_path_template = 'infra/platform-config/{}/{}/{}.json'
        mock_open.assert_any_call(
            file_path_template.format(account_prefix, 'dev', aws_region)
        )
        mock_open.assert_any_call(
            file_path_template.format(account_prefix, 'prod', aws_region)
        )


class TestReleaseCLI(unittest.TestCase):

    @patch('cdflow_commands.cli.load_global_config')
    @patch('cdflow_commands.cli.assume_role')
    @patch('cdflow_commands.cli.Release')
    @patch('cdflow_commands.cli.ReleaseConfig')
    def test_release_is_configured(
        self, ReleaseConfig, Release, assume_role, load_global_config
    ):
        mock_config = Mock()
        ReleaseConfig.return_value = mock_config

        mock_boto_session = Mock()
        assume_role.return_value = mock_boto_session
        mock_ecr_client = Mock()
        mock_boto_session.client.return_value = mock_ecr_client

        dev_account_id = 1
        prod_account_id = 2
        aws_region = 'eu-west-8'
        mock_global_config = Mock()
        mock_global_config.dev_account_id = dev_account_id
        mock_global_config.prod_account_id = prod_account_id
        mock_global_config.aws_region = aws_region
        load_global_config.return_value = mock_global_config

        component_name = 'dummy-component'
        version = '1.2.3'
        cli.run(['release', version, '-c', component_name])

        ReleaseConfig.assert_called_once_with(
            dev_account_id, prod_account_id, aws_region
        )

        Release.assert_called_once_with(
            mock_config, mock_ecr_client, component_name, version
        )
