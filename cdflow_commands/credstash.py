from subprocess import check_output
import os


def get_secrets(env_name, team, component_name, boto_session):
    credentials = boto_session.get_credentials()
    env = os.environ.copy()
    env.update({
        'AWS_ACCESS_KEY_ID': credentials.access_key,
        'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
        'AWS_SESSION_TOKEN': credentials.token
    })

    command = [
        'credstash', '-t', 'credstash-{}'.format(team),
        '-r', boto_session.region_name
    ]
    prefix = 'deploy.{}.{}.'.format(env_name, component_name)

    return {
        name: check_output(command + ['get', prefix + name], env=env)[:-1]
        for name in [
            line[len(prefix):].split(' ', 2)[0]
            for line
            in check_output(command + ['list'], env=env).splitlines()
            if line.startswith(prefix)
        ]
    }
