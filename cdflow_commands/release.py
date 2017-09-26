from contextlib import contextmanager
from io import BytesIO
import json
import os
from os import chmod, getcwd, path, mkdir
from shutil import copytree, make_archive, ignore_patterns
import shutil
from tempfile import TemporaryDirectory
from time import time
from zipfile import ZipFile

from cdflow_commands.constants import (
    CONFIG_BASE_PATH, INFRASTRUCTURE_DEFINITIONS_PATH,
    PLATFORM_CONFIG_BASE_PATH, RELEASE_METADATA_FILE, TERRAFORM_BINARY
)
from cdflow_commands.logger import logger
from cdflow_commands.process import check_call
from cdflow_commands.zip_patch import _make_zipfile

# Monkey patch the standard library...
# https://xkcd.com/292/
shutil._ARCHIVE_FORMATS['zip'] = (_make_zipfile, [], 'ZIP file')


@contextmanager
def fetch_release(boto_session, release_bucket, component_name, version):
    release_archive = download_release(
        boto_session, release_bucket,
        format_release_key(component_name, version)
    )
    with TemporaryDirectory(prefix='{}/release-{}'.format(getcwd(), time())) \
            as path_to_release:
        for zipinfo in release_archive.infolist():
            extract_file(release_archive, zipinfo, path_to_release)
        yield path_to_release


def extract_file(release_archive, zipinfo, extract_path):
    extracted_file_path = release_archive.extract(
        zipinfo.filename, extract_path
    )
    file_mode = zipinfo.external_attr >> 16
    chmod(extracted_file_path, file_mode)


def download_release(boto_session, release_bucket, key):
    s3_resource = boto_session.resource('s3')
    f = BytesIO()
    s3_object = s3_resource.Object(release_bucket, key)
    s3_object.download_fileobj(f)
    f.seek(0)
    return ZipFile(f)


def format_release_key(component_name, version):
    return '{}/{}-{}.zip'.format(component_name, component_name, version)


class Release:

    def __init__(
        self, boto_session, release_bucket, platform_config_paths, commit,
        version, component_name, team
    ):
        self.boto_session = boto_session
        self._release_bucket = release_bucket
        self._platform_config_paths = platform_config_paths
        self._commit = commit
        self._team = team
        self.version = version
        self.component_name = component_name

    def create(self, plugin):
        with TemporaryDirectory() as temp_dir:
            base_dir = self._setup_base_dir(temp_dir)

            self._run_terraform_get(
                base_dir,
                '{}/{}'.format(getcwd(), INFRASTRUCTURE_DEFINITIONS_PATH)
            )

            if os.path.exists(CONFIG_BASE_PATH):
                self._copy_app_config_files(base_dir)
            else:
                logger.warn("""
                    {} not found - Add if you want to include environment \
                    configuration
                    """.format(CONFIG_BASE_PATH))
            self._copy_platform_config_files(base_dir)
            self._copy_infra_files(base_dir)

            extra_data = plugin.create()

            self._generate_release_metadata(base_dir, extra_data)

            release_archive = make_archive(
                base_dir, 'zip', temp_dir,
                '{}-{}'.format(self.component_name, self.version),
            )

            self._upload_archive(release_archive)

    def _generate_release_metadata(self, base_dir, extra_data):
        base_data = {
            'commit': self._commit,
            'version': self.version,
            'component': self.component_name,
            'team': self._team,
        }

        with open(path.join(base_dir, RELEASE_METADATA_FILE), 'w') as f:
            f.write(json.dumps({
                'release': dict(**base_data, **extra_data)
            }))

    def _setup_base_dir(self, temp_dir):
        base_dir = '{}/{}-{}'.format(
            temp_dir, self.component_name, self.version
        )
        logger.debug('Creating directory for release: {}'.format(base_dir))
        mkdir(base_dir)
        return base_dir

    def _upload_archive(self, release_archive):
        s3_resource = self.boto_session.resource('s3')
        s3_object = s3_resource.Object(
            self._release_bucket,
            format_release_key(self.component_name, self.version)
        )
        s3_object.upload_file(
            release_archive,
            ExtraArgs={'Metadata': {
                'cdflow_image_digest': os.environ['CDFLOW_IMAGE_DIGEST'],
            }},
        )

    def _run_terraform_get(self, base_dir, infra_dir):
        logger.debug(
            'Getting Terraform modules defined in {}'.format(infra_dir)
        )
        check_call([
            TERRAFORM_BINARY, 'get', infra_dir
        ], cwd=base_dir)

    def _copy_platform_config_files(self, base_dir):
        path_in_release = '{}/{}'.format(base_dir, PLATFORM_CONFIG_BASE_PATH)
        for platform_config_path in self._platform_config_paths:
            logger.debug('Copying {} to {}'.format(
                platform_config_path, path_in_release
            ))
            copytree(
                platform_config_path, path_in_release,
                ignore=ignore_patterns(['.git'])
            )

    def _copy_app_config_files(self, base_dir):
        path_in_release = '{}/{}'.format(base_dir, CONFIG_BASE_PATH)
        logger.debug('Copying {} to {}'.format(
            CONFIG_BASE_PATH, path_in_release
        ))
        copytree(CONFIG_BASE_PATH, path_in_release)

    def _copy_infra_files(self, base_dir):
        path_in_release = '{}/{}'.format(
            base_dir, INFRASTRUCTURE_DEFINITIONS_PATH
        )
        logger.debug('Copying {} to {}'.format(
            INFRASTRUCTURE_DEFINITIONS_PATH, path_in_release
        ))
        copytree(INFRASTRUCTURE_DEFINITIONS_PATH, path_in_release)
