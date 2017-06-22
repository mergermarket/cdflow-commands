from subprocess import check_call
from tempfile import TemporaryDirectory
from os import getcwd, path, mkdir
from shutil import copytree, make_archive
import json


class Release:

    def __init__(
        self, boto_session, release_bucket, platform_config_path, commit,
        version, component_name
    ):
        self.boto_session = boto_session
        self._release_bucket = release_bucket
        self._platform_config_path = platform_config_path
        self._commit = commit
        self.version = version
        self.component_name = component_name

    def _run_terraform_get(self, base_dir, infra_dir):
        check_call([
            'terraform', 'get', infra_dir
        ], cwd=base_dir)

    def _copy_platform_config_files(self, base_dir):
        copytree(
            self._platform_config_path,
            '{}/platform-config'.format(base_dir)
        )

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

            self._run_terraform_get(base_dir, '{}/infra'.format(cwd))
            self._copy_platform_config_files(base_dir)

            artefacts = plugin.create()

            with open(path.join(base_dir, 'release.json'), 'w') as f:
                f.write(json.dumps({
                    'release': {
                        'commit': self._commit,
                        'version': self.version,
                        'component-name': self.component_name,
                        'artefacts': artefacts
                    }
                }))

            return make_archive(
                base_dir, 'zip', temp_dir,
                '{}-{}'.format(self.component_name, self.version),
            )
