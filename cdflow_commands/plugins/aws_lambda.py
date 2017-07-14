import os
from zipfile import ZipFile
from contextlib import contextmanager

from cdflow_commands.logger import logger
from cdflow_commands.state import S3BucketFactory


class ReleasePlugin:

    _BUCKET_NAME = 'cdflow-lambda-releases'

    def __init__(self, release, account_scheme):
        self._boto_session = release.boto_session
        self._component_name = release.component_name
        self._version = release.version
        self._account_scheme = account_scheme

    @property
    def _lambda_s3_key(self):
        return '{}/{}-{}.zip'.format(
            self._component_name, self._component_name, self._version
        )

    @property
    def _boto_s3_client(self):
        return self._boto_session.client('s3')

    def create(self):
        zipped_folder = self._zip_up_component()
        s3_bucket_factory = S3BucketFactory(
            self._boto_session, self._account_scheme.release_account.id
        )
        created_bucket_name = s3_bucket_factory.get_bucket_name(
            self._BUCKET_NAME
        )
        self._upload_zip_to_bucket(
            created_bucket_name, zipped_folder.filename
        )
        self._remove_zipped_folder(zipped_folder.filename)

        return {
            's3_bucket': created_bucket_name,
            's3_key': self._lambda_s3_key,
        }

    @contextmanager
    def _change_dir(self, path):
        top_level = os.getcwd()
        os.chdir(path)
        yield
        os.chdir(top_level)

    def _zip_up_component(self):
        logger.info('Zipping up ./{} folder'.format(self._component_name))
        with ZipFile(self._component_name + '.zip', 'w') as zipped_folder:
            with self._change_dir(self._component_name):
                for dirname, subdirs, files in os.walk('.'):
                    for filename in files:
                        zipped_folder.write(os.path.join(dirname, filename))
        return zipped_folder

    def _upload_zip_to_bucket(self, bucket_name, filename):
        logger.info('Uploading {} to s3 bucket ({}) with key: {}'.format(
            filename, bucket_name, self._lambda_s3_key
        ))
        self._boto_s3_client.upload_file(
            filename,
            bucket_name,
            self._lambda_s3_key
        )

    def _remove_zipped_folder(self, filename):
        logger.info('Removing local zipped package: {}'.format(filename))
        os.remove(filename)
