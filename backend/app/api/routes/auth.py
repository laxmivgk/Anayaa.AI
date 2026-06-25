from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import require_auth
from app.auth.identity import verify_identity
from app.auth.jwt import create_access_token
from app.auth.session import SessionManager
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str


@router.post("/login")
async def login(body: LoginBody, request: Request):
    ok, err = verify_identity(str(body.email))
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    settings = get_settings()
    token, session_id, expires = create_access_token(str(body.email))
    session_mgr: SessionManager = request.app.state.session_mgr
    await session_mgr.register_session(session_id, str(body.email), settings.jwt_exp_minutes * 60)

    return {
        "success": True,
        "token": token,
        "expiresInMinutes": expires,
        "email": str(body.email),
    }


@router.post("/refresh")
async def refresh(request: Request, user=Depends(require_auth)):
    email = user.get("email") or user.get("sub")
    session_id = user.get("session_id")
    if not email or not session_id:
        raise HTTPException(status_code=401, detail="Invalid session.")

    settings = get_settings()
    session_mgr: SessionManager = request.app.state.session_mgr
    if not await session_mgr.check_rate_limit(
        session_id,
        settings.session_refresh_rate_limit_per_minute,
        scope="refresh",
    ):
        raise HTTPException(status_code=429, detail="Too many session refresh attempts.")

    refreshed = await session_mgr.refresh_session(session_id, email, settings.jwt_exp_minutes * 60)
    if not refreshed:
        raise HTTPException(status_code=401, detail="Session revoked or expired.")

    token, _, expires = create_access_token(email, session_id)
    return {
        "success": True,
        "token": token,
        "expiresInMinutes": expires,
        "email": email,
    }
