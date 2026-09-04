import unittest

from app.models import Document, Tenant
from app.repositories.document_repository import DocumentRepository
from app.services.tenant_service import TenantService
from tests.helpers import DatabaseTestCase


class TenantServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.owner = self.create_user("owner@example.com")
        self.member = self.create_user("member@example.com")
        self.service = TenantService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_default_and_created_tenants_are_membership_scoped(self) -> None:
        default_membership = self.service.ensure_default_membership(self.owner.id)
        created_membership = self.service.create_tenant(
            creator_user_id=self.owner.id,
            name="Research division",
        )
        self.service.add_member(tenant_id=created_membership.tenant_id, user_id=self.member.id)

        self.assertEqual(default_membership.tenant.slug, "default")
        self.assertEqual(created_membership.tenant.slug, "research-division")
        self.assertEqual(
            [membership.tenant_id for membership in self.service.list_active_memberships(self.member.id)],
            [created_membership.tenant_id],
        )

    def test_document_repository_hides_other_tenant_documents(self) -> None:
        first = Tenant(name="First", slug="first")
        second = Tenant(name="Second", slug="second")
        self.session.add_all([first, second])
        self.session.commit()
        for tenant, name in ((first, "first"), (second, "second")):
            self.session.add(Document(
                tenant_id=tenant.id,
                uploader_user_id=self.owner.id,
                title=name,
                original_filename=f"{name}.txt",
                content_type="text/plain",
                size_bytes=1,
                sha256=name[0] * 64,
                storage_key=f"documents/tenant-{tenant.id}/{name}",
            ))
        self.session.commit()

        documents = DocumentRepository(self.session).list_active(offset=0, limit=25, tenant_id=first.id)
        self.assertEqual([document.title for document in documents], ["first"])
