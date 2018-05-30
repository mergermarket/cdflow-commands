import unittest
from string import ascii_letters, digits

from hypothesis import given
from hypothesis.strategies import (
    composite, fixed_dictionaries, lists, text, booleans
)

from test.test_config import ROLE_SAFE_ALPHABET

from cdflow_commands.account import Account, AccountScheme


@composite
def account(draw):
    return draw(fixed_dictionaries({
        'id': text(alphabet=digits, min_size=3),
        'alias': text(alphabet=ascii_letters+digits, min_size=1),
        'role': text(alphabet=ROLE_SAFE_ALPHABET, min_size=1),
    }))


@composite
def accounts(draw, min_size=1):
    accounts = []
    ids = set()
    aliases = set()
    while len(accounts) < min_size:
        candidate = draw(account())
        if candidate['id'] in ids or candidate['alias'] in aliases:
            continue
        ids.add(candidate['id'])
        aliases.add(candidate['alias'])
        accounts.append(candidate)
    return accounts


def dedupe_accounts(accounts):
    aliases = set()
    for account in accounts:
        if account['alias'] not in aliases:
            aliases.add(account['alias'])
        else:
            return False
    return True


class TestAccount(unittest.TestCase):

    @given(account())
    def test_account(self, fixtures):
        account = Account(**fixtures)

        assert account.id == fixtures['id']
        assert account.alias == fixtures['alias']
        assert account.role == fixtures['role']


class TestAccountScheme(unittest.TestCase):

    @given(fixed_dictionaries({
        'account': account(),
        'region': text(min_size=1),
        'release-bucket': text(),
        'lambda-bucket': text(),
        'classic-metadata-handling': booleans(),
        'backend-s3-bucket': text(),
        'backend-s3-dynamodb-table': text(),
    }))
    def test_create_account_scheme_from_json(self, fixtures):
        raw_scheme = {
            'accounts': {
                fixtures['account']['alias']: {
                    'id': fixtures['account']['id'],
                    'role': fixtures['account']['role'],
                }
            },
            'release-bucket': fixtures['release-bucket'],
            'lambda-bucket': fixtures['lambda-bucket'],
            'classic-metadata-handling': fixtures['classic-metadata-handling'],
            'release-account': fixtures['account']['alias'],
            'default-region': fixtures['region'],
            'environments': {},
            'terraform-backend-s3-bucket': fixtures['backend-s3-bucket'],
            'terraform-backend-s3-dynamodb-table':
            fixtures['backend-s3-dynamodb-table'],
        }

        account_scheme = AccountScheme.create(raw_scheme)
        assert account_scheme.release_account.id == fixtures['account']['id']
        assert account_scheme.release_account.role == \
            fixtures['account']['role']
        assert account_scheme.default_region == fixtures['region']
        assert account_scheme.accounts == {account_scheme.release_account}
        assert account_scheme.release_bucket == fixtures['release-bucket']
        assert account_scheme.lambda_bucket == fixtures['lambda-bucket']
        assert account_scheme.classic_metadata_handling == \
            fixtures['classic-metadata-handling']
        assert account_scheme.backend_s3_bucket == \
            fixtures['backend-s3-bucket']
        assert account_scheme.backend_s3_dynamodb_table == \
            fixtures['backend-s3-dynamodb-table']

    @given(lists(
            elements=account(),
            min_size=1,
            unique_by=lambda a: a['id'],
    ).filter(dedupe_accounts))
    def test_deploy_account_ids(self, accounts):
        raw_scheme = {
            'accounts': {
                a['alias']: {'id': a['id'], 'role': a['role']}
                for a in accounts
            },
            'release-account': accounts[0]['alias'],
            'release-bucket': 'releases',
            'default-region': 'eu-west-69',
            'environments': {},
            'terraform-backend-s3-bucket': 'tfstate-bucket',
            'terraform-backend-s3-dynamodb-table': 'tflocks-table',
        }

        account_scheme = AccountScheme.create(raw_scheme)

        expected_account_ids = list(sorted(
            account['id'] for account in accounts
        ))

        assert list(sorted(account_scheme.account_ids)) == expected_account_ids

    @given(fixed_dictionaries({
        'accounts': lists(
            elements=account(),
            min_size=2,
            unique_by=lambda a: a['id'],
        ).filter(dedupe_accounts),
        'environments': lists(
            elements=text(alphabet=ascii_letters+digits, min_size=2),
            unique=True, min_size=2,
        ),
    }))
    def test_environment_account_mapping(self, fixtures):
        accounts = fixtures['accounts']
        dev_account = accounts[0]['alias']
        live_account = accounts[-1]['alias']
        live_environment = fixtures['environments'][0]
        environments = {
            live_environment: live_account,
        }
        for environment in fixtures['environments'][1:]:
            environments[environment] = dev_account

        raw_scheme = {
            'accounts': {
                a['alias']: {'id': a['id'], 'role': a['role']}
                for a in accounts
            },
            'release-account': dev_account,
            'release-bucket': 'releases',
            'default-region': 'eu-west-69',
            'environments': environments,
            'terraform-backend-s3-bucket': 'tfstate-bucket',
            'terraform-backend-s3-dynamodb-table': 'tflocks-table',
        }

        account_scheme = AccountScheme.create(raw_scheme)

        assert account_scheme.account_for_environment(live_environment).alias \
            == live_account
        for environment in fixtures['environments'][1:]:
            assert account_scheme.account_for_environment(environment).alias \
                == dev_account

    @given(fixed_dictionaries({
        'accounts': lists(
            elements=account(),
            min_size=2,
            unique_by=lambda a: a['id'],
        ).filter(dedupe_accounts),
        'environments': lists(
            elements=text(alphabet=ascii_letters+digits, min_size=2),
            unique=True, min_size=2,
        ),
    }))
    def test_environment_account_mapping_with_default(self, fixtures):
        accounts = fixtures['accounts']
        dev_account = accounts[0]['alias']
        live_account = accounts[-1]['alias']
        live_environment = fixtures['environments'][0]
        environments = {
            live_environment: live_account,
            '*': dev_account,
        }

        raw_scheme = {
            'accounts': {
                a['alias']: {'id': a['id'], 'role': a['role']}
                for a in accounts
            },
            'release-account': dev_account,
            'release-bucket': 'releases',
            'default-region': 'eu-west-69',
            'environments': environments,
            'terraform-backend-s3-bucket': 'tfstate-bucket',
            'terraform-backend-s3-dynamodb-table': 'tflocks-table',
        }

        account_scheme = AccountScheme.create(raw_scheme)

        assert account_scheme.account_for_environment(live_environment).alias \
            == live_account
        for environment in fixtures['environments'][1:]:
            assert account_scheme.account_for_environment(environment).alias \
                == dev_account
