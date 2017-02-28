import credstash

from botocore.exceptions import ClientError


def get_secrets(env_name, team, component_name, boto_session):
    credentials = boto_session.get_credentials()
    aws_credentials = {
        'aws_access_key_id': credentials.access_key,
        'aws_secret_access_key': credentials.secret_key,
        'aws_session_token': credentials.token
    }

    prefix = 'deploy.{}.{}.'.format(env_name, component_name)
    table_name = "credstash-{}".format(team)

    return {
        name[len(prefix):]: credstash.getSecret(
            name,
            table=table_name,
            region=boto_session.region_name,
            **aws_credentials
        )
        for name
        in _component_secrets_for_environment(
                table_name,
                boto_session.region_name,
                prefix,
                aws_credentials
            )
        }


def _component_secrets_for_environment(
    table, region_name, prefix, aws_credentials
):

    try:
        return [
            secret_data['name']
            for secret_data in credstash.listSecrets(
                table=table,
                region=region_name,
                **aws_credentials
            )
            if secret_data['name'].startswith(prefix)
        ]
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return []
        else:
            raise
