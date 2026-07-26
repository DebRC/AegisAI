from fastapi import APIRouter
from fastapi import Depends

from app.security.dependencies import (
    get_current_user,
)

router = APIRouter(
    prefix="/protected",
    tags=["Protected"],
)


@router.get("")
def protected(
    user=Depends(
        get_current_user
    ),
):

    return {
        "message": "Access granted",
        "user": user,
    }