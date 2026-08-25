from sqlalchemy.orm import Session

from app.core.exceptions import PermissionNotFoundError
from app.core.exceptions import RoleAlreadyExistsError
from app.core.exceptions import RoleAssignmentAlreadyExistsError
from app.core.exceptions import RoleAssignmentNotFoundError
from app.core.exceptions import RoleNotFoundError
from app.core.exceptions import RolePermissionAlreadyExistsError
from app.core.exceptions import RolePermissionNotFoundError
from app.core.exceptions import SystemRoleModificationError
from app.core.exceptions import UserNotFoundError
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_role import UserRole
from app.models.audit_event import AuditEventOutcome
from app.models.audit_event import AuditEventType
from app.repositories.permission_repository import PermissionRepository
from app.repositories.role_permission_repository import RolePermissionRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.services.audit_event_service import AuditEventService


class RbacService:
    def __init__(self, db: Session):
        self.db = db
        self.permissions = PermissionRepository(db)
        self.roles = RoleRepository(db)
        self.role_permissions = RolePermissionRepository(db)
        self.user_roles = UserRoleRepository(db)
        self.users = UserRepository(db)
        self.audit_events = AuditEventService(db)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def create_role(self, name: str, description: str | None, *, actor_user_id: int | None = None) -> Role:
        if self.roles.get_by_name(name) is not None:
            raise RoleAlreadyExistsError()

        role = self.roles.create(
            Role(name=name, description=description)
        )
        self._record(actor_user_id, AuditEventType.RBAC_ROLE_CREATED, "role", role.id)
        self._commit()

        return role

    def list_roles(self) -> list[Role]:
        return self.roles.list()

    def get_role(self, role_id: int) -> Role:
        role = self.roles.get_by_id(role_id)

        if role is None:
            raise RoleNotFoundError()

        return role

    def delete_role(self, role_id: int, *, actor_user_id: int | None = None) -> None:
        role = self.get_role(role_id)

        if role.is_system:
            raise SystemRoleModificationError()

        self.roles.delete(role)
        self._record(actor_user_id, AuditEventType.RBAC_ROLE_DELETED, "role", role.id)
        self._commit()

    def list_permissions(self) -> list[Permission]:
        return self.permissions.list()

    def list_role_permissions(self, role_id: int) -> list[RolePermission]:
        self.get_role(role_id)

        return self.role_permissions.list_by_role_id(role_id)

    def grant_permission(
        self,
        role_id: int,
        permission_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> RolePermission:
        self.get_role(role_id)

        if self.permissions.get_by_id(permission_id) is None:
            raise PermissionNotFoundError()

        if (
            self.role_permissions.get_by_role_and_permission(
                role_id,
                permission_id,
            )
            is not None
        ):
            raise RolePermissionAlreadyExistsError()

        assignment = self.role_permissions.create(
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
            )
        )
        self._record(
            actor_user_id,
            AuditEventType.RBAC_ROLE_PERMISSION_GRANTED,
            "role",
            role_id,
            {"permission_id": permission_id},
        )
        self._commit()

        return assignment

    def revoke_permission(self, role_id: int, permission_id: int, *, actor_user_id: int | None = None) -> None:
        self.get_role(role_id)

        assignment = self.role_permissions.get_by_role_and_permission(
            role_id,
            permission_id,
        )

        if assignment is None:
            raise RolePermissionNotFoundError()

        self.role_permissions.delete(assignment)
        self._record(
            actor_user_id,
            AuditEventType.RBAC_ROLE_PERMISSION_REVOKED,
            "role",
            role_id,
            {"permission_id": permission_id},
        )
        self._commit()

    def list_user_roles(self, user_id: int) -> list[UserRole]:
        self._get_user(user_id)

        return self.user_roles.list_by_user_id(user_id)

    def assign_role(self, user_id: int, role_id: int, *, actor_user_id: int | None = None) -> UserRole:
        self._get_user(user_id)
        self.get_role(role_id)

        if self.user_roles.get_by_user_and_role(user_id, role_id) is not None:
            raise RoleAssignmentAlreadyExistsError()

        assignment = self.user_roles.create(
            UserRole(user_id=user_id, role_id=role_id)
        )
        self._record(
            actor_user_id,
            AuditEventType.RBAC_USER_ROLE_ASSIGNED,
            "user",
            user_id,
            {"role_id": role_id},
        )
        self._commit()

        return assignment

    def remove_role(self, user_id: int, role_id: int, *, actor_user_id: int | None = None) -> None:
        self._get_user(user_id)
        self.get_role(role_id)

        assignment = self.user_roles.get_by_user_and_role(user_id, role_id)

        if assignment is None:
            raise RoleAssignmentNotFoundError()

        self.user_roles.delete(assignment)
        self._record(
            actor_user_id,
            AuditEventType.RBAC_USER_ROLE_REMOVED,
            "user",
            user_id,
            {"role_id": role_id},
        )
        self._commit()

    def _get_user(self, user_id: int) -> User:
        user = self.users.get_by_id(user_id)

        if user is None:
            raise UserNotFoundError()

        return user

    def _record(
        self,
        actor_user_id: int | None,
        event_type: AuditEventType,
        target_type: str,
        target_id: int,
        metadata: dict[str, int] | None = None,
    ) -> None:
        self.audit_events.record(
            event_type=event_type,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata,
        )
