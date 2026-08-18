import unittest

from app.chat.citations import CitationValidationError
from app.chat.citations import CitationValidator
from app.chat.prompting import GroundedPromptBuilder
from app.schemas.retrieval import RetrievalSearchResult


class CitationValidatorTests(unittest.TestCase):
    def _prompt(self):
        results = [
            RetrievalSearchResult(
                document_id=3,
                document_title="Security guide",
                content_type="text/markdown",
                chunk_id=7,
                chunk_ordinal=2,
                content="AegisAI uses verified context.",
                source_locations=[{"page": 4}],
                score=0.91,
            ),
            RetrievalSearchResult(
                document_id=4,
                document_title="Operations guide",
                content_type="text/plain",
                chunk_id=8,
                chunk_ordinal=0,
                content="AegisAI streams answer fragments.",
                source_locations=None,
                score=0.82,
            ),
        ]
        return GroundedPromptBuilder(1_000).build("What does AegisAI do?", results)

    def test_issues_deduplicated_metadata_from_known_prompt_sources_only(self) -> None:
        citations = CitationValidator().citations_for("It verifies context [S2] and cites it [S1][S2].", self._prompt())

        self.assertEqual([citation.source_id for citation in citations], ["S2", "S1"])
        self.assertEqual(citations[0].document_title, "Operations guide")
        self.assertIsNone(citations[0].source_locations)
        self.assertEqual(citations[1].source_locations, [{"page": 4}])
        self.assertEqual(citations[1].score, 0.91)

    def test_allows_an_answer_without_citations_but_rejects_unknown_or_malformed_source_ids(self) -> None:
        validator = CitationValidator()
        prompt = self._prompt()

        self.assertEqual(validator.citations_for("The available context is insufficient.", prompt), ())
        for answer in ("Unsupported claim [S3].", "Malformed source [S01].", "Bad source [Sx]."):
            with self.subTest(answer=answer):
                with self.assertRaises(CitationValidationError):
                    validator.citations_for(answer, prompt)
