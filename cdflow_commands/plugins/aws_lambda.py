import os
from zipfile import ZipFile
from cdflow_commands.config import (
    assume_role, get_role_session_name
)


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
            self._metadata
        )
        release.create()


class Release():
    def __init__(
        self,
        global_config,
        boto_s3_client,
        component_name,
        metadata
    ):
        self._global_config = global_config
        self._boto_s3_client = boto_s3_client
        self._component_name = component_name
        self._metadata = metadata

    def create(self):
        zip = ZipFile(self._component_name + '.zip', 'x')

        for dirname, subdirs, files in os.walk('.'):
            zip.write(dirname)
            for filename in files:
                zip.write(os.path.join(dirname, filename))
        zip.close()

        self._boto_s3_client.create_bucket(
            ACL='private',
            Bucket=self._metadata.team,
            CreateBucketConfiguration={
                'LocationConstraint': self._metadata.aws_region
            }
        )

        self._boto_s3_client.put_object(
            Body=zip,
            Bucket=self._metadata.team,
            Key=self._component_name
        )
