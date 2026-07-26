from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from sqlalchemy.orm import Session

from app.db.database import get_db

from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
)

from app.schemas.token import (
    TokenResponse,
)

from app.schemas.user import (
    UserResponse,
)

from app.services.auth_service import AuthService

from app.core.exceptions import (
    AuthenticationError,
    UserAlreadyExistsError,
)

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
    db: Session = Depends(get_db),
):

    service = AuthService(db)

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
    request: LoginRequest,
    db: Session = Depends(get_db),
):

    service = AuthService(db)

    try:

        return service.login(request)

    except AuthenticationError:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

@router.get("/me")
def me(
    current_user=Depends(get_current_user),
):

    return current_user

@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh():

    raise HTTPException(
        status_code=501,
        detail="Not implemented yet",
    )

@router.post("/logout")
def logout():

    raise HTTPException(
        status_code=501,
        detail="Not implemented yet",
    )