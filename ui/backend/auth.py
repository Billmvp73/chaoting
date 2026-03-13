"""HTTP Basic Auth dependency for chaoting Web UI."""

from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def require_auth(
    credentials: HTTPBasicCredentials = Depends(security),
) -> HTTPBasicCredentials:
    correct_user = os.environ.get("CHAOTING_UI_USER", "")
    correct_pass = os.environ.get("CHAOTING_UI_PASS", "")
    user_ok = secrets.compare_digest(
        credentials.username.encode(), correct_user.encode()
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode(), correct_pass.encode()
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials
