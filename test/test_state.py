import unittest
from contextlib import ExitStack
from io import BufferedRandom
from os.path import join
from string import ascii_letters, ascii_lowercase, digits
from textwrap import dedent

from boto3.session import Session
from cdflow_commands.state import (
    initialise_terraform, remove_file
)
from hypothesis import given
from hypothesis.strategies import fixed_dictionaries, text
from mock import MagicMock, patch, ANY


terraform_backend_input = fixed_dictionaries({
    'base_directory': text(min_size=1).filter(
        lambda t: '/' not in t and '.' not in t
    ),
    'sub_directory': text(min_size=1).filter(
        lambda t: '/' not in t and '.' not in t
    ),
    'aws_region': text(min_size=1),
    'bucket_name': text(
        alphabet=ascii_letters + digits + '-_.', min_size=3, max_size=63
    ),
    'lock_table_name': text(
        alphabet=ascii_lowercase + digits + '-', min_size=3, max_size=63
    ),
    'environment_name': text(min_size=1),
    'component_name': text(min_size=1),
    'tfstate_filename': text(min_size=1),
})


class TestTerraformBackendConfig(unittest.TestCase):

    @given(terraform_backend_input)
    def test_backend_config_written_into_infra_code(
        self, terraform_backend_input
    ):
        base_directory = terraform_backend_input['base_directory']
        sub_directory = terraform_backend_input['sub_directory']
        bucket_name = terraform_backend_input['bucket_name']
        lock_table_name = terraform_backend_input['lock_table_name']
        environment_name = terraform_backend_input['environment_name']
        component_name = terraform_backend_input['component_name']
        tfstate_filename = terraform_backend_input['tfstate_filename']
        boto_session = MagicMock(spec=Session)

        with ExitStack() as stack:
            stack.enter_context(patch('cdflow_commands.state.check_call'))
            stack.enter_context(patch('cdflow_commands.state.atexit'))
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.state.NamedTemporaryFile')
            )

            mock_file = MagicMock(spec=BufferedRandom)
            NamedTemporaryFile.return_value.__enter__.return_value = mock_file

            initialise_terraform(
                base_directory, sub_directory, boto_session, environment_name,
                component_name, tfstate_filename, bucket_name, lock_table_name,
            )

        NamedTemporaryFile.assert_called_once_with(
            prefix='cdflow_backend_', suffix='.tf',
            dir=join(base_directory, sub_directory), delete=False, mode='w+'
        )

        mock_file.write.assert_called_once_with(dedent('''
            terraform {
                backend "s3" {
                }
            }
        ''').strip())

    @given(terraform_backend_input)
    def test_backend_is_initialised(self, terraform_backend_input):
        base_directory = terraform_backend_input['base_directory']
        sub_directory = terraform_backend_input['sub_directory']
        bucket_name = terraform_backend_input['bucket_name']
        lock_table_name = terraform_backend_input['lock_table_name']
        environment_name = terraform_backend_input['environment_name']
        component_name = terraform_backend_input['component_name']
        tfstate_filename = terraform_backend_input['tfstate_filename']
        boto_session = MagicMock(spec=Session)

        state_file_key = (
            f'{environment_name}/{component_name}/{tfstate_filename}'
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch('cdflow_commands.state.NamedTemporaryFile')
            )
            stack.enter_context(patch('cdflow_commands.state.atexit'))
            check_call = stack.enter_context(
                patch('cdflow_commands.state.check_call')
            )

            initialise_terraform(
                base_directory, sub_directory, boto_session, environment_name,
                component_name, tfstate_filename, bucket_name, lock_table_name,
            )

        check_call.assert_called_once_with(
            [
                'terraform', 'init',
                '-get=false',
                '-get-plugins=false',
                f'-backend-config=bucket={bucket_name}',
                f'-backend-config=region={boto_session.region_name}',
                f'-backend-config=key={state_file_key}',
                f'-backend-config=dynamodb_table={lock_table_name}',
                ANY,
                ANY,
                ANY,
                join(base_directory, sub_directory),
            ],
            cwd=base_directory,
        )

    @given(fixed_dictionaries({
        'terraform_backend_input': terraform_backend_input,
        'temp_file_name': text(
            min_size=3, max_size=10, alphabet=ascii_lowercase+digits
        )
    }))
    def test_config_file_is_removed_at_exit(self, test_fixtures):
        terraform_backend_input = test_fixtures['terraform_backend_input']
        base_directory = terraform_backend_input['base_directory']
        sub_directory = terraform_backend_input['sub_directory']
        bucket_name = test_fixtures['terraform_backend_input']['bucket_name']
        boto_session = MagicMock(spec=Session)
        lock_table_name = (
            test_fixtures['terraform_backend_input']['lock_table_name']
        )
        environment_name = (
            test_fixtures['terraform_backend_input']['environment_name']
        )
        component_name = (
            test_fixtures['terraform_backend_input']['component_name']
        )
        tfstate_filename = (
            test_fixtures['terraform_backend_input']['tfstate_filename']
        )

        backend_config_file_name = (
            f'cdflow_backend_{test_fixtures["temp_file_name"]}.tf'
        )

        with ExitStack() as stack:
            stack.enter_context(patch('cdflow_commands.state.check_call'))
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.state.NamedTemporaryFile')
            )
            atexit = stack.enter_context(patch('cdflow_commands.state.atexit'))

            NamedTemporaryFile.return_value.__enter__.return_value.name = \
                backend_config_file_name

            initialise_terraform(
                base_directory, sub_directory, boto_session, environment_name,
                component_name, tfstate_filename, bucket_name, lock_table_name,
            )

        atexit.register.assert_called_once_with(
            remove_file, backend_config_file_name
        )

    @given(text())
    def test_remove_file_function(self, filepath):
        with patch('cdflow_commands.state.unlink') as unlink:
            remove_file(filepath)

        unlink.assert_called_once_with(filepath)

    @given(text())
    def test_remove_file_function_handles_missing_file(self, filepath):
        with patch('cdflow_commands.state.unlink') as unlink:
            unlink.side_effect = OSError('File not found')

            try:
                remove_file(filepath)
            except OSError as e:
                self.fail(f'An error was thrown: {e}')

        unlink.assert_called_once_with(filepath)
