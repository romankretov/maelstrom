"""TOTP enrollment + verification.

Flow:
  1. User calls POST /auth/totp/enroll -> server generates secret, returns provisioning URI
  2. User scans QR in authenticator app, then calls POST /auth/totp/confirm with a code
  3. Subsequent sensitive operations require POST /auth/totp/verify with current code
"""
import base64
import io
import secrets
from datetime import UTC, datetime

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .auth import current_active_user
from .db import get_session
from .models import User

router = APIRouter(prefix="/auth/totp", tags=["auth"])


class EnrollResponse(BaseModel):
    provisioning_uri: str
    qr_code_data_url: str


class CodeIn(BaseModel):
    code: str


def _generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _qr_data_url(uri: str) -> str:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@router.post("/enroll", response_model=EnrollResponse)
async def enroll(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> EnrollResponse:
    if user.totp_confirmed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "TOTP already confirmed")
    user.totp_secret = _generate_secret()
    uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(
        name=user.email,
        issuer_name="Maelstrom",
    )
    session.add(user)
    await audit.record(session, action="totp.enroll", actor_id=user.id)
    await session.commit()
    return EnrollResponse(provisioning_uri=uri, qr_code_data_url=_qr_data_url(uri))


@router.post("/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm(
    body: CodeIn,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if user.totp_secret is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOTP not enrolled")
    if not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    user.totp_confirmed_at = datetime.now(UTC)
    session.add(user)
    await audit.record(session, action="totp.confirm", actor_id=user.id)
    await session.commit()


@router.post("/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify(
    body: CodeIn,
    user: User = Depends(current_active_user),
) -> None:
    if user.totp_secret is None or user.totp_confirmed_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "TOTP not configured")
    if not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
