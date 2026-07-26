from datetime import datetime
from datetime import timedelta
from datetime import timezone

from jose import JWTError
from jose import jwt

from app.core.config import settings


def create_access_token(
    user_id: int,
) -> str:
    """
    Generate a short-lived access token.
    """

    expire = datetime.now(
        timezone.utc
    ) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    user_id: int,
) -> str:
    """
    Generate a long-lived refresh token.
    """

    expire = datetime.now(
        timezone.utc
    ) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(
    token: str,
) -> dict:
    """
    Decode and validate a JWT.
    """

    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[
            settings.JWT_ALGORITHM
        ],
    )