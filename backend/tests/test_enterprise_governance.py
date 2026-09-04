import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from app.core.exceptions import ApiKeyAuthenticationError, ApiKeyValidationError, RateLimitExceededError
from app.models import Document, Tenant
from app.security.permissions import PermissionCode
from app.services.api_key_service import ApiKeyService
from app.services.rate_limit_service import RateLimitService
from app.services.retention_service import RetentionService
from tests.helpers import DatabaseTestCase


class ApiKeyServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user("machine-owner@example.com")
        self.tenant = Tenant(name="Example organization", slug="example")
        self.session.add(self.tenant)
        self.session.commit()
        self.service = ApiKeyService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_creates_hashes_authenticates_and_revokes_a_scoped_key(self) -> None:
        with patch.object(self.service.permissions, "user_has_permission", return_value=True):
            created = self.service.create(
                tenant_id=self.tenant.id,
                creator_user_id=self.user.id,
                name="indexing automation",
                scopes=[PermissionCode.DOCUMENTS_READ.value],
            )

        self.assertTrue(created.plaintext.startswith("aegis_"))
        self.assertNotIn(created.plaintext, created.api_key.secret_hash)
        authenticated = self.service.authenticate(created.plaintext)
        self.assertEqual(authenticated.id, created.api_key.id)
        self.assertIsNotNone(authenticated.last_used_at)

        self.service.revoke(
            tenant_id=self.tenant.id,
            api_key_id=created.api_key.id,
            actor_user_id=self.user.id,
        )
        with self.assertRaises(ApiKeyAuthenticationError):
            self.service.authenticate(created.plaintext)

    def test_rejects_unknown_or_escalated_scopes(self) -> None:
        with self.assertRaises(ApiKeyValidationError):
            self.service.create(
                tenant_id=self.tenant.id,
                creator_user_id=self.user.id,
                name="invalid",
                scopes=["system:root"],
            )
        with patch.object(self.service.permissions, "user_has_permission", return_value=False):
            with self.assertRaises(ApiKeyValidationError):
                self.service.create(
                    tenant_id=self.tenant.id,
                    creator_user_id=self.user.id,
                    name="escalated",
                    scopes=[PermissionCode.DOCUMENTS_READ.value],
                )


class RateLimitServiceTests(unittest.TestCase):
    def test_enforces_a_bounded_tenant_principal_bucket(self) -> None:
        redis = Mock()
        redis.incr.side_effect = [1, 2, 3]
        redis.ttl.return_value = 42
        service = RateLimitService(redis_factory=lambda: redis, limit=2)

        decision = service.enforce(tenant_id=7, principal="user-3")
        self.assertEqual((decision.limit, decision.used, decision.retry_after_seconds), (2, 1, 42))
        service.enforce(tenant_id=7, principal="user-3")
        with self.assertRaises(RateLimitExceededError):
            service.enforce(tenant_id=7, principal="user-3")
        redis.expire.assert_called_once_with("aegis:rate-limit:v1:7:user-3", 60)


class RetentionServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.user = self.create_user("retention-owner@example.com")
        self.tenant = Tenant(name="Retention organization", slug="retention")
        self.session.add(self.tenant)
        self.session.commit()
        self.service = RetentionService(self.session, Mock())

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_purge_delegates_expired_tenant_documents_to_the_existing_lifecycle(self) -> None:
        self.service.update_policy(
            tenant_id=self.tenant.id,
            actor_user_id=self.user.id,
            document_retention_days=30,
        )
        document = Document(
            tenant_id=self.tenant.id,
            uploader_user_id=self.user.id,
            title="Old policy",
            original_filename="old-policy.txt",
            content_type="text/plain",
            size_bytes=3,
            sha256="a" * 64,
            storage_key="documents/tenant-1/old",
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
            updated_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        self.session.add(document)
        self.session.commit()
        self.service.documents = Mock()

        self.assertEqual(self.service.purge_expired_documents(tenant_id=self.tenant.id), 1)
        self.service.documents.delete_document.assert_called_once_with(
            document.id,
            actor_user_id=None,
            tenant_id=self.tenant.id,
        )
