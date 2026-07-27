from datetime import datetime
from datetime import timedelta
from datetime import timezone

from jose import JWTError
from jose import jwt
from jose import ExpiredSignatureError

from app.core.config import settings
from app.schemas.token import TokenPayload
from app.security.constants import ACCESS_TOKEN
from app.security.constants import REFRESH_TOKEN
from app.core.exceptions import AuthenticationError

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
        "type": ACCESS_TOKEN,
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
        "type": REFRESH_TOKEN,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
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
