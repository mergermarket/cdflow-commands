from contextlib import contextmanager
from io import BytesIO
import json
from os import getcwd, path, mkdir
from shutil import copytree, make_archive
from subprocess import check_call
from tempfile import TemporaryDirectory
from time import time
from zipfile import ZipFile

from cdflow_commands.constants import (
    CONFIG_BASE_PATH, GLOBAL_CONFIG_FILE, INFRASTRUCTURE_DEFINITIONS_PATH,
    PLATFORM_CONFIG_BASE_PATH, RELEASE_METADATA_FILE, TERRAFORM_BINARY
)


@contextmanager
def fetch_release(boto_session, release_bucket, component_name, version):
    release_archive = download_release(
        boto_session, release_bucket,
        format_release_key(component_name, version)
    )
    with TemporaryDirectory(
        prefix='{}/release-{}'.format(getcwd(), time())
    ) as path_to_release:
        release_archive.extractall(path_to_release)
        yield path_to_release


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
        self, boto_session, release_bucket, platform_config_path, commit,
        version, component_name, team
    ):
        self.boto_session = boto_session
        self._release_bucket = release_bucket
        self._platform_config_path = platform_config_path
        self._commit = commit
        self._team = team
        self.version = version
        self.component_name = component_name

    @property
    def global_config_present(self):
        return path.exists(GLOBAL_CONFIG_FILE)

    def create(self, plugin):
        release_archive = self.create_archive(plugin)
        s3_resource = self.boto_session.resource('s3')
        s3_object = s3_resource.Object(
            self._release_bucket,
            format_release_key(self.component_name, self.version)
        )
        s3_object.upload_file(release_archive)

    def create_archive(self, plugin):

        with TemporaryDirectory() as temp_dir:
            base_dir = '{}/{}-{}'.format(
                temp_dir, self.component_name, self.version
            )
            mkdir(base_dir)

            cwd = getcwd()

            self._run_terraform_get(
                base_dir, '{}/{}'.format(cwd, INFRASTRUCTURE_DEFINITIONS_PATH)
            )
            self._copy_app_config_files(base_dir)
            self._copy_platform_config_files(base_dir)

            extra_data = plugin.create()

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

            return make_archive(
                base_dir, 'zip', temp_dir,
                '{}-{}'.format(self.component_name, self.version),
            )

    def _run_terraform_get(self, base_dir, infra_dir):
        check_call([
            TERRAFORM_BINARY, 'get', infra_dir
        ], cwd=base_dir)

    def _copy_platform_config_files(self, base_dir):
        copytree(
            self._platform_config_path,
            '{}/{}'.format(base_dir, PLATFORM_CONFIG_BASE_PATH)
        )

    def _copy_app_config_files(self, base_dir):
        copytree(
            CONFIG_BASE_PATH,
            '{}/{}'.format(base_dir, CONFIG_BASE_PATH)
        )
