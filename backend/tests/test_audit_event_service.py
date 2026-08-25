import unittest

from app.core.exceptions import AuditEventValidationError
from app.models import AuditEventOutcome
from app.models import AuditEventType
from app.services.audit_event_service import AuditEventService
from tests.helpers import DatabaseTestCase


class AuditEventServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.actor = self.create_user("actor@example.com")
        self.service = AuditEventService(self.session)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_records_validated_event_without_committing_the_caller_transaction(self) -> None:
        event = self.service.record(
            event_type=AuditEventType.DOCUMENT_ACCESS_GRANT_UPDATED,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=self.actor.id,
            target_type="document",
            target_id=12,
            metadata={
                "previous_access_level": "read",
                "access_level": "write",
            },
        )

        self.assertEqual(event.id, 1)
        self.assertEqual(event.metadata_, {
            "previous_access_level": "read",
            "access_level": "write",
        })
        self.assertTrue(self.session.in_transaction())
        self.session.commit()
        self.assertEqual(self.session.query(type(event)).count(), 1)

    def test_rejects_untrusted_identifiers_and_metadata(self) -> None:
        invalid_events = (
            {"event_type": "document.read"},
            {"outcome": "succeeded"},
            {"actor_user_id": 0},
            {"target_type": "email", "target_id": 1},
            {"target_type": "document", "target_id": None},
            {"metadata": {"query": "do not persist user text"}},
            {"metadata": {"provider": ["nested data is not allowed"]}},
            {"metadata": {"provider": "x" * 129}},
        )
        base = {
            "event_type": AuditEventType.DOCUMENT_READ,
            "outcome": AuditEventOutcome.SUCCEEDED,
        }
        for invalid in invalid_events:
            with self.subTest(invalid=invalid):
                with self.assertRaises(AuditEventValidationError):
                    self.service.record(**(base | invalid))
