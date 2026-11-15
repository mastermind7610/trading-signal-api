import hmac
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# The server reads its accepted key(s) from this environment variable. Several
# keys can be given separated by commas, so a key can be rotated by adding the
# new one, switching clients over, then removing the old one.
API_KEY_ENV_VAR = "API_KEY"
API_KEY_HEADER = "X-API-Key"

_api_key_header = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    description="API key issued by the service owner.",
)


def configured_api_keys() -> list[str]:
    """Keys the server currently accepts. Read on every call, never cached,
    so a rotated key takes effect as soon as the environment changes."""
    raw = os.environ.get(API_KEY_ENV_VAR, "")
    return [key.strip() for key in raw.split(",") if key.strip()]


def require_api_key(provided: str | None = Security(_api_key_header)) -> None:
    """Reject the request unless it carries an accepted X-API-Key.

    Fails closed: with no key configured on the server every protected route
    answers 503 instead of running unauthenticated.
    """
    accepted = configured_api_keys()

    if not accepted:
        raise HTTPException(
            status_code=503,
            detail=(
                "API key authentication is not configured: "
                f"set {API_KEY_ENV_VAR} on the server."
            ),
        )

    # Compare against every key, in constant time each, so the response time
    # does not reveal which key matched or how much of one was right.
    candidate = (provided or "").encode()
    matches = [hmac.compare_digest(candidate, key.encode()) for key in accepted]

    if not any(matches):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
