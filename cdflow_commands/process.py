from cdflow_commands.exceptions import UserFacingError

from subprocess import check_call as _check_call
from subprocess import Popen as _popen
from subprocess import CalledProcessError


def check_call(*args, **kwargs):
    try:
        _check_call(*args, **kwargs)
    except CalledProcessError as e:
        raise UserFacingError(e)


def popen(*args, **kwargs):
    try:
        _popen(*args, **kwargs)
    except CalledProcessError as e:
        raise UserFacingError(e)
