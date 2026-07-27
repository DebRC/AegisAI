from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import get_auth_service

from app.schemas.auth import (
    RegisterRequest,
)

from app.schemas.token import (
    TokenResponse,
)

from app.schemas.user import (
    UserResponse,
)

from app.schemas.refresh import (
    RefreshRequest,
)

from app.services.auth_service import AuthService

from app.core.exceptions import (
    AuthenticationError,
    UserAlreadyExistsError,
)
from app.models.user import User

from app.security.dependencies import (
    get_current_user,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
):
    try:

        return service.register(request)

    except UserAlreadyExistsError:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    try:

        return service.login(
            email=form_data.username,
            password=form_data.password,
        )

    except AuthenticationError:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

@router.get(
    "/me",
    response_model=UserResponse,
)
def me(
    current_user: User = Depends(
        get_current_user
    ),
):

    return current_user

@router.post("/logout")
def logout(
    request: RefreshRequest,
    service: AuthService = Depends(
        get_auth_service
    ),
):

    service.logout(
        request.refresh_token
    )

    return {
        "message":"Logged out"
    }

@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh(
    request: RefreshRequest,
    service: AuthService = Depends(
        get_auth_service
    ),
):

    try:

        return service.refresh(
            request.refresh_token
        )

    except AuthenticationError:

        raise HTTPException(

            status_code=401,

            detail="Invalid refresh token",

        )