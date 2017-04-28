import os
from zipfile import ZipFile
from cdflow_commands.config import (
    assume_role, get_role_session_name
)
from cdflow_commands.deploy import Deploy


def build_lambda_plugin(
    environment_name, component_name, version,
    metadata, global_config, root_session
):
    return LambdaPlugin(
        environment_name, component_name, version,
        metadata, global_config, root_session
    )


class LambdaPlugin():
    def __init__(
        self,
        environment_name,
        component_name,
        version,
        metadata,
        global_config,
        root_session
    ):
        self._environment_name = environment_name
        self._component_name = component_name
        self._version = version
        self._metadata = metadata
        self._global_config = global_config
        self._boto_s3_client = assume_role(
            root_session,
            global_config.dev_account_id,
            get_role_session_name(os.environ)
        ).client('s3')

    def release(self):
        release = Release(
            self._global_config,
            self._boto_s3_client,
            self._component_name,
            self._metadata,
            self._version
        )
        release.create()

    def deploy(self):
        deploy = Deploy(
            self._component_name,
            self._environment_name,
            self._version,
            self._global_config
        )
        deploy.run()


class Release():
    def __init__(
        self,
        global_config,
        boto_s3_client,
        component_name,
        metadata,
        version
    ):
        self._global_config = global_config
        self._boto_s3_client = boto_s3_client
        self._component_name = component_name
        self._metadata = metadata
        self._version = version

    def create(self):
        zip = ZipFile(self._component_name + '.zip', 'x')

        for dirname, subdirs, files in os.walk(self._component_name):
            zip.write(dirname)
            for filename in files:
                zip.write(os.path.join(dirname, filename))
        zip.close()
        bucket_list = self._boto_s3_client.list_buckets()
        bucket_names = [
            bucket['Name']
            for bucket in bucket_list['Buckets']
            if bucket['Name'] == 'mmg-lambdas-{}'.format(self._metadata.team)
        ]
        if not bucket_names:
            self._boto_s3_client.create_bucket(
                ACL='private',
                Bucket='mmg-lambdas-{}'.format(self._metadata.team),
                CreateBucketConfiguration={
                    'LocationConstraint': self._metadata.aws_region
                }
            )
        self._boto_s3_client.upload_file(
            zip.filename,
            'mmg-lambdas-{}'.format(self._metadata.team),
            '{}/{}.zip'.format(self._component_name, self._version)
        )

        os.remove(zip.filename)
