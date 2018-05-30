from collections import defaultdict


class Account:

    def __init__(self, alias, id, role):
        self.alias = alias
        self.id = id
        self.role = role


class AccountScheme:

    DEFAULT_ENV_KEY = '*'

    def __init__(
        self, raw_scheme, accounts, release_account, release_bucket,
        lambda_bucket, default_region, environment_mapping,
        classic_metadata_handling, backend_s3_bucket, backend_s3_dynamodb_table
    ):
        self.raw_scheme = raw_scheme
        self.accounts = accounts
        self.release_account = release_account
        self.release_bucket = release_bucket
        self.lambda_bucket = lambda_bucket
        self.default_region = default_region
        self._environment_mapping = environment_mapping
        self.classic_metadata_handling = classic_metadata_handling
        self.backend_s3_bucket = backend_s3_bucket
        self.backend_s3_dynamodb_table = backend_s3_dynamodb_table

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
    def create(cls, raw_scheme):
        accounts = {
            alias: Account(alias, account['id'], account['role'])
            for alias, account
            in raw_scheme['accounts'].items()
        }

        environment_value_types = (
            type(a) for a in raw_scheme['environments'].values()
        )

        assert all(t is str for t in environment_value_types), \
            'environment mapping values should be strings'

        environment_mapping = cls._get_env_mapping(
            raw_scheme, accounts
        )

        return AccountScheme(
            raw_scheme,
            set(accounts.values()),
            accounts[raw_scheme['release-account']],
            raw_scheme['release-bucket'],
            raw_scheme.get('lambda-bucket', ''),
            raw_scheme['default-region'],
            environment_mapping,
            raw_scheme.get('classic-metadata-handling', False),
            raw_scheme['terraform-backend-s3-bucket'],
            raw_scheme['terraform-backend-s3-dynamodb-table'],
        )

    @property
    def account_ids(self):
        return [account.id for account in self.accounts]

    def account_for_environment(self, environment):
        return self._environment_mapping[environment]
