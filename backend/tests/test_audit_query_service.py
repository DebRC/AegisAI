from datetime import datetime, timedelta, timezone
import unittest

from app.core.exceptions import AuditEventValidationError
from app.models import AuditEventOutcome
from app.models import AuditEventType
from app.services.audit_event_service import AuditEventService
from app.services.audit_query_service import AuditQueryService
from tests.helpers import DatabaseTestCase


class AuditQueryServiceTests(DatabaseTestCase, unittest.TestCase):
    def setUp(self) -> None:
        self.set_up_database()
        self.actor = self.create_user("actor@example.com")
        self.other_actor = self.create_user("other@example.com")
        self.writer = AuditEventService(self.session)
        self.service = AuditQueryService(self.session)
        self.now = datetime.now(timezone.utc)
        self._event(AuditEventType.DOCUMENT_READ, self.actor.id, "document", 10)
        self._event(AuditEventType.RETRIEVAL_SEARCH, self.actor.id, None, None)
        self._event(AuditEventType.DOCUMENT_DELETED, self.other_actor.id, "document", 11)

    def tearDown(self) -> None:
        self.tear_down_database()

    def test_lists_newest_first_with_allow_list_filters_and_total(self) -> None:
        page = self.service.list_events(offset=0, limit=1, actor_user_id=self.actor.id)

        self.assertEqual(page.total, 2)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].event_type, AuditEventType.RETRIEVAL_SEARCH)

        document_page = self.service.list_events(
            offset=0,
            limit=25,
            target_type="document",
            target_id=10,
            event_type=AuditEventType.DOCUMENT_READ,
            occurred_after=self.now - timedelta(minutes=1),
            occurred_before=self.now + timedelta(minutes=1),
        )
        self.assertEqual([item.target_id for item in document_page.items], [10])

    def test_rejects_unbounded_or_inconsistent_filters(self) -> None:
        invalid_filters = (
            {"offset": -1},
            {"limit": 101},
            {"actor_user_id": 0},
            {"target_type": "email"},
            {"target_id": 10},
            {"occurred_after": self.now, "occurred_before": self.now - timedelta(seconds=1)},
        )
        for invalid in invalid_filters:
            with self.subTest(invalid=invalid):
                with self.assertRaises(AuditEventValidationError):
                    self.service.list_events(**({"offset": 0, "limit": 25} | invalid))

    def _event(
        self,
        event_type: AuditEventType,
        actor_user_id: int,
        target_type: str | None,
        target_id: int | None,
    ) -> None:
        self.writer.record(
            event_type=event_type,
            outcome=AuditEventOutcome.SUCCEEDED,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
        )
        self.session.commit()
