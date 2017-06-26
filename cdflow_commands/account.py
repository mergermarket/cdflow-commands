from collections import defaultdict


class Account:

    def __init__(self, alias, id, role):
        self.alias = alias
        self.id = id
        self.role = role


class AccountScheme:

    DEFAULT_ENV_KEY = '*'

    def __init__(
        self, accounts, release_account, release_bucket,
        default_region, environment_mapping
    ):
        self.accounts = accounts
        self.release_account = release_account
        self.release_bucket = release_bucket
        self.default_region = default_region
        self._environment_mapping = environment_mapping

    @classmethod
    def create(cls, raw_scheme):
        accounts = {
            alias: Account(alias, account['id'], account['role'])
            for alias, account
            in raw_scheme['accounts'].items()
        }

        default_env_alias = raw_scheme['environments'].get(cls.DEFAULT_ENV_KEY)

        environment_mapping = {
            env: accounts[raw_scheme['environments'][env]]
            for env in raw_scheme['environments']
        }

        if default_env_alias:
            default_env = accounts[default_env_alias]
            environment_mapping = defaultdict(
                lambda: default_env, environment_mapping
            )

        return AccountScheme(
            set(accounts.values()),
            accounts[raw_scheme['release-account']],
            raw_scheme['release-bucket'],
            raw_scheme['default-region'],
            environment_mapping,
        )

    @property
    def account_ids(self):
        return [account.id for account in self.accounts]

    def account_for_environment(self, environment):
        return self._environment_mapping[environment]
