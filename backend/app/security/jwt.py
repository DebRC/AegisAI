from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import uuid4

from jose import JWTError
from jose import jwt
from jose import ExpiredSignatureError

from app.core.config import settings
from app.schemas.token import TokenPayload
from app.security.constants import TokenType
from app.core.exceptions import AuthenticationError

def create_token(
    user_id: int,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    """Generate a signed token with the requested lifetime and type."""

    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "exp": expire,
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(user_id: int) -> str:
    return create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    user_id: int,
) -> str:
    return create_token(
        user_id,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(
    token: str,
) -> TokenPayload:

    try:

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[
                settings.JWT_ALGORITHM
            ],
        )
        
        return TokenPayload(**payload)

    except ExpiredSignatureError:

        raise AuthenticationError(
            "Refresh token expired"
        )

    except JWTError:

        raise AuthenticationError(
            "Invalid token"
        )

    

def refresh_token_expiry():

    return (
        datetime.now(timezone.utc)
        + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    )
