from subprocess import check_call
from tempfile import TemporaryDirectory
from os import getcwd, path, mkdir
from shutil import copytree, make_archive
import json

from cdflow_commands.constants import (
    CONFIG_BASE_PATH, GLOBAL_CONFIG_FILE, INFRASTRUCTURE_DEFINITIONS_PATH,
    PLATFORM_CONFIG_BASE_PATH, RELEASE_METADATA_FILE, TERRAFORM_BINARY
)


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

    @property
    def all_environment_config(self):
        if (
            not hasattr(self, '__all_environment_config')
            and self.global_config_present
        ):
            with open(GLOBAL_CONFIG_FILE) as f:
                self.__all_environment_config = json.loads(f.read())
        return self.__all_environment_config

    def create(self, plugin):
        release_archive = self.create_archive(plugin)
        s3_resource = self.boto_session.resource('s3')
        s3_object = s3_resource.Object(
            self._release_bucket,
            '{}/{}-{}.zip'.format(
                self.component_name, self.component_name, self.version
            )
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
