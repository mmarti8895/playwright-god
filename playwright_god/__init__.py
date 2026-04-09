"""playwright-god: AI-powered Playwright test generator backed by RAG."""

from .auth_templates import (
    AUTH_TYPES,
    LOGGING_FIXTURE_TEMPLATE,
    NTLM_AUTH_TEMPLATE,
    OIDC_AUTH_TEMPLATE,
    SAML_AUTH_TEMPLATE,
    get_auth_hint,
    get_template,
)
from .crawler import FileInfo, RepositoryCrawler
from .chunker import Chunk, FileChunker
from .embedder import DefaultEmbedder, EmbeddingFunction, MockEmbedder
from .indexer import RepositoryIndexer, SearchResult
from .generator import (
    AnthropicClient,
    GeminiClient,
    LLMClient,
    OllamaClient,
    OpenAIClient,
    PlaywrightTestGenerator,
    TemplateLLMClient,
)

__all__ = [
    "AUTH_TYPES",
    "AnthropicClient",
    "Chunk",
    "DefaultEmbedder",
    "EmbeddingFunction",
    "FileChunker",
    "FileInfo",
    "GeminiClient",
    "LLMClient",
    "LOGGING_FIXTURE_TEMPLATE",
    "MockEmbedder",
    "NTLM_AUTH_TEMPLATE",
    "OIDC_AUTH_TEMPLATE",
    "OllamaClient",
    "OpenAIClient",
    "PlaywrightTestGenerator",
    "RepositoryCrawler",
    "RepositoryIndexer",
    "SAML_AUTH_TEMPLATE",
    "SearchResult",
    "TemplateLLMClient",
    "get_auth_hint",
    "get_template",
]
