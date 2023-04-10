from contextlib import contextmanager
from io import BytesIO
import json
from operator import attrgetter
import os
from os import chmod, getcwd, path, mkdir, makedirs, listdir
from os.path import isdir, isfile
from shutil import copytree, make_archive, copyfile
import shutil
from tempfile import TemporaryDirectory
from time import time
from zipfile import ZipFile
from re import match, search

from cdflow_commands.constants import (
    CONFIG_BASE_PATH, INFRASTRUCTURE_DEFINITIONS_PATH,
    PLATFORM_CONFIG_BASE_PATH, RELEASE_METADATA_FILE, TERRAFORM_BINARY,
    ACCOUNT_SCHEME_FILE
)
from cdflow_commands.logger import logger
from cdflow_commands.process import check_call
from cdflow_commands.zip_patch import _make_zipfile


shutil.unregister_archive_format('zip')
shutil.register_archive_format('zip', _make_zipfile)


@contextmanager
def fetch_release(
    boto_session, account_scheme, team_name, component_name, version,
):
    if account_scheme.classic_metadata_handling:
        release_key = format_release_key_classic(component_name, version)
    else:
        release_key = format_release_key(team_name, component_name, version)
    release_archive = download_release(
        boto_session, account_scheme.release_bucket, release_key,
    )
    with TemporaryDirectory(prefix='{}/release-{}'.format(getcwd(), time())) \
            as path_to_release:
        for zipinfo in release_archive.infolist():
            extract_file(release_archive, zipinfo, path_to_release)
        yield path_to_release


def find_latest_release_version(
    boto_session, account_scheme, team_name, component_name,
):
    s3 = boto_session.resource('s3')
    bucket = s3.Bucket(account_scheme.release_bucket)
    if account_scheme.classic_metadata_handling:
        key_prefix = format_release_key_prefix_classic(component_name)
    else:
        key_prefix = format_release_key_prefix(team_name, component_name)
    component_releases = bucket.objects.filter(Prefix=key_prefix)
    ordered_releases = sorted(
        component_releases,
        key=attrgetter('last_modified'),
        reverse=True,
    )
    latest_release = ordered_releases[0].key
    version = latest_release[len(key_prefix):][:-len('.zip')]
    return version


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


def format_release_key(team_name, component_name, version):
    return (
        f'{format_release_key_prefix(team_name, component_name)}'
        f'{version}.zip'
    )


def format_release_key_prefix(team_name, component_name):
    return f'{team_name}/{component_name}/{component_name}-'


def format_release_key_classic(component_name, version):
    return (
        f'{format_release_key_prefix_classic(component_name)}'
        f'{version}.zip'
    )


def format_release_key_prefix_classic(component_name):
    return f'{component_name}/{component_name}-'


def _copy_platform_config_files(source_dir, dest_dir):
    makedirs(dest_dir, exist_ok=True)
    for config in listdir(source_dir):
        source = os.path.join(source_dir, config)
        dest = os.path.join(dest_dir, config)
        if search(r'\.json$', source) and isfile(source):
            copyfile(source, dest)


def _copy_platform_config(source_dir, dest_dir):
    for item in listdir(source_dir):
        if not match(r'^\w+$', item):
            continue
        source = os.path.join(source_dir, item)
        if not isdir(source):
            continue
        dest = os.path.join(dest_dir, item)
        _copy_platform_config_files(source, dest)


class Release:

    def __init__(
        self, boto_session, release_bucket, platform_config_paths,
        release_data, commit, version, component_name, team, account_scheme,
        multi_region
    ):
        self.boto_session = boto_session
        self._release_bucket = release_bucket
        self._platform_config_paths = platform_config_paths
        self.release_data = release_data
        self._commit = commit
        self.team = team
        self.version = version
        self.component_name = component_name
        self.account_scheme = account_scheme
        self.multi_region = multi_region

    def create(self, plugin):
        with TemporaryDirectory() as temp_dir:
            base_dir = self._setup_base_dir(temp_dir)

            self._copy_infra_files(base_dir)

            self._run_terraform_init(
                base_dir,
                './{}'.format(INFRASTRUCTURE_DEFINITIONS_PATH)
            )

            if os.path.exists(CONFIG_BASE_PATH):
                self._copy_app_config_files(base_dir)
            else:
                logger.warning("""
                    {} not found - Add if you want to include environment \
                    configuration
                    """.format(CONFIG_BASE_PATH))
            self._copy_platform_configs(base_dir)

            extra_data = plugin.create()

            self._generate_release_metadata(base_dir,
                                            self.release_data,
                                            extra_data)

            self._add_account_scheme(base_dir)

            release_archive = make_archive(
                base_dir, 'zip', temp_dir,
                '{}-{}'.format(self.component_name, self.version),
            )

            self._upload_archive(release_archive)

    def _add_account_scheme(self, base_dir):
        with open(path.join(base_dir, ACCOUNT_SCHEME_FILE), 'w') as f:
            f.write(json.dumps(self.account_scheme.raw_scheme))

    def _generate_release_metadata(self, base_dir, release_data, extra_data):
        base_data = {
            'commit': self._commit,
            'version': self.version,
            'component': self.component_name,
            'team': self.team,
        }

        release_map = dict(item.split('=', 1) for item in release_data)

        with open(path.join(base_dir, RELEASE_METADATA_FILE), 'w') as f:
            f.write(json.dumps({
                'release': dict(**base_data, **release_map, **extra_data)
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
        if self.account_scheme.classic_metadata_handling:
            release_key = format_release_key_classic(
                self.component_name, self.version,
            )
        else:
            release_key = format_release_key(
                self.team, self.component_name, self.version,
            )
        s3_object = s3_resource.Object(
            self._release_bucket,
            release_key,
        )
        s3_object.upload_file(
            release_archive,
            ExtraArgs={'Metadata': {
                'cdflow_image_digest': os.environ['CDFLOW_IMAGE_DIGEST'],
            }},
        )

    def _run_terraform_init(self, base_dir, infra_dir):
        logger.debug(
            'Getting Terraform modules defined in {}'.format(infra_dir)
        )
        check_call([
            TERRAFORM_BINARY, 'init', infra_dir
        ], cwd=base_dir)

    def _copy_platform_configs(self, base_dir):
        path_in_release = '{}/{}'.format(base_dir, PLATFORM_CONFIG_BASE_PATH)
        for platform_config_path in self._platform_config_paths:
            logger.debug('Copying {} to {}'.format(
                platform_config_path, path_in_release
            ))
            _copy_platform_config(platform_config_path, path_in_release)

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
