from os.path import join
import random
import unittest
from collections import namedtuple
from contextlib import ExitStack
from string import ascii_letters, digits
from subprocess import PIPE

from cdflow_commands.account import Account, AccountScheme
from cdflow_commands.deploy import Deploy
from cdflow_commands.exceptions import UserFacingError
from hypothesis import given
from hypothesis.strategies import (
    dictionaries, fixed_dictionaries, text
)
from mock import MagicMock, Mock, patch

BotoCredentials = namedtuple(
    'BotoCredentials', ['access_key', 'secret_key', 'token']
)


ALNUM = ascii_letters + digits


def create_mock_account(alias):
    account = MagicMock(spec=Account)
    account.alias = alias
    return account


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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
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

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}
            check_call.return_value = ''

            def mock_path_exists(path):
                if path == 'config/{}.json'.format(environment):
                    return True

            path_exists.side_effect = mock_path_exists

            deploy.run()

            popen_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
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
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
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
        'secrets': dictionaries(
            keys=text(min_size=2), values=text(min_size=8).filter(
                lambda v: len(v.replace('*', '')) > 0
            ),
            min_size=1,
            max_size=4,
        ),
        'plan_output': text(alphabet=ALNUM, min_size=16)
    }))
    def test_deploy_runs_terraform_apply_obfuscates_secrets(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = {'secrets': fixtures['secrets']}
        plan_output = fixtures['plan_output']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
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
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )
            mock_stdout = stack.enter_context(
                patch('cdflow_commands.deploy.sys.stdout')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    (
                        plan_output + random.choice(list(
                            secrets['secrets'].values()
                        ))
                    ).encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

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
                    'AWS_DEFAULT_REGION': aws_region,
                }
            )

            for value in secrets['secrets'].values():
                assert value not in mock_stdout.write.call_args[0][0]

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'account_alias': text(alphabet=ALNUM),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(
            keys=text(min_size=2), values=text(min_size=8).filter(
                lambda v: len(v.replace('*', '')) > 0
            ),
            min_size=1,
            max_size=4,
        ),
        'plan_output': text(alphabet=ALNUM, min_size=16)
    }))
    def test_deploy_does_not_run_apply_if_plan_fails(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        account_alias = fixtures['account_alias']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.default_region = aws_region
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, {}, account_scheme, boto_session,
        )

        with ExitStack() as stack:
            stack.enter_context(patch('cdflow_commands.deploy.path.exists'))
            stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 1
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            mock_os.environ = {}

            self.assertRaises(UserFacingError, deploy.run)

            for call_args in check_call.call_args_list:
                args, kwargs = call_args
                command_args = args[0]
                if command_args[0] == 'terraform':
                    assert not command_args[1] == 'apply'

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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
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
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            def mock_path_exists(path):
                if path == 'config/{}.json'.format(environment):
                    return True

            path_exists.side_effect = mock_path_exists

            mock_os.environ = {}

            deploy.run(plan_only=True)

            popen_call.assert_called_once_with(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
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
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
            )
            check_call.assert_not_called()

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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
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
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}

            path_exists.return_value = False

            deploy.run()

            popen_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
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
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
            )

            check_call.assert_called()

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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
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
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

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

            popen_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
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
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
            )
            check_call.assert_called()

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
    def test_path_to_infrastructure_can_be_injected(self, fixtures):
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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        path_to_infra = '/tmp/my-infra-code/'

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
            path_to_infra,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
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

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}
            check_call.return_value = ''

            def mock_path_exists(path):
                if path == 'config/{}.json'.format(environment):
                    return True

            path_exists.side_effect = mock_path_exists

            deploy.run()

            popen_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    '-var-file', 'config/{}.json'.format(environment),
                    path_to_infra,
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
            )

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM, min_size=1),
        'release_path': text(alphabet=ALNUM, min_size=1),
        'account_alias': text(alphabet=ALNUM, min_size=1),
        'utcnow': text(alphabet=digits, min_size=1),
        'access_key': text(alphabet=ALNUM, min_size=1),
        'secret_key': text(alphabet=ALNUM, min_size=1),
        'token': text(alphabet=ALNUM, min_size=1),
        'aws_region': text(alphabet=ALNUM, min_size=1),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_base_path_to_config_can_be_injected(self, fixtures):
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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        config_base_path = '/tmp/config/'

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
            config_base_path=config_base_path,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}

            def mock_path_exists(path):
                config_paths = (
                    join(config_base_path, 'common.json'),
                    join(config_base_path, f'{environment}.json'),
                )
                if path in config_paths:
                    return True
                else:
                    return False
            path_exists.side_effect = mock_path_exists

            deploy.run()

            popen_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    '-var-file', join(config_base_path, f'{environment}.json'),
                    '-var-file', join(config_base_path, 'common.json'),
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
            )
            check_call.assert_called()

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM, min_size=1),
        'release_path': text(alphabet=ALNUM, min_size=1),
        'account_alias': text(alphabet=ALNUM, min_size=1),
        'utcnow': text(alphabet=digits, min_size=1),
        'access_key': text(alphabet=ALNUM, min_size=1),
        'secret_key': text(alphabet=ALNUM, min_size=1),
        'token': text(alphabet=ALNUM, min_size=1),
        'aws_region': text(alphabet=ALNUM, min_size=1),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_interactive_flag_allows_input_and_dynamic_plan_file(
        self, fixtures,
    ):
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
        account_scheme.account_for_environment.return_value = \
            create_mock_account(account_alias)

        boto_session = Mock()
        boto_session.region_name = aws_region
        credentials = BotoCredentials(access_key, secret_key, token)
        boto_session.get_credentials.return_value = credentials

        deploy = Deploy(
            environment, release_path, secrets, account_scheme, boto_session,
            interactive=True,
        )

        with ExitStack() as stack:
            path_exists = stack.enter_context(
                patch('cdflow_commands.deploy.path.exists')
            )
            check_call = stack.enter_context(
                patch('cdflow_commands.deploy.check_call')
            )
            popen_call = stack.enter_context(
                patch('cdflow_commands.deploy.Popen')
            )
            NamedTemporaryFile = stack.enter_context(
                patch('cdflow_commands.deploy.NamedTemporaryFile')
            )
            mock_os = stack.enter_context(patch('cdflow_commands.deploy.os'))
            time = stack.enter_context(
                patch('cdflow_commands.deploy.time')
            )

            time.return_value = utcnow

            process_mock = Mock()
            process_mock.poll.return_value = 0
            attrs = {
                'communicate.return_value': (
                    ''.encode('utf-8'),
                    ''.encode('utf-8')
                )
            }
            process_mock.configure_mock(**attrs)
            popen_call.return_value = process_mock

            secret_file_path = NamedTemporaryFile.return_value.__enter__\
                .return_value.name

            mock_os.environ = {}

            def mock_path_exists(path):
                return False

            path_exists.side_effect = mock_path_exists

            deploy.run()

            popen_call.assert_any_call(
                [
                    'terraform', 'plan',
                    '-var', 'env={}'.format(environment),
                    '-var-file', 'release.json',
                    '-var-file', 'platform-config/{}/{}.json'.format(
                        account_alias, boto_session.region_name
                    ),
                    '-var-file', secret_file_path,
                    '-out', 'plan-$(date +%s)',
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                    'AWS_DEFAULT_REGION': aws_region,
                },
                stdout=PIPE, stderr=PIPE
            )
            check_call.assert_called()
