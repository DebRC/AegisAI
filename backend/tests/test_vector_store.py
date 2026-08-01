import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.vector_store.qdrant_client import create_qdrant_client


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
        create_qdrant_client(Settings(**self._REQUIRED_SETTINGS))

        self.assertIsNone(client_class.call_args.kwargs["api_key"])
