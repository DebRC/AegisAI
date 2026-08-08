import unittest

from pydantic import ValidationError

from app.schemas.retrieval import RetrievalSearchRequest
from app.schemas.retrieval import RetrievalSearchResponse
from app.schemas.retrieval import RetrievalSearchResult


class RetrievalSchemaTests(unittest.TestCase):
    def test_search_request_normalizes_and_bounds_public_filters(self) -> None:
        request = RetrievalSearchRequest(
            query="  rotate refresh tokens  ",
            limit=5,
            document_ids=[12, 18],
            content_types=["text/markdown", "application/pdf"],
        )

        self.assertEqual(request.query, "rotate refresh tokens")
        self.assertEqual(request.limit, 5)
        self.assertEqual(request.document_ids, [12, 18])
        self.assertEqual(request.content_types, ["text/markdown", "application/pdf"])

    def test_search_request_rejects_empty_query_untrusted_filters_and_duplicates(self) -> None:
        invalid_requests = (
            {"query": "   "},
            {"query": "policy", "limit": 21},
            {"query": "policy", "document_ids": [1, 1]},
            {"query": "policy", "document_ids": [0]},
            {"query": "policy", "document_ids": []},
            {"query": "policy", "content_types": ["text/plain", "text/plain"]},
            {"query": "policy", "content_types": ["application/octet-stream"]},
            {"query": "policy", "content_types": []},
        )

        for values in invalid_requests:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                RetrievalSearchRequest(**values)

    def test_response_keeps_source_text_and_similarity_score_explicit(self) -> None:
        response = RetrievalSearchResponse(
            items=[
                RetrievalSearchResult(
                    document_id=12,
                    document_title="Authentication design",
                    content_type="text/markdown",
                    chunk_id=47,
                    chunk_ordinal=3,
                    content="Refresh tokens rotate after a successful refresh.",
                    source_locations=[{"kind": "line", "start": 82, "end": 96}],
                    score=0.91,
                )
            ],
            limit=5,
        )

        self.assertEqual(response.items[0].chunk_id, 47)
        self.assertEqual(response.items[0].score, 0.91)

        with self.assertRaises(ValidationError):
            RetrievalSearchResult(
                document_id=12,
                document_title="Authentication design",
                content_type="text/markdown",
                chunk_id=47,
                chunk_ordinal=3,
                content="content",
                source_locations=None,
                score=float("nan"),
            )
