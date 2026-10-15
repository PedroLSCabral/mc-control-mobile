"""Bearer token check."""

import secrets

from fastapi import Header, HTTPException, Request, status


def require_token(request: Request, authorization: str = Header(default="")) -> None:
    """FastAPI dependency: rejects the request unless it carries the right token."""
    expected = request.app.state.token
    scheme, _, token = authorization.partition(" ")
    # compare_digest takes the same time whether the token is right or wrong,
    # so an attacker cannot guess it character by character by measuring latency.
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
