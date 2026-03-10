"""
API key authentication dependency.
"""

import os
from typing import Optional
from fastapi import Header, HTTPException


API_KEY = os.getenv("API_KEY")


async def verify_api_key(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> None:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")

    # Accept X-Api-Key header or Authorization: Bearer <token>
    token = x_api_key
    if token is None and authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")

    if token != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
