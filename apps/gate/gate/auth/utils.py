# -*- coding: utf-8 -*-
"""

    Supporting functions for the auth endpoints.

    Three jobs, in the order a request meets them. Reading a credential and
    turning it into a caller -- one place decides what counts as a
    credential, rather than each endpoint deciding for itself. Reading the
    request itself, where what arrived and what the caller actually sent are
    not the same thing. Then rendering that caller as the headers nginx
    copies onward, which every endpoint here needs and none of them should
    spell out twice.

"""


# imports
# -------
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, status

from gate.config import config


# constants
# ---------
# the scheme gate accepts, and the challenge it returns with a 401. a bare
# 401 tells a client it failed; the challenge tells it what to try instead,
# which is what makes the status code actionable rather than just true.
SCHEME = 'Bearer'
CHALLENGE = {'WWW-Authenticate': SCHEME}

# the cookie a browser carries its credential in. it holds gate's own token
# rather than claims of its own, so a browser and an api client differ in how
# they arrive and not in what they present. one constant because the writer
# in the callback and the reader below must agree on the name -- spelled
# twice, a login succeeds and no check ever sees it. not configuration until
# a deployment needs a different name.
COOKIE = 'gate_session'

# what login sends as `state` when the caller asked for no destination. the
# provider echoes state back untouched and an empty one does not reliably
# survive the trip, so absence travels as a word. it is not a path, so the
# callback has to recognise it before validating -- `verify_relative_path`
# would refuse it with a 400.
NO_DESTINATION = 'none'

# the identity nginx copies onto the forwarded request. downstream services
# read these instead of the token, so the set is a contract -- adding one is
# easy and removing one breaks whatever quietly came to depend on it.
HEADERS = {
    'X-User-ID': 'sub',
    'X-User-Name': 'name',
    'X-User-Email': 'email',
}


# credentials
# -----------
def unauthorised(detail):
    """
    Build the 401 gate returns for every refused credential.

    Args:
        detail (str) - Why the credential was refused.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=CHALLENGE,
    )


def bearer(request):
    """
    Read the bearer token off a request, or None if there is no credential.

    Raises for a header that is present but malformed. An absent header and
    a broken one are different situations -- the first is a caller who has
    not logged in, the second is a caller doing it wrong -- and only an
    optional check is ever allowed to treat them the same.

    Args:
        request (Request) - Incoming request.
    """
    header = request.headers.get('Authorization')
    if not header:
        return None

    # the scheme is matched case-insensitively: rfc 7235 defines it that way,
    # and clients do vary
    scheme, _, token = header.partition(' ')
    if scheme.lower() != SCHEME.lower():
        raise unauthorised(f'expected {SCHEME} authorization')

    token = token.strip()
    if not token:
        raise unauthorised('missing bearer token')

    return token


def session(request):
    """
    Read the session cookie off a request, or None if there is no credential.

    The browser's half of the pair. What comes back goes through the same
    `decode` as a bearer token, because it is the same token -- the cookie is
    how a browser carries one, not a second kind of credential.

    Unlike `bearer` there is no malformed case to separate out: no scheme to
    get wrong, and a browser sends back whatever it was given. An empty
    cookie is a caller with no credential rather than one doing it wrong.

    Args:
        request (Request) - Incoming request.
    """
    return request.cookies.get(COOKIE) or None


def mint(subject, name=None, email=None, groups=None, ttl_hours=None):
    """
    Issue a signed token for a caller.

    gate does not pass an identity provider's token through. It reads the
    provider's answer once and issues one of its own, with a deliberately
    small claim set, so that every downstream consumer sees the same shape
    regardless of which provider vouched for the person -- and so that
    swapping providers breaks nothing beyond this service.

    Args:
        subject (str) - Stable identifier for the caller, the `sub` claim.
        name (str) - Display name. Falls back to the subject.
        email (str) - Email address, or None for a non-human caller.
        groups (list) - Group strings the caller belongs to.
        ttl_hours (int) - Lifetime in hours. Defaults to the configured ttl.
    """
    if not subject:
        raise ValueError('a token needs a subject')

    issued = datetime.now(timezone.utc)
    lifetime = config.JWT_TTL_HOURS if ttl_hours is None else ttl_hours

    # pyjwt converts datetimes to numeric dates for the registered claims
    claims = {
        'sub': subject,
        'name': name or subject,
        'email': email,
        'groups': list(groups or []),
        'iat': issued,
        'exp': issued + timedelta(hours=lifetime),
    }

    return jwt.encode(
        claims,
        config.JWT_SECRET.get_secret_value(),
        algorithm=config.JWT_ALGORITHM,
    )


def decode(token):
    """
    Read the claims out of a token, or refuse it.

    An expired token is reported apart from an invalid one. Both are refused
    identically, but the caller's remedy differs: log in again, versus stop
    sending this token at all.

    Every credential that arrives from a caller comes through here, header
    or cookie, api client or browser. The provider's `id_token` is the one
    token in gate read without verifying, because it arrives down a channel
    gate opened and authenticated itself -- that read is spelled out where
    it happens rather than hidden behind a helper, and the reasoning for it
    sits with it.

    Args:
        token (str) - Encoded token.
    """
    try:
        # the algorithm is pinned rather than read from the token's own
        # header. trusting the header is how a token arrives claiming
        # `alg: none` and is accepted without a signature at all.
        return jwt.decode(
            token,
            config.JWT_SECRET.get_secret_value(),
            algorithms=[config.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise unauthorised('token expired')
    except jwt.InvalidTokenError:
        raise unauthorised('invalid token')


# request
# -------
def scheme(request):
    """
    The scheme the caller actually used, not the one that reached us.

    gate runs behind nginx, which terminates tls and forwards over plain
    http -- so `request.url.scheme` says http for a browser that used
    https. Build a redirect_uri from that and the identity provider refuses
    it, because it will not match the callback registered against it.

    Args:
        request (Request) - Incoming request.
    """
    return request.headers.get('x-forwarded-proto', request.url.scheme)


def callback_url(request):
    """
    The address the provider returns the caller to.

    Both legs need this string and it has to be identical in each: login
    sends it as `redirect_uri`, and the exchange sends it again for the
    provider to compare. A provider refuses a mismatch before showing the
    caller anything at all, so the two must not be spelled out separately.

    Reversed from the route rather than assembled from the current path, so
    the answer does not depend on which endpoint is asking -- building it
    from `request.url.path` gives the right string on the login leg and
    `/auth/callback/callback` on the other one.

    Args:
        request (Request) - Incoming request.
    """
    # url_for reports the scheme that reached us, which behind nginx is http
    # even when the browser used https
    url = request.url_for('callback')

    return str(url.replace(scheme=scheme(request)))


def verify_relative_path(rd):
    """
    Validate where a caller asks to be returned after logging in.

    Only relative paths are accepted. This value survives the round trip to
    the provider and is eventually redirected to, so an absolute url here
    makes gate an open redirect -- a link that starts on our host and lands
    on someone else's, which is exactly the shape a phishing link wants.

    Args:
        rd (str) - Requested destination, or None.
    """
    if not rd:
        return None

    # a protocol-relative url (//evil.test) is absolute to a browser while
    # looking relative to a naive check, so both forms are refused
    if not rd.startswith('/') or rd.startswith('//'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='rd must be a relative path',
        )

    return rd


# identity
# --------
def scrub(value):
    """
    Render a claim as a header value.

    Newlines are stripped rather than escaped. `name` and `email` originate
    with the identity provider, and a newline inside a header value is how
    one header becomes two -- in the response every other service is about
    to trust. Cheap to prevent, unpleasant to discover.

    Args:
        value - Claim value, of whatever type the token carried.
    """
    if value is None:
        return ''

    return str(value).replace('\r', '').replace('\n', '').strip()


def identity(user):
    """
    Build the identity headers for a caller.

    Args:
        user (dict) - Claims of the authenticated caller.
    """
    headers = {name: scrub(user.get(claim)) for name, claim in HEADERS.items()}

    # groups travel as one comma-separated value, which is safe only because
    # each one is scrubbed on the way out -- the receiver splits on commas
    # and has no escaping rule to fall back on.
    headers['X-Groups'] = ','.join(scrub(group) for group in user.get('groups') or [])

    return headers


# dependency
# ----------
async def get_current_user(request: Request):
    """
    FastAPI dependency resolving a request to the claims of its caller.

    Two credentials, tried in turn rather than chained. An api client carries
    a bearer token and no cookie, a browser carries a cookie and no
    Authorization header, and requiring both would refuse everybody.

    Bearer wins where both arrive. A browser attaches a cookie on its own
    initiative, while a header is something a caller deliberately put there,
    so it is the better statement of which identity was meant -- and it is
    the path every non-browser caller has.

    Both branches end at the same `decode`, which is what keeps them from
    drifting apart. The cookie carries gate's own token, so there is one
    thing to verify here and, in the next section, one thing to revoke.

    Args:
        request (Request) - Incoming request.
    """
    token = bearer(request)
    if token is not None:
        return decode(token)

    token = session(request)
    if token is not None:
        return decode(token)

    raise unauthorised('not authenticated')
