import unittest

from sqlalchemy.exc import IntegrityError

from app.models import AuditEvent
from app.models import AuditEventOutcome
from app.models import AuditEventType
from tests.helpers import DatabaseTestCase


class AuditEventModelTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.actor = self.create_user("actor@example.com")

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_persists_a_safe_event_with_actor_target_and_independent_metadata(self) -> None:
        first = AuditEvent(
            actor_user_id=self.actor.id,
            event_type=AuditEventType.DOCUMENT_ACCESS_GRANT_CREATED,
            outcome=AuditEventOutcome.SUCCEEDED,
            target_type="document",
            target_id=12,
            metadata_={"access_level": "read"},
        )
        second = AuditEvent(
            event_type=AuditEventType.AUTH_LOGIN_FAILED,
            outcome=AuditEventOutcome.DENIED,
        )
        self.session.add_all([first, second])
        self.session.commit()

        self.assertEqual(first.actor, self.actor)
        self.assertEqual(first.metadata_, {"access_level": "read"})
        self.assertEqual(second.metadata_, {})
        self.assertNotEqual(first.metadata_, second.metadata_)
        self.assertIsNotNone(first.occurred_at)

    def test_rejects_partially_specified_targets(self) -> None:
        self.session.add(
            AuditEvent(
                event_type=AuditEventType.DOCUMENT_READ,
                outcome=AuditEventOutcome.SUCCEEDED,
                target_type="document",
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

        self.session.add(
            AuditEvent(
                event_type=AuditEventType.DOCUMENT_READ,
                outcome=AuditEventOutcome.SUCCEEDED,
                target_id=12,
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.commit()
