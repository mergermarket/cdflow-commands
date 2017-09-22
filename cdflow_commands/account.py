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
        default_region, environment_mapping, multiple_account_deploys
    ):
        self.accounts = accounts
        self.release_account = release_account
        self.release_bucket = release_bucket
        self.default_region = default_region
        self._environment_mapping = environment_mapping
        self.multiple_account_deploys = multiple_account_deploys

    @classmethod
    def _get_env_mapping(cls, raw_scheme, accounts):
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
        return environment_mapping

    @classmethod
    def _get_multiple_account_deploys_env_mapping(cls, raw_scheme, accounts):
        default_env_aliases = raw_scheme['environments'].get(
            cls.DEFAULT_ENV_KEY
        )

        environment_mapping = {
            env: {
                prefix: accounts[raw_scheme['environments'][env][prefix]]
                for prefix in raw_scheme['environments'][env]
            }
            for env in raw_scheme['environments']
        }

        if default_env_aliases:
            default_env = {
                prefix: accounts[
                    raw_scheme['environments'][cls.DEFAULT_ENV_KEY][prefix]
                ]
                for prefix
                in raw_scheme['environments'][cls.DEFAULT_ENV_KEY]
            }
            environment_mapping = defaultdict(
                lambda: default_env, environment_mapping
            )
        return environment_mapping

    @classmethod
    def create(cls, raw_scheme):
        accounts = {
            alias: Account(alias, account['id'], account['role'])
            for alias, account
            in raw_scheme['accounts'].items()
        }

        environment_value_types = [
            type(a) for a in raw_scheme['environments'].values()
        ]
        multiple_account_deploys = False

        if all([t == str for t in environment_value_types]):
            environment_mapping = cls._get_env_mapping(
                raw_scheme, accounts
            )
        elif all([t == dict for t in environment_value_types]):
            multiple_account_deploys = True
            environment_mapping = \
                cls._get_multiple_account_deploys_env_mapping(
                    raw_scheme, accounts
                )
        else:
            raise Exception('mixed environment types in account scheme')

        return AccountScheme(
            set(accounts.values()),
            accounts[raw_scheme['release-account']],
            raw_scheme['release-bucket'],
            raw_scheme['default-region'],
            environment_mapping,
            multiple_account_deploys
        )

    @property
    def account_ids(self):
        return [account.id for account in self.accounts]

    def account_for_environment(self, environment):
        if self.multiple_account_deploys:
            raise Exception(
                'account_for_environment not suported for '
                'multiple account deploys'
            )
        return self._environment_mapping[environment]

    def accounts_for_environment(self, environment):
        if not self.multiple_account_deploys:
            raise Exception(
                'accounts_for_environment not support when not a '
                'multiple account deploy'
            )
        return self._environment_mapping[environment]
