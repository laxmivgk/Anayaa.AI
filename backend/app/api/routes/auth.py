from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import require_auth
from app.auth.identity import verify_identity
from app.auth.jwt import create_access_token
from app.auth.session import SessionManager
from app.auth.users import (
    create_password_reset_code,
    normalize_email,
    register_user_if_missing,
    reset_user_password,
    verify_user_credentials,
)
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


class PasswordResetRequestBody(BaseModel):
    email: str


class PasswordResetConfirmBody(BaseModel):
    email: str
    resetCode: str
    newPassword: str


@router.post("/login")
async def login(body: LoginBody, request: Request):
    email = normalize_email(body.email)
    ok, err = verify_identity(email)
<<<<<<< HEAD
    email = normalize_email(body.email)
    ok, err = verify_identity(email)
=======
>>>>>>> main
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    settings = get_settings()
    pg = request.app.state.pg
    authenticated_email = await verify_user_credentials(pg, email, body.password)
    if authenticated_email is None:
        try:
            authenticated_email = await register_user_if_missing(pg, email, body.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if authenticated_email is None:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

    token, session_id, expires = create_access_token(authenticated_email)
    session_mgr: SessionManager = request.app.state.session_mgr
    await session_mgr.register_session(session_id, authenticated_email, settings.jwt_exp_minutes * 60)

    return {
        "success": True,
        "token": token,
        "expiresInMinutes": expires,
        "email": authenticated_email,
    }


@router.post("/password-reset/request")
async def request_password_reset(body: PasswordResetRequestBody, request: Request):
    email = normalize_email(body.email)
    ok, err = verify_identity(email)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    pg = request.app.state.pg
    reset_code = await create_password_reset_code(pg, email)
    if reset_code:
        print(f"[anayaa-auth] Password reset code for {email}: {reset_code}", flush=True)
    return {
        "success": True,
        "message": "If this email exists, a reset code was printed in the backend terminal.",
    }


@router.post("/password-reset/confirm")
async def confirm_password_reset(body: PasswordResetConfirmBody, request: Request):
    email = normalize_email(body.email)
    ok, err = verify_identity(email)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    pg = request.app.state.pg
    try:
        updated_email = await reset_user_password(pg, email, body.resetCode, body.newPassword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated_email is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
    return {"success": True, "email": updated_email}


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
