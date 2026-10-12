# -*- coding: utf-8 -*-
"""

    Normalising provider groups into gate's own vocabulary.

    An identity provider hands back long directory group names carrying an
    environment-specific prefix. Everything downstream -- tokens, headers, the
    policy layer -- speaks a compact `service:role` form instead, and this is
    the only module that knows what the provider's shape looks like.

"""


# imports
# -------
from gate.config import config
from gate.logging import api as log


# vocabulary
# ----------
# the roles a group may end in. a prefixed group ending in anything else
# cannot be expressed as `service:role` and is dropped, which keeps the
# vocabulary total -- every entry the policy layer sees is well formed.
ROLES = ('read', 'write', 'admin')


# helpers
# -------
def convert(group):
    """
    Convert one provider group into `service:role`, or None if it is not ours.

    Args:
        group (str) - Group name as the provider spelled it.
    """
    name = group.strip().lower()
    prefix = config.GROUP_PREFIX.lower()

    # the prefix is an allowlist: a group without it belongs to some other
    # part of the directory and is none of gate's business
    if prefix:
        if not name.startswith(prefix):
            return None
        name = name[len(prefix):]

    # split on the last dash, so a service whose name contains one survives
    service, dash, role = name.rpartition('-')
    if not dash or not service or role not in ROLES:
        return None

    return f'{service}:{role}'


# normalise
# ---------
def normalise(groups):
    """
    Convert a provider's group list into gate's vocabulary.

    Returns a sorted list of unique `service:role` strings. Sorting makes the
    claim deterministic, so the same identity always mints an identical token
    body and tests do not depend on the provider's ordering.

    Args:
        groups (list) - Group names as the provider spelled them.
    """
    converted = set()
    dropped = []

    for group in groups or []:
        entry = convert(group)
        if entry is None:
            dropped.append(group)
            continue
        converted.add(entry)

    # dropping is normal and expected, but silently discarding a group the
    # operator believed was granting access is a bad afternoon
    if dropped:
        log.debug(f'dropped {len(dropped)} group(s) outside the vocabulary: {dropped}')

    return sorted(converted)
