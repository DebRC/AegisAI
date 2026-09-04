"""Safe administrator operations for local user accounts."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import AdministratorSelfDeactivationError
from app.core.exceptions import UserNotFoundError
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.audit_event_service import AuditEventService
from app.repositories.tenant_repository import TenantRepository


@dataclass(frozen=True)
class AdminUserPage:
    items: list[User]
    offset: int
    limit: int
    total: int


class AdminUserService:
    """List, inspect, and safely change local account active state."""

    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.audit_events = AuditEventService(db)
        self.tenants = TenantRepository(db)

    def list_users(
        self,
        *,
        offset: int,
        limit: int,
        email_query: str | None = None,
        is_active: bool | None = None,
        tenant_id: int | None = None,
    ) -> AdminUserPage:
        normalized_query = self._validate_filters(
            offset=offset,
            limit=limit,
            email_query=email_query,
            is_active=is_active,
        )
        return AdminUserPage(
            items=self.users.list_for_administration(
                email_query=normalized_query,
                is_active=is_active,
                offset=offset,
                limit=limit,
                tenant_id=tenant_id,
            ),
            offset=offset,
            limit=limit,
            total=self.users.count_for_administration(
                email_query=normalized_query,
                is_active=is_active,
                tenant_id=tenant_id,
            ),
        )

    def get_user(self, user_id: int, *, tenant_id: int | None = None) -> User:
        user = self.users.get_for_administration(user_id, tenant_id=tenant_id)
        if user is None:
            raise UserNotFoundError()
        return user

    def set_active(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        is_active: bool,
        tenant_id: int | None = None,
    ) -> User:
        if not isinstance(is_active, bool):
            raise ValueError("User active state must be boolean")
        if actor_user_id == user_id and not is_active:
            raise AdministratorSelfDeactivationError()
        user = self.get_user(user_id, tenant_id=tenant_id)
        if tenant_id is not None:
            membership = self.tenants.get_membership(tenant_id=tenant_id, user_id=user.id)
            if membership is None:
                raise UserNotFoundError()
            if membership.is_active == is_active:
                return user
            try:
                membership.is_active = is_active
                self.audit_events.record(
                    event_type=(
                        AuditEventType.ADMIN_USER_ACTIVATED
                        if is_active
                        else AuditEventType.ADMIN_USER_DEACTIVATED
                    ),
                    outcome=AuditEventOutcome.SUCCEEDED,
                    actor_user_id=actor_user_id,
                    tenant_id=tenant_id,
                    target_type="user",
                    target_id=user.id,
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return user
        if user.is_active == is_active:
            return user

        try:
            user.is_active = is_active
            if not is_active:
                self.db.execute(
                    update(RefreshToken)
                    .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                    .values(revoked_at=datetime.now(timezone.utc))
                )
            self.users.update()
            self.audit_events.record(
                event_type=(
                    AuditEventType.ADMIN_USER_ACTIVATED
                    if is_active
                    else AuditEventType.ADMIN_USER_DEACTIVATED
                ),
                outcome=AuditEventOutcome.SUCCEEDED,
                actor_user_id=actor_user_id,
                target_type="user",
                target_id=user.id,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return user

    def membership_is_active(self, *, tenant_id: int, user_id: int) -> bool:
        membership = self.tenants.get_membership(tenant_id=tenant_id, user_id=user_id)
        return bool(membership and membership.is_active)

    @staticmethod
    def _validate_filters(
        *,
        offset: int,
        limit: int,
        email_query: str | None,
        is_active: bool | None,
    ) -> str | None:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid offset")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Invalid limit")
        if email_query is not None:
            if not isinstance(email_query, str):
                raise ValueError("Invalid email filter")
            email_query = email_query.strip()
            if not 1 <= len(email_query) <= 255:
                raise ValueError("Invalid email filter")
        if is_active is not None and not isinstance(is_active, bool):
            raise ValueError("Invalid active filter")
        return email_query
