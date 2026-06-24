from fastapi import Header, HTTPException, Request

from app.auth.jwt import decode_access_token
from app.auth.session import SessionManager


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    session_mgr: SessionManager = request.app.state.session_mgr
    session_id = payload.get("session_id")
    email = payload.get("email")
    if session_id and email:
        active = await session_mgr.is_session_active(session_id, email)
        if not active:
            raise HTTPException(status_code=401, detail="Session revoked or expired.")
    return payload
