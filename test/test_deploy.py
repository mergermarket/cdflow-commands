import unittest
from collections import namedtuple
from contextlib import ExitStack
from string import ascii_letters, digits

from hypothesis import given
from hypothesis.strategies import dictionaries, fixed_dictionaries, text
from mock import patch, Mock, MagicMock

from cdflow_commands.account import AccountScheme, Account
from cdflow_commands.deploy import Deploy


BotoCredentials = namedtuple(
    'BotoCredentials', ['access_key', 'secret_key', 'token']
)


ALNUM = ascii_letters + digits


class TestDeploy(unittest.TestCase):

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'account_alias': text(alphabet=ALNUM),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_deploy_runs_terraform_plan(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = fixtures['secrets']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account = MagicMock(spec=Account)
        account.alias = account_alias
        account_scheme.account_for_environment.return_value = account

        boto_session = Mock()
        boto_session.region_name = 'us-north-4'
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}

            def mock_path_exists(path):
                if path == 'config/{}.json'.format(environment):
                    return True

            path_exists.side_effect = mock_path_exists

            deploy.run()

            check_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var', 'aws_region={}'.format(aws_region),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    '-var-file', 'config/{}.json'.format(environment),
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                }
            )

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'account_alias': text(alphabet=ALNUM),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_deploy_runs_terraform_apply(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = fixtures['secrets']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account = MagicMock(spec=Account)
        account.alias = account_alias
        account_scheme.account_for_environment.return_value = account

        boto_session = Mock()
        boto_session.region_name = 'us-north-4'
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            stack.enter_context(patch('cdflow_commands.deploy.path.exists'))
            stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            mock_os.environ = {}

            deploy.run()

            check_call.assert_any_call(
                [
                    'terraform', 'apply', '-input=false',
                    'plan-{}'.format(utcnow)
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                }
            )

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'account_alias': text(alphabet=ALNUM),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_plan_only_does_not_apply(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = fixtures['secrets']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account = MagicMock(spec=Account)
        account.alias = account_alias
        account_scheme.account_for_environment.return_value = account

        boto_session = Mock()
        boto_session.region_name = 'us-north-4'
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            def mock_path_exists(path):
                if path == 'config/{}.json'.format(environment):
                    return True

            path_exists.side_effect = mock_path_exists

            mock_os.environ = {}

            deploy.run(plan_only=True)

            check_call.assert_called_once_with(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var', 'aws_region={}'.format(aws_region),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    '-var-file', 'config/{}.json'.format(environment),
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                }
            )

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'account_alias': text(alphabet=ALNUM),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_environment_config_not_added_if_not_present(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = fixtures['secrets']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account = MagicMock(spec=Account)
        account.alias = account_alias
        account_scheme.account_for_environment.return_value = account

        boto_session = Mock()
        boto_session.region_name = 'us-north-4'
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}

            path_exists.return_value = False

            deploy.run()

            check_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var', 'aws_region={}'.format(aws_region),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                }
            )

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'account_alias': text(alphabet=ALNUM),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_global_environment_config_added_if_present(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = fixtures['secrets']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account = MagicMock(spec=Account)
        account.alias = account_alias
        account_scheme.account_for_environment.return_value = account

        boto_session = Mock()
        boto_session.region_name = 'us-north-4'
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}

            def mock_path_exists(path):
                if path == 'config/common.json':
                    return True
                else:
                    return False
            path_exists.side_effect = mock_path_exists

            deploy.run()

            check_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var', 'aws_region={}'.format(aws_region),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    '-var-file', 'config/common.json',
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                }
            )
