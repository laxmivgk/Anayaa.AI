from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
