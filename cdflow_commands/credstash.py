import os
from subprocess import check_output


def get_secrets(env_name, team, component_name, boto_session):
    credentials = boto_session.get_credentials()
    env = os.environ.copy()
    env.update({
        'AWS_ACCESS_KEY_ID': credentials.access_key,
        'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
        'AWS_SESSION_TOKEN': credentials.token
    })

    base_command = [
        'credstash', '-t', 'credstash-{}'.format(team),
        '-r', boto_session.region_name
    ]
    prefix = 'deploy.{}.{}.'.format(env_name, component_name)

    return {
        name[len(prefix):]: _get_secret_value_without_final_newline(
            base_command, env, name
        )
        for name
        in _component_secrets_for_environment(base_command, env, prefix)
    }


def _get_secret_value_without_final_newline(base_command, env, name):
    return check_output(base_command + ['get', name], env=env)[:-1]


def _component_secrets_for_environment(base_command, env, prefix):
    lines = check_output(base_command + ['list'], env=env).splitlines()
    return [
        line.split(' ')[0]
        for line in lines
        if line.startswith(prefix)
    ]
