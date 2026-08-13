import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError
from qdrant_client import QdrantClient, models

from app.core.config import Settings
from app.integrations.vector_store.qdrant_client import create_qdrant_client
from app.integrations.vector_store.exceptions import VectorStoreConfigurationError
from app.integrations.vector_store.exceptions import VectorStoreOperationError
from app.integrations.vector_store.qdrant_store import QdrantVectorPoint
from app.integrations.vector_store.qdrant_store import QdrantSearchCandidate
from app.integrations.vector_store.qdrant_store import QdrantVectorStore


class VectorStoreConfigurationTests(unittest.TestCase):
    _REQUIRED_SETTINGS = {
        "APP_NAME": "AegisAI",
        "APP_VERSION": "test",
        "APP_ENV": "test",
        "HOST": "127.0.0.1",
        "PORT": 8000,
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "QDRANT_URL": "http://qdrant:6333",
        "JWT_SECRET_KEY": "test-secret",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
    }

    def test_uses_the_phase_nine_default_collection_and_embedding_shape(self) -> None:
        configuration = Settings(**self._REQUIRED_SETTINGS)

        self.assertEqual(configuration.QDRANT_COLLECTION_NAME, "aegis_document_chunks_v1")
        self.assertEqual(configuration.QDRANT_TIMEOUT_SECONDS, 10.0)
        self.assertEqual(configuration.EMBEDDING_PROVIDER, "openai")
        self.assertEqual(configuration.EMBEDDING_MODEL, "text-embedding-3-small")
        self.assertEqual(configuration.EMBEDDING_VECTOR_DIMENSION, 1_536)
        self.assertEqual(configuration.EMBEDDING_BATCH_SIZE, 64)

    def test_rejects_invalid_vector_store_and_embedding_configuration(self) -> None:
        invalid_values = (
            {"QDRANT_URL": "qdrant:6333"},
            {"QDRANT_COLLECTION_NAME": "aegis document chunks"},
            {"QDRANT_TIMEOUT_SECONDS": 0},
            {"EMBEDDING_VECTOR_DIMENSION": 0},
            {"EMBEDDING_BATCH_SIZE": 0},
            {"EMBEDDING_REQUEST_TIMEOUT_SECONDS": 121},
            {"OPENAI_BASE_URL": "api.openai.com/v1"},
        )

        for overrides in invalid_values:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValidationError):
                    Settings(**(self._REQUIRED_SETTINGS | overrides))


class QdrantClientFactoryTests(unittest.TestCase):
    _REQUIRED_SETTINGS = VectorStoreConfigurationTests._REQUIRED_SETTINGS

    @patch("app.integrations.vector_store.qdrant_client.QdrantClient")
    def test_creates_a_client_from_validated_settings_without_contacting_qdrant(self, client_class) -> None:
        configuration = Settings(
            **(
                self._REQUIRED_SETTINGS
                | {
                    "QDRANT_URL": "https://qdrant.example.test/",
                    "QDRANT_API_KEY": "qdrant-secret",
                    "QDRANT_TIMEOUT_SECONDS": 7.5,
                }
            )
        )

        created = create_qdrant_client(configuration)

        self.assertIs(created, client_class.return_value)
        client_class.assert_called_once_with(
            url="https://qdrant.example.test",
            api_key="qdrant-secret",
            timeout=7.5,
        )

    @patch("app.integrations.vector_store.qdrant_client.QdrantClient")
    def test_uses_no_api_key_for_the_local_unauthenticated_service(self, client_class) -> None:
        create_qdrant_client(Settings(**(self._REQUIRED_SETTINGS | {"QDRANT_API_KEY": ""})))

        self.assertIsNone(client_class.call_args.kwargs["api_key"])


class QdrantVectorPointTests(unittest.TestCase):
    def test_normalizes_a_uuid_and_exposes_only_the_safe_payload(self) -> None:
        point = QdrantVectorPoint(
            point_id="A911E79C-97E2-4B68-8974-803034FC62CA",
            vector=(1, 2.5),
            document_id=3,
            chunk_id=4,
            document_extraction_id=5,
            uploader_user_id=6,
            content_type="text/plain",
            embedding_provider="openai",
            embedding_model="test-model",
        )

        self.assertEqual(point.point_id, "a911e79c-97e2-4b68-8974-803034fc62ca")
        self.assertEqual(point.vector, (1.0, 2.5))
        self.assertEqual(
            point.payload,
            {
                "document_id": 3,
                "chunk_id": 4,
                "document_extraction_id": 5,
                "uploader_user_id": 6,
                "content_type": "text/plain",
                "embedding_provider": "openai",
                "embedding_model": "test-model",
            },
        )

    def test_rejects_invalid_point_data_before_contacting_qdrant(self) -> None:
        valid_values = {
            "point_id": "a911e79c-97e2-4b68-8974-803034fc62ca",
            "vector": (1.0, 2.0),
            "document_id": 3,
            "chunk_id": 4,
            "document_extraction_id": 5,
            "uploader_user_id": 6,
            "content_type": "text/plain",
            "embedding_provider": "openai",
            "embedding_model": "test-model",
        }

        for overrides in (
            {"point_id": "not-a-uuid"},
            {"vector": ()},
            {"vector": (1.0, float("nan"))},
            {"document_id": 0},
            {"content_type": ""},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    QdrantVectorPoint(**(valid_values | overrides))


class QdrantVectorStoreTests(unittest.TestCase):
    _REQUIRED_SETTINGS = VectorStoreConfigurationTests._REQUIRED_SETTINGS

    def _configuration(self) -> Settings:
        return Settings(
            **(
                self._REQUIRED_SETTINGS
                | {
                    "QDRANT_COLLECTION_NAME": "unit_test_vectors",
                    "EMBEDDING_VECTOR_DIMENSION": 3,
                }
            )
        )

    @staticmethod
    def _point() -> QdrantVectorPoint:
        return QdrantVectorPoint(
            point_id="a911e79c-97e2-4b68-8974-803034fc62ca",
            vector=(0.1, 0.2, 0.3),
            document_id=3,
            chunk_id=4,
            document_extraction_id=5,
            uploader_user_id=6,
            content_type="text/plain",
            embedding_provider="openai",
            embedding_model="test-model",
        )

    def test_creates_validates_upserts_and_deletes_with_an_in_memory_qdrant(self) -> None:
        client = QdrantClient(":memory:")
        store = QdrantVectorStore(client, self._configuration())
        point = self._point()
        try:
            # Local Qdrant intentionally does not implement payload indexes;
            # the real server receives the same calls without this warning.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                self.assertEqual(store.upsert_points([point]), 1)

            collection = client.get_collection("unit_test_vectors")
            self.assertEqual(collection.config.params.vectors.size, 3)
            self.assertEqual(collection.config.params.vectors.distance, models.Distance.COSINE)
            stored = client.retrieve(
                collection_name="unit_test_vectors",
                ids=[point.point_id],
                with_vectors=True,
            )
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].id, point.point_id)
            self.assertEqual(stored[0].payload, point.payload)
            self.assertEqual(len(stored[0].vector), 3)
            self.assertAlmostEqual(stored[0].vector[0], 0.26726124)
            self.assertAlmostEqual(stored[0].vector[1], 0.53452248)
            self.assertAlmostEqual(stored[0].vector[2], 0.80178373)

            self.assertEqual(store.delete_points([point.point_id]), 1)
            self.assertEqual(
                client.retrieve(collection_name="unit_test_vectors", ids=[point.point_id]),
                [],
            )
        finally:
            client.close()

    def test_search_returns_scored_active_identity_candidates_without_vectors(self) -> None:
        client = QdrantClient(":memory:")
        store = QdrantVectorStore(client, self._configuration())
        point = QdrantVectorPoint(
            point_id="a911e79c-97e2-4b68-8974-803034fc62ca",
            vector=(0.1, 0.2, 0.3),
            document_id=3,
            chunk_id=4,
            document_extraction_id=5,
            uploader_user_id=6,
            content_type="text/plain",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )
        second_point = QdrantVectorPoint(
            point_id="b911e79c-97e2-4b68-8974-803034fc62ca",
            vector=(0.1, 0.2, 0.3),
            document_id=7,
            chunk_id=8,
            document_extraction_id=9,
            uploader_user_id=10,
            content_type="application/pdf",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                store.upsert_points([point, second_point])

            candidates = store.search(
                vector=(0.1, 0.2, 0.3),
                provider="openai",
                model="text-embedding-3-small",
                limit=5,
            )

            self.assertEqual(len(candidates), 2)
            self.assertTrue(all(isinstance(candidate, QdrantSearchCandidate) for candidate in candidates))
            point_candidate = next(candidate for candidate in candidates if candidate.point_id == point.point_id)
            self.assertAlmostEqual(point_candidate.score, 1.0)
            self.assertEqual(point_candidate.payload, point.payload)

            filtered_candidates = store.search(
                vector=(0.1, 0.2, 0.3),
                provider="openai",
                model="text-embedding-3-small",
                limit=5,
                document_ids=[3],
                content_types=["text/plain"],
            )
            self.assertEqual([candidate.point_id for candidate in filtered_candidates], [point.point_id])
        finally:
            client.close()

    def test_search_rejects_identity_or_dimension_mismatch_before_query(self) -> None:
        client = Mock()
        store = QdrantVectorStore(client, self._configuration())

        with self.assertRaises(VectorStoreConfigurationError):
            store.search(
                vector=(1.0, 2.0, 3.0),
                provider="other",
                model="text-embedding-3-small",
                limit=5,
            )
        with self.assertRaises(VectorStoreConfigurationError):
            store.search(
                vector=(1.0, 2.0),
                provider="openai",
                model="text-embedding-3-small",
                limit=5,
            )
        client.collection_exists.assert_not_called()

    def test_search_returns_empty_for_missing_collection_and_wraps_qdrant_failures(self) -> None:
        client = Mock()
        client.collection_exists.return_value = False
        store = QdrantVectorStore(client, self._configuration())

        self.assertEqual(
            store.search(
                vector=(1.0, 2.0, 3.0),
                provider="openai",
                model="text-embedding-3-small",
                limit=5,
            ),
            [],
        )

        client.collection_exists.side_effect = RuntimeError("Qdrant internals")
        with self.assertRaisesRegex(VectorStoreOperationError, "Document-vector storage is unavailable"):
            store.search(
                vector=(1.0, 2.0, 3.0),
                provider="openai",
                model="text-embedding-3-small",
                limit=5,
            )

    def test_search_rejects_unsupported_or_duplicate_metadata_filters(self) -> None:
        client = Mock()
        store = QdrantVectorStore(client, self._configuration())

        invalid_filters = (
            {"document_ids": [1, 1]},
            {"document_ids": [0]},
            {"content_types": ["application/octet-stream"]},
            {"content_types": ["text/plain", "text/plain"]},
            {"content_types": []},
        )
        for overrides in invalid_filters:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                store.search(
                    vector=(1.0, 2.0, 3.0),
                    provider="openai",
                    model="text-embedding-3-small",
                    limit=5,
                    **overrides,
                )
        client.collection_exists.assert_not_called()

    def test_rejects_an_existing_collection_with_a_different_dimension_without_mutating_it(self) -> None:
        client = Mock()
        client.collection_exists.return_value = True
        client.get_collection.return_value = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=models.VectorParams(size=2, distance=models.Distance.COSINE)
                )
            )
        )

        with self.assertRaises(VectorStoreConfigurationError):
            QdrantVectorStore(client, self._configuration()).ensure_collection()

        client.create_collection.assert_not_called()
        client.create_payload_index.assert_not_called()

    def test_rejects_a_vector_with_the_wrong_dimension_before_creating_a_collection(self) -> None:
        client = Mock()
        point = self._point()
        wrong_dimension_point = QdrantVectorPoint(
            **(
                {field: getattr(point, field) for field in point.__dataclass_fields__}
                | {"vector": (1.0,)}
            )
        )

        with self.assertRaises(VectorStoreConfigurationError):
            QdrantVectorStore(client, self._configuration()).upsert_points([wrong_dimension_point])

        client.collection_exists.assert_not_called()

    def test_converts_qdrant_failures_to_safe_operation_errors(self) -> None:
        client = Mock()
        client.collection_exists.side_effect = RuntimeError("connection details must not escape")

        with self.assertRaisesRegex(VectorStoreOperationError, "Document-vector storage is unavailable"):
            QdrantVectorStore(client, self._configuration()).ensure_collection()
