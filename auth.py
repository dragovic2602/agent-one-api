"""
API key authentication dependency.
"""

import os
from fastapi import Header, HTTPException


API_KEY = os.getenv("API_KEY")


async def verify_api_key(x_api_key: str = Header(...)) -> None:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
