"""POST /analysis/users: minimal user creation so the existing analysis API is usable.

Mounted under /analysis so LocalDevelopmentBoundaryMiddleware (no-auth acknowledgement +
loopback-only) applies unchanged. Returns only user_id: no email or name is echoed back."""
import logging
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, StringConstraints
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError
from app.api.routes.analysis import _internal_error
from app.services import user_service as us

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis/users", tags=["users"])

Email = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254,
                                         pattern=r"^[^@\s]+@[^@\s]+$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class UserCreateRequest(BaseModel):
    email: Email
    full_name: Name


class UserCreateResponse(BaseModel):
    user_id: int


@router.post("", response_model=UserCreateResponse, status_code=201)
def create_user(body: UserCreateRequest) -> UserCreateResponse:
    try:
        user = us.create_user(body.email, body.full_name)
    except IntegrityError:
        # Assumes users.email is UNIQUE; verify against the schema before relying on this.
        raise ApiError(409, "user_exists", "A user with this email already exists.") from None
    except Exception as exc:
        raise _internal_error(exc) from None
    return UserCreateResponse(user_id=user.user_id)
