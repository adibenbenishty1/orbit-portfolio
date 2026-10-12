# -*- coding: utf-8 -*-
"""

    Authentication API

    The endpoints nginx consults. gate is not in the request path: nginx
    holds each incoming request, asks one of these whether the caller may
    proceed, and forwards the original request itself -- copying the
    identity headers from our answer onto it. Everything here is an answer
    about a request being handled somewhere else.

"""


# imports
# -------
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from gate.config import config
from gate.logging import api as log
from gate.auth.groups import normalise
from gate.auth.utils import (
    COOKIE,
    NO_DESTINATION,
    callback_url,
    get_current_user,
    identity,
    mint,
    scheme,
    verify_relative_path,
)


# router
# ------
router = APIRouter(
    prefix='/auth',
    tags=['auth'],
    responses={401: {'description': 'Not authenticated'}},
)


# endpoints
# ---------
@router.get('/login')
async def login(request: Request, rd: str = None):
    """
    Send a caller to the identity provider to authenticate.

    The first leg of three: out to the provider, the person authenticates
    there, and the provider returns them to our callback with a code to
    exchange. Only this leg exists so far, so the trip currently ends at a
    provider that is still a placeholder.

    `state` carries the destination rather than a random nonce, so that the
    callback knows where to put the caller afterwards. That is a return
    address, not csrf protection -- verifying a nonce means storing one, and
    gate has nowhere to store it yet.

    Args:
        request (Request) - Incoming request.
        rd (str) - Relative path to return to after logging in.
    """
    rd = verify_relative_path(rd)

    params = urlencode(dict(
        client_id=config.AUTH_CLIENT_ID,
        response_type='code',
        scope=config.AUTH_SCOPES,
        redirect_uri=callback_url(request),
        state=rd or NO_DESTINATION,
    ))

    # 302 rather than fastapi's default 307: an authorize redirect is a plain
    # get, and 302 is what every provider's documentation describes
    authorize = str(config.AUTH_PROVIDER_URL).rstrip('/') + config.AUTH_AUTHORIZE_PATH

    return RedirectResponse(
        url=f'{authorize}?{params}',
        status_code=status.HTTP_302_FOUND,
    )


@router.get('/callback')
async def callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    """
    Receive the caller back from the identity provider.

    The third and last leg: the person has authenticated somewhere else and
    the provider has sent them here with the result. The code is traded for
    the provider's `id_token`, read once, and thrown away -- what leaves here
    is a token gate signed itself, carrying four claims and the provider's
    groups rewritten into gate's own vocabulary.

    This is the seam the whole two-token design exists for. Nothing downstream
    ever sees the provider's token, so nothing downstream is shaped by which
    provider vouched for the person; swapping auth0 for something else changes
    this function and nothing beyond it.

    Authentication finishes here and nothing about authorisation begins. The
    groups are not a decision -- they are the facts a decision gets made from
    later, by `/check` on every single request, which is why they have to be
    carried in the credential rather than fetched from the provider each time.

    These four parameters are the provider's whole vocabulary here, and it
    reports failure in the query string rather than as a status code: someone
    who declines consent arrives with `error` set and no `code` at all. Both
    shapes are refused before the exchange is attempted, since there is
    nothing to trade.

    The exchange itself is the one back-channel call in the flow: no browser
    in the middle, gate calling the provider directly and authenticating as
    itself. The code is single use and short lived, so a replayed one arrives
    as a provider error rather than as a second valid token -- which is the
    provider's job to enforce, not ours.

    Credentials travel as HTTP Basic rather than in the form body. Both are
    legal; Basic keeps the secret out of anything that logs request bodies.

    How this ends depends on `state`. A caller who arrived with somewhere to
    be is a browser that was bounced here against its will: it gets the
    credential in a cookie and a redirect to what it originally asked for,
    a cookie being the only credential a browser attaches to a link by
    itself. A caller with no destination came here deliberately to fetch a
    token, and still gets the placeholder json -- the ending that deserves
    waits on the cli `login` that will read it.

    Args:
        request (Request) - Incoming request.
        code (str) - Authorisation code, to exchange for the provider's token.
        state (str) - The value login sent out, echoed back untouched. Carries
            the caller's requested destination.
        error (str) - Provider's error code, when authentication did not happen.
        error_description (str) - Provider's explanation of `error`.
    """

    # the provider's own error text is not echoed back: anyone can request
    # this url with any error on it, and reflecting it makes gate a mouthpiece
    if code is None or error:
        log.info(f'callback refused: error={error!r} description={error_description!r}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='authentication did not complete',
        )

    url = str(config.AUTH_PROVIDER_URL).rstrip('/') + config.AUTH_TOKEN_PATH

    async with httpx.AsyncClient() as http:
        response = await http.post(
            url,
            data=dict(
                grant_type='authorization_code',
                code=code,
                # identical to the one login sent, or the provider refuses it
                redirect_uri=callback_url(request),
            ),
            auth=(config.AUTH_CLIENT_ID, config.AUTH_CLIENT_SECRET.get_secret_value()),
            timeout=10,
        )

    # 400 rather than 502: the likeliest cause by far is a code that was
    # already used or has expired, which is the caller's problem and not the
    # provider's. a misconfigured secret looks the same from here, and the log
    # line is what tells the two apart -- the provider's own explanation
    # describes our configuration, and whoever reached this url is not
    # necessarily someone to describe it to.
    if response.status_code != 200:
        log.error(f'code exchange refused ({response.status_code}): {response.text}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='the identity provider refused the code exchange',
        )

    provider = response.json()

    # a provider that returns no id_token was not asked for one -- the openid
    # scope is missing. reported here rather than as a KeyError two lines on.
    token = provider.get('id_token')
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='the identity provider returned no id_token',
        )

    # read without verifying the signature, deliberately. this token arrived
    # as the body of a tls response to a request gate itself made, to a
    # configured host, authenticated with gate's client secret -- there is no
    # position in that channel for anyone to have substituted it, so a
    # signature would confirm what the channel already established. checking
    # it against the provider's jwks would defend against a compromised
    # provider, which is not the threat here, and needs a key cache gate has
    # nowhere to put. anything arriving from a *caller* goes through decode()
    # instead: the distinction is the channel, not the token's shape.
    claims = jwt.decode(token, options={'verify_signature': False})

    # every provider must send `sub` -- it is the one claim oidc requires, and
    # the only stable handle on a person. refused here rather than reaching
    # mint() as a ValueError and surfacing as a 500.
    subject = claims.get('sub')
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='the identity provider returned no subject',
        )

    # the only place the provider's spelling of a group exists. everything
    # downstream -- this token, the headers, §6's policy -- speaks the
    # `service:role` vocabulary that comes out of here.
    groups = normalise(claims.get(config.GROUPS_CLAIM))

    # the one failure on this path nothing else can see. a tenant that emits
    # no group claim mints a token that looks perfectly healthy and is
    # refused by every policy in the section that reads it, and the suite
    # cannot notice because every test supplies the claim itself. said here
    # against a real login, or nowhere.
    if not groups:
        log.warning(
            f'no groups minted for {subject}: '
            f'claim {config.GROUPS_CLAIM!r} carried '
            f'{claims.get(config.GROUPS_CLAIM)!r}'
        )

    gate_token = mint(
        subject=subject,
        name=claims.get('name'),
        email=claims.get('email'),
        groups=groups,
    )

    # `state` came back through a browser and was not ours in between, so the
    # destination is validated again rather than trusted for having survived
    # the round trip. the sentinel is recognised first: it is not a path, and
    # `verify_relative_path` would refuse it with a 400.
    rd = verify_relative_path(state) if state != NO_DESTINATION else None

    if rd:
        response = RedirectResponse(url=rd, status_code=status.HTTP_302_FOUND)

        # the attributes are where the silent failures live. Secure follows
        # the forwarded scheme because a Secure cookie is discarded without a
        # word over plain http, which is what localhost is; no domain is set
        # because localhost has no parent domain and setting one fails the
        # same silent way. HttpOnly because nothing in a browser needs to
        # read a credential and javascript that can read one turns an xss
        # into a stolen token. Lax rather than Strict because the navigation
        # that matters arrives from the provider's domain, and Strict
        # withholds the cookie on exactly that one. The lifetime matches the
        # token's, so a browser cannot look logged in while 401ing.
        response.set_cookie(
            COOKIE,
            gate_token,
            max_age=config.JWT_TTL_HOURS * 3600,
            path='/',
            httponly=True,
            secure=scheme(request) == 'https',
            samesite='lax',
        )

        return response

    # temporary, and longer-lived than intended: handing the token back as
    # json proves the leg works rather than answering what a caller who came
    # for a credential should get. it is replaced when the cli `login` gives
    # the parked token page a caller.
    return {'token': gate_token}


@router.get('/check', status_code=status.HTTP_200_OK)
async def check(user: dict = Depends(get_current_user)):
    """
    Authorise one request. The endpoint nginx calls on every single request.

    A 200 admits the request and carries the caller's identity; a 401
    refuses it. Route- and method-scoped policy joins this decision in a
    later section, reading the original request's url and method from the
    headers the ingress sets -- the subrequest itself has neither.

    Args:
        user (dict) - Claims of the authenticated caller.
    """
    return Response(
        content='Authenticated',
        status_code=status.HTTP_200_OK,
        media_type='text/plain',
        headers=identity(user),
    )
