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
        'region': text(min_size=1)
    }))
    def test_create_account_scheme_from_json(self, fixtures):
        raw_scheme = {
            'accounts': {
                fixtures['account']['alias']: {
                    'id': fixtures['account']['id'],
                    'role': fixtures['account']['role'],
                }
            },
            'release-account': fixtures['account']['alias'],
            'default-region': fixtures['region'],
        }

        account_scheme = AccountScheme.create(raw_scheme)
        assert account_scheme.release_account.id == fixtures['account']['id']
        assert account_scheme.release_account.role == \
            fixtures['account']['role']
        assert account_scheme.default_region == fixtures['region']
        assert account_scheme.accounts == {account_scheme.release_account}

    @given(lists(
        elements=account(), min_size=1,
        unique_by=lambda account: account['alias']
    ))
    def test_deploy_account_ids(self, fixtures):
        accounts = {
            fixture['alias']: {'id': fixture['id'], 'role': fixture['role']}
            for fixture in fixtures
        }

        raw_scheme = {
            'accounts': accounts,
            'release-account': fixtures[0]['alias'],
            'default-region': 'eu-west-69',
        }

        account_scheme = AccountScheme.create(raw_scheme)

        expected_account_ids = list(sorted(
            fixture['id'] for fixture in fixtures
        ))

        assert list(sorted(account_scheme.account_ids)) == expected_account_ids
