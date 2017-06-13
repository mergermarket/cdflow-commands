class Account:

    def __init__(self, alias, id, role):
        self.alias = alias
        self.id = id
        self.role = role


class AccountScheme:

    def __init__(self, accounts, release_account, default_region):
        self.accounts = accounts
        self.release_account = release_account
        self.default_region = default_region

    def create(raw_scheme):
        accounts = {
            alias: Account(alias, account['id'], account['role'])
            for alias, account
            in raw_scheme['accounts'].items()
        }

        return AccountScheme(
            set(accounts.values()),
            accounts[raw_scheme['release-account']],
            raw_scheme['default-region']
        )

    @property
    def account_ids(self):
        return [account.id for account in self.accounts]
