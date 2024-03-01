"""
********************************************************************************
console
********************************************************************************

Text console UI helpers and patterns, e.g. ‘Y/n’ prompts and the like.

.. currentmodule:: compas_invocations2.console

.. autosummary::
    :toctree: generated/
    :nosignatures:

    confirm
    chdir

"""

import contextlib
import os
import sys


# NOTE: originally taken from invocations https://github.com/pyinvoke/invocations/blob/main/invocations/console.py
def confirm(question, assume_yes=True):
    """
    Ask user a yes/no question and return their response as a boolean.

    ``question`` should be a simple, grammatically complete question such as
    "Do you wish to continue?", and will have a string similar to ``" [Y/n] "``
    appended automatically. This function will *not* append a question mark for
    you.
    By default, when the user presses Enter without typing anything, "yes" is
    assumed. This can be changed by specifying ``assume_yes=False``.

    .. note::

        If the user does not supply input that is (case-insensitively) equal to
        "y", "yes", "n" or "no", they will be re-prompted until they do.

    Parameters
    ----------
    question : str
        The question part of the prompt.
    assume_yes : bool
        Whether to assume the affirmative answer by default. Defaults to ``True``.

    Returns
    -------
    bool
    """
    if assume_yes:
        suffix = "Y/n"
    else:
        suffix = "y/N"

    while True:
        response = input("{} [{}] ".format(question, suffix))
        response = response.lower().strip()

        if not response:
            return assume_yes

        if response in ["y", "yes"]:
            return True

        if response in ["n", "no"]:
            return False

        err = "Focus, kid! It is either (y)es or (n)o"
        print(err, file=sys.stderr)


@contextlib.contextmanager
def chdir(dirname=None):
    """Context-manager syntax to change to a directory and return to the current one afterwards."""
    current_dir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(current_dir)
