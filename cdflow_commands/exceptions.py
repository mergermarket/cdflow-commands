class CDFlowError(Exception):
    pass


class UserFacingError(CDFlowError):
    pass


class FixedMessageError(CDFlowError):
    _message = 'Error'

    def __str__(self):
        return self._message


class UserFacingFixedMessageError(UserFacingError, FixedMessageError):
    pass
