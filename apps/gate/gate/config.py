# -*- coding: utf-8 -*-
"""

    Application configuration

"""


# imports
# -------
from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# config
# ------
class Config(BaseSettings):
    """
    Settings for the gate service.

    Fields are flat and uppercase so that each one maps directly onto an
    environment variable, and from there onto a single key in a helm values
    file. Every field has a working default, so a fresh clone runs with no
    setup. Unknown keys are ignored, which lets one .env file serve several
    services.

    Signing, session and auth-provider fields arrive with the code that reads
    them, in the same way catalog grew its server fields.
    """
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # basic
    ENV: str = 'local'
    PROJECT: str = 'gate'

    # build
    VERSION: str = 'unknown'
    COMMIT: str = 'unknown'

    # server
    # GATE_HOST is where to reach the service from elsewhere -- used by the
    # cli, not as a bind address. The server always binds every interface.
    # The port differs from catalog's so that both run at once locally.
    GATE_HOST: str = 'localhost'
    GATE_PORT: int = 5001

    # signing
    # the default key exists so a fresh clone runs with no setup, and is
    # deliberately obvious. anything other than a local environment must
    # override it -- the key is the whole of gate's authority. it is padded
    # past 32 bytes because an HMAC key shorter than the hash it feeds is
    # weaker than the algorithm it is used with.
    #
    # the algorithm is configured here and pinned at every decode, rather
    # than read from a token's own header: trusting the header is how a
    # token arrives claiming `alg: none` and is accepted unsigned.
    JWT_SECRET: SecretStr = SecretStr('dev-signing-key-do-not-deploy-anywhere')
    JWT_ALGORITHM: str = 'HS256'
    JWT_TTL_HOURS: int = 24

    # provider
    # the identity provider gate sends people to. both legs of the flow are
    # built from these six values, so pointing gate at a real provider is
    # configuration rather than code.
    #
    # the base is a url type so a malformed provider fails at startup with a
    # clear message, rather than at first redirect with an obscure one. the
    # two paths are separate fields because every provider spells them
    # differently: okta serves /oauth2/v1/authorize and /oauth2/v1/token,
    # auth0 /authorize and /oauth/token.
    #
    # the secret defaults to empty so that a fresh clone still starts. it is
    # the one value here that cannot have a working default -- an empty one
    # reaches the provider and comes back as invalid_client, which is the
    # correct outcome for a secret nobody has set.
    AUTH_PROVIDER_URL: HttpUrl = HttpUrl('https://provider.invalid')
    AUTH_AUTHORIZE_PATH: str = '/oauth2/v1/authorize'
    AUTH_TOKEN_PATH: str = '/oauth2/v1/token'
    AUTH_CLIENT_ID: str = 'orbit-dev-client'
    AUTH_CLIENT_SECRET: SecretStr = SecretStr('')
    AUTH_SCOPES: str = 'openid email profile groups'

    # groups
    # the prefix marking a directory group as ours. groups without it are
    # dropped rather than carried, so unrelated memberships cannot leak into
    # the authorisation vocabulary. empty means no prefix is required.
    GROUP_PREFIX: str = 'orbit-'

    # which claim of the provider's id_token carries the group list. plain
    # `groups` is the obvious spelling and the one auth0 cannot give us: it
    # sits on auth0's restricted-claim list, so an action setting it is
    # refused however the tenant is configured. namespacing is optional for
    # custom claims in general since 2022 and mandatory for this one in
    # particular, which makes the real value something like
    # https://orbit.test/groups. configurable rather than hardcoded because it
    # is a contract with the provider's dashboard, not a fact about gate.
    GROUPS_CLAIM: str = 'groups'

    # logging
    LOG_LEVEL: str = 'INFO'

    # monitor
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_NAMESPACE: str = 'orbit'
    PROMETHEUS_SUBSYSTEM: str = 'gate'


# instance
# --------
config = Config()
