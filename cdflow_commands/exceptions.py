class UserError(Exception):
    _message = 'User error'

    def __str__(self):
        return self._message
