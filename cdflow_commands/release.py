from subprocess import check_call
from tempfile import mkdtemp
from os import getcwd, path
from shutil import copyfile
import json


class Release:

    def __init__(
        self, platform_config_path, commit,
        version, component_name
    ):
        self._platform_config_path = platform_config_path
        self._commit = commit
        self.version = version
        self.component_name = component_name

    def _run_terraform_get(self, base_dir, infra_dir):
        check_call([
            'terraform', 'get', infra_dir
        ], cwd=base_dir)

    def _copy_platform_config_files(self, base_dir):
        copyfile(
            '{}/dev.json'.format(self._platform_config_path),
            '{}/dev.json'.format(base_dir)
        )
        copyfile(
            '{}/prod.json'.format(self._platform_config_path),
            '{}/prod.json'.format(base_dir)
        )

    def create(self, plugin):

        base_dir = mkdtemp()
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
