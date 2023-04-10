import os
from zipfile import ZipFile
from contextlib import contextmanager

from cdflow_commands.logger import logger


class ReleasePlugin:

    def __init__(self, release, account_scheme):
        self._boto_session = release.boto_session
        self._component_name = release.component_name
        self._team = release.team
        self._version = release.version
        self._account_scheme = account_scheme
        self._multi_region = release.multi_region
        if os.path.isdir(release.component_name):
            self._source_dir = release.component_name
        else:
            self._source_dir = 'src'

    @property
    def _lambda_s3_key(self):
        key = '{}/{}-{}.zip'.format(
            self._component_name, self._component_name, self._version
        )
        if not self._account_scheme.classic_metadata_handling:
            key = f'{self._team}/{key}'
        return key

    @property
    def _boto_s3_client(self):
        return self._boto_session.client('s3')

    def create(self):
        zipped_folder = self._zip_up_component()
        if self._multi_region:
            metadata = self._upload_zip_to_buckets(
                self._account_scheme.lambda_buckets, zipped_folder.filename
            )
        else:
            metadata = self._upload_zip_to_bucket(
                self._account_scheme.lambda_bucket, zipped_folder.filename
            )
        self._remove_zipped_folder(zipped_folder.filename)
        return metadata

    @contextmanager
    def _change_dir(self, path):
        top_level = os.getcwd()
        os.chdir(path)
        yield
        os.chdir(top_level)

    def _zip_up_component(self):
        logger.info('Zipping up ./{} folder'.format(self._source_dir))
        with ZipFile(self._source_dir + '.zip', 'w') as zipped_folder:
            with self._change_dir(self._source_dir):
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
        return {
            's3_bucket': bucket_name,
            's3_key': self._lambda_s3_key,
        }

    def _upload_zip_to_buckets(self, buckets, filename):
        metadata = {
            's3_key': self._lambda_s3_key,
            # this is a map tfvar that currently only allows scalar values
            # in the future we might have a list without the _csv postfix
            # (the same applies to the "s3_bucket." psuedo-map below)
            's3_bucket_regions_csv': ','.join(sorted(buckets.keys()))
        }
        for region, bucket_name in buckets.items():
            logger.info(
                'Uploading {} to s3 bucket ({} in {}) with key: {}'.format(
                    filename, bucket_name, region, self._lambda_s3_key
                )
            )
            self._boto_session.client('s3', region_name=region).upload_file(
                filename,
                bucket_name,
                self._lambda_s3_key
            )
            metadata[f's3_bucket.{region}'] = bucket_name
        return metadata

    def _remove_zipped_folder(self, filename):
        logger.info('Removing local zipped package: {}'.format(filename))
        os.remove(filename)
