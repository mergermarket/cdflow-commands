import os
from subprocess import check_call


class Destroy(object):

    def __init__(
        self, boto_session, component_name, environment_name, bucket_name
    ):
        self._boto_session = boto_session
        self._aws_region = boto_session.region_name
        self._component_name = component_name
        self._environment_name = environment_name
        self._bucket_name = bucket_name

    @property
    def _terraform_parameters(self):
        return [
            '-var', 'aws_region={}'.format(self._aws_region),
            '/cdflow/tf-destroy'
        ]

    def run(self):
        credentials = self._boto_session.get_credentials()
        aws_credentials = {
            'AWS_ACCESS_KEY_ID': credentials.access_key,
            'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
            'AWS_SESSION_TOKEN': credentials.token
        }
        env = os.environ.copy()
        env.update(aws_credentials)
        check_call(
            ['terraform', 'plan', '-destroy'] + self._terraform_parameters,
            env=env
        )
        check_call(
            ['terraform', 'destroy', '-force'] + self._terraform_parameters,
            env=env
        )
        boto_s3_client = self._boto_session.client('s3')
        boto_s3_client.delete_object(
            Bucket=self._bucket_name,
            Key='{}/{}/terraform.tfstate'.format(
                self._environment_name, self._component_name
            )
        )
