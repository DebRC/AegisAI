import unittest
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.exc import IntegrityError

from app.models import ExternalIdentity
from app.models import RefreshToken
from app.models import Role
from app.models import RolePermission
from app.models import UserRole
from app.repositories.permission_repository import PermissionRepository
from app.repositories.external_identity_repository import ExternalIdentityRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.role_permission_repository import RolePermissionRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_role_repository import UserRoleRepository
from app.security.permissions import PermissionCode
from tests.helpers import DatabaseTestCase


class RepositoryTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user()
        self.seed_permissions()

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_user_repository_create_get_and_update(self) -> None:
        repository = UserRepository(self.session)
        created = self.create_user("other@example.com")

        self.assertEqual(repository.get_by_email(created.email).id, created.id)
        self.assertEqual(repository.get_by_id(created.id).email, created.email)

        created.full_name = "Updated User"
        repository.update()
        self.session.commit()
        self.assertEqual(repository.get_by_id(created.id).full_name, "Updated User")

    def test_refresh_token_repository_lifecycle(self) -> None:
        repository = RefreshTokenRepository(self.session)
        valid = repository.create(
            RefreshToken(
                token="valid-token",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                user_id=self.user.id,
            )
        )
        expired = repository.create(
            RefreshToken(
                token="expired-token",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                user_id=self.user.id,
            )
        )
        self.session.commit()

        self.assertEqual(repository.get_valid_token(valid.token).id, valid.id)
        self.assertEqual(repository.get_by_token(valid.token).id, valid.id)
        self.assertIsNone(repository.get_valid_token(expired.token))

        repository.revoke_by_token(valid.token)
        self.session.commit()
        self.assertIsNone(repository.get_valid_token(valid.token))

        self.assertEqual(repository.delete_expired(datetime.now(timezone.utc)), 1)
        self.session.commit()
        self.assertIsNone(repository.get_by_token(expired.token))

        repository.delete(valid)
        self.session.commit()
        self.assertIsNone(repository.get_by_token(valid.token))

    def test_external_identity_repository_enforces_provider_subject_uniqueness(
        self,
    ) -> None:
        repository = ExternalIdentityRepository(self.session)
        identity = repository.create(
            ExternalIdentity(
                provider="google",
                provider_subject="google-subject-123",
                provider_email="user@example.com",
                email_verified=True,
                user_id=self.user.id,
            )
        )
        self.session.commit()

        self.assertEqual(
            repository.get_by_provider_and_subject("google", "google-subject-123").id,
            identity.id,
        )
        self.assertEqual(repository.list_by_user_id(self.user.id), [identity])
        self.assertIsNone(
            repository.get_by_provider_and_subject("github", "google-subject-123")
        )

        identity.provider_email = "updated@example.com"
        repository.update()
        self.session.commit()
        self.assertEqual(
            repository.get_by_provider_and_subject(
                "google",
                "google-subject-123",
            ).provider_email,
            "updated@example.com",
        )

        self.session.add(
            ExternalIdentity(
                provider="google",
                provider_subject="google-subject-123",
                user_id=self.user.id,
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.flush()
        self.session.rollback()

    def test_role_repository_create_get_list_and_delete(self) -> None:
        repository = RoleRepository(self.session)
        zulu = repository.create(Role(name="zulu", description=None))
        alpha = repository.create(Role(name="alpha", description="First"))
        self.session.commit()

        self.assertEqual(repository.get_by_id(alpha.id).name, "alpha")
        self.assertEqual(repository.get_by_name(zulu.name).id, zulu.id)
        self.assertEqual([role.name for role in repository.list()], ["alpha", "zulu"])

        repository.delete(zulu)
        self.session.commit()
        self.assertIsNone(repository.get_by_id(zulu.id))

    def test_permission_repository_get_list_and_effective_permission(self) -> None:
        repository = PermissionRepository(self.session)
        permission_id = self.permission_id(PermissionCode.ROLES_READ)
        role = Role(name="reader", description=None)
        self.session.add(role)
        self.session.flush()
        self.session.add(UserRole(user_id=self.user.id, role_id=role.id))
        self.session.add(RolePermission(role_id=role.id, permission_id=permission_id))
        self.session.commit()

        self.assertEqual(repository.get_by_id(permission_id).code, "roles:read")
        self.assertEqual(repository.get_by_code("roles:read").id, permission_id)
        self.assertEqual(repository.list()[0].code, "documents:read")
        self.assertTrue(repository.user_has_permission(self.user.id, "roles:read"))
        self.assertFalse(repository.user_has_permission(self.user.id, "roles:manage"))

    def test_assignment_repositories_create_get_list_and_delete(self) -> None:
        roles = RoleRepository(self.session)
        role = roles.create(Role(name="reader", description=None))
        permission_id = self.permission_id(PermissionCode.ROLES_READ)
        user_roles = UserRoleRepository(self.session)
        role_permissions = RolePermissionRepository(self.session)

        user_assignment = user_roles.create(
            UserRole(user_id=self.user.id, role_id=role.id)
        )
        permission_assignment = role_permissions.create(
            RolePermission(role_id=role.id, permission_id=permission_id)
        )
        self.session.commit()

        self.assertEqual(
            user_roles.get_by_user_and_role(self.user.id, role.id).id,
            user_assignment.id,
        )
        self.assertEqual(user_roles.list_by_user_id(self.user.id), [user_assignment])
        self.assertEqual(
            role_permissions.get_by_role_and_permission(role.id, permission_id).id,
            permission_assignment.id,
        )
        self.assertEqual(
            role_permissions.list_by_role_id(role.id),
            [permission_assignment],
        )

        user_roles.delete(user_assignment)
        role_permissions.delete(permission_assignment)
        self.session.commit()
        self.assertIsNone(user_roles.get_by_user_and_role(self.user.id, role.id))
        self.assertIsNone(
            role_permissions.get_by_role_and_permission(role.id, permission_id)
        )
