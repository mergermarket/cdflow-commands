from cdflow_commands.exceptions import UserFacingError

from subprocess import check_call as _check_call, check_output as _check_output
from subprocess import CalledProcessError


def check_call(*args, **kwargs):
    try:
        _check_call(*args, **kwargs)
    except CalledProcessError as e:
        raise UserFacingError(e)


def check_output(*args, **kwargs):
    try:
        return _check_output(*args, **kwargs)
    except CalledProcessError as e:
        raise UserFacingError(e)
