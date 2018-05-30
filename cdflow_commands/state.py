import atexit
from os import unlink
from os.path import join
from tempfile import NamedTemporaryFile
from textwrap import dedent

from cdflow_commands.logger import logger
from cdflow_commands.process import check_call


def remove_file(filepath):
    try:
        logger.debug(f'Removing {filepath}')
        unlink(filepath)
    except OSError as e:
        logger.debug(f'Error removing {filepath}: {e}')


def initialise_terraform(
    base_directory, sub_directory, boto_session, environment_name,
    component_name, tfstate_filename, bucket_name, lock_table_name,
):
    working_directory = join(base_directory, sub_directory)
    with NamedTemporaryFile(
        prefix='cdflow_backend_', suffix='.tf',
        dir=working_directory, delete=False, mode='w+'
    ) as backend_file:
        logger.debug(f'Writing backend config to {backend_file.name}')
        backend_file.write(dedent('''
            terraform {
                backend "s3" {
                }
            }
        ''').strip())
        logger.debug(f'Registering {backend_file.name} to be removed at exit')
        atexit.register(remove_file, backend_file.name)

    key = state_file_key(environment_name, component_name, tfstate_filename)
    logger.debug(
        f'Initialising backend in {working_directory} with {bucket_name}, '
        f'{boto_session.region_name}, {key}, {lock_table_name}'
    )

    credentials = boto_session.get_credentials()
    check_call(
        [
            'terraform', 'init',
            '-get=false',
            '-get-plugins=false',
            f'-backend-config=bucket={bucket_name}',
            f'-backend-config=region={boto_session.region_name}',
            f'-backend-config=key={key}',
            f'-backend-config=dynamodb_table={lock_table_name}',
            f'-backend-config=access_key={credentials.access_key}',
            f'-backend-config=secret_key={credentials.secret_key}',
            f'-backend-config=token={credentials.token}',
            working_directory,
        ],
        cwd=base_directory,
    )


def state_file_key(environment_name, component_name, tfstate_filename):
    return f'{environment_name}/{component_name}/{tfstate_filename}'


def remove_state(
    boto_session, environment_name, component_name, tfstate_filename,
    account_scheme
):

    key = state_file_key(environment_name, component_name, tfstate_filename)

    s3_client = boto_session.client('s3')
    s3_client.delete_object(Bucket=account_scheme.backend_s3_bucket, Key=key)
