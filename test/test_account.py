import unittest
from string import ascii_letters, digits

from hypothesis import given
from hypothesis.strategies import composite, fixed_dictionaries, lists, text

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
            'release-account': fixtures['account']['alias'],
            'default-region': fixtures['region'],
            'environments': {},
        }

        account_scheme = AccountScheme.create(raw_scheme)
        assert account_scheme.release_account.id == fixtures['account']['id']
        assert account_scheme.release_account.role == \
            fixtures['account']['role']
        assert account_scheme.default_region == fixtures['region']
        assert account_scheme.accounts == {account_scheme.release_account}
        assert account_scheme.release_bucket == fixtures['release-bucket']

    @given(accounts())
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
        }

        account_scheme = AccountScheme.create(raw_scheme)

        expected_account_ids = list(sorted(
            account['id'] for account in accounts
        ))

        assert list(sorted(account_scheme.account_ids)) == expected_account_ids

    @given(fixed_dictionaries({
        'accounts': accounts(min_size=2),
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
        }

        account_scheme = AccountScheme.create(raw_scheme)

        assert account_scheme.account_for_environment(live_environment).alias \
            == live_account
        for environment in fixtures['environments'][1:]:
            assert account_scheme.account_for_environment(environment).alias \
                == dev_account

    @given(fixed_dictionaries({
        'accounts': accounts(min_size=2),
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
        }

        account_scheme = AccountScheme.create(raw_scheme)

        assert account_scheme.account_for_environment(live_environment).alias \
            == live_account
        for environment in fixtures['environments'][1:]:
            assert account_scheme.account_for_environment(environment).alias \
                == dev_account

    @given(fixed_dictionaries({
        'account_prefixes': lists(
            elements=text(alphabet=ascii_letters+digits, min_size=2),
            unique=True, min_size=2,
        ),
        'accounts': accounts(min_size=4),
        'environments': lists(
            elements=text(alphabet=ascii_letters+digits, min_size=2),
            unique=True, min_size=2,
        ),
    }))
    def test_environment_accont_mapping_with_multiple_accounts(self, fixtures):
        # Given
        accounts = fixtures['accounts']
        prefix_a = fixtures['account_prefixes'][0]
        prefix_b = fixtures['account_prefixes'][1]
        dev_account_a = accounts[0]['alias']
        live_account_a = accounts[1]['alias']
        dev_account_b = accounts[2]['alias']
        live_account_b = accounts[3]['alias']
        live_environment = fixtures['environments'][0]
        environments = {
            live_environment: {
                prefix_a: live_account_a, prefix_b: live_account_b
            },
            '*': {
                prefix_a: dev_account_a, prefix_b: dev_account_b
            },
        }

        raw_scheme = {
            'accounts': {
                a['alias']: {'id': a['id'], 'role': a['role']}
                for a in accounts
            },
            'release-account': dev_account_a,
            'release-bucket': 'releases',
            'default-region': 'eu-west-69',
            'environments': environments,
        }

        # When
        account_scheme = AccountScheme.create(raw_scheme)

        # Then
        assert account_scheme.multiple_account_deploys
        for envionment in fixtures['environments']:
            with self.assertRaisesRegex(Exception, 'multiple account deploy'):
                account_scheme.account_for_environment(envionment)
        live_env_accounts = account_scheme.accounts_for_environment(
            fixtures['environments'][0]
        )
        assert live_env_accounts[prefix_a].alias == live_account_a
        assert live_env_accounts[prefix_b].alias == live_account_b
        for environment in fixtures['environments'][1:]:
            env_accounts = account_scheme.accounts_for_environment(environment)
            assert env_accounts[prefix_a].alias == dev_account_a
            assert env_accounts[prefix_b].alias == dev_account_b
