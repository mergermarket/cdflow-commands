import unittest
from collections import namedtuple
from contextlib import ExitStack
from string import ascii_letters, digits
from itertools import chain
import json

from hypothesis import given
from hypothesis.strategies import (
    dictionaries, fixed_dictionaries, text, sampled_from
)
from mock import patch, Mock, MagicMock

from cdflow_commands.account import AccountScheme, Account
from cdflow_commands.deploy import Deploy


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
        account_scheme.multiple_account_deploys = False
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
        account_scheme.multiple_account_deploys = False
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
                    'AWS_DEFAULT_REGION': aws_region,
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
        account_scheme.multiple_account_deploys = False
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
        account_scheme.multiple_account_deploys = False
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
        account_scheme.multiple_account_deploys = False
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
                }
            )

    @given(fixed_dictionaries({
        'environment': text(alphabet=ALNUM),
        'release_path': text(alphabet=ALNUM),
        'roles_by_account_prefix': dictionaries(
            keys=text(alphabet=ALNUM),
            values=text(alphabet=ALNUM),
            min_size=1,
        ),
        'account_postfix': sampled_from(['dev', 'prod']),
        'utcnow': text(alphabet=digits),
        'access_key': text(alphabet=ALNUM),
        'secret_key': text(alphabet=ALNUM),
        'token': text(alphabet=ALNUM),
        'aws_region': text(alphabet=ALNUM),
        'secrets': dictionaries(keys=text(), values=text()),
    }))
    def test_account_role_mappings(self, fixtures):
        environment = fixtures['environment']
        release_path = fixtures['release_path']
        roles_by_account_prefix = fixtures['roles_by_account_prefix']
        account_postfix = fixtures['account_postfix']
        utcnow = fixtures['utcnow']
        access_key = fixtures['access_key']
        secret_key = fixtures['secret_key']
        token = fixtures['token']
        aws_region = fixtures['aws_region']
        secrets = fixtures['secrets']

        account_scheme = MagicMock(spec=AccountScheme)
        account_scheme.multiple_account_deploys = True
        account_scheme.default_region = aws_region

        account_scheme.accounts_for_environment.return_value = [
            create_mock_account(account_prefix + account_postfix)
            for account_prefix in roles_by_account_prefix
        ]

        account_scheme.account_role_mapping.return_value \
            = roles_by_account_prefix

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

            def flatten(x):
                return list(chain(*x))

            check_call.assert_any_call(
                [
                    'terraform', 'plan', '-input=false',
                    '-var', 'env={}'.format(environment),
                    '-var-file', 'release.json',
                ] + flatten([
                    (
                        '-var-file', 'platform-config/{}/{}.json'.format(
                            account_prefix + account_postfix,
                            boto_session.region_name
                        )
                    )
                    for account_prefix in roles_by_account_prefix
                ]) + [
                    '-var-file', secret_file_path,
                    '-out', 'plan-{}'.format(utcnow),
                    '-var', 'accounts={}'.format(json.dumps(
                        roles_by_account_prefix
                    )),
                    'infra',
                ],
                cwd=release_path,
                env={
                    'AWS_ACCESS_KEY_ID': credentials.access_key,
                    'AWS_SECRET_ACCESS_KEY': credentials.secret_key,
                    'AWS_SESSION_TOKEN': credentials.token,
                    'AWS_DEFAULT_REGION': aws_region,
                }
            )
