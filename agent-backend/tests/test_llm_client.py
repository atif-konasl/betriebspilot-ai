"""
Unit tests for BetriebsPilot AI multi-provider LLM client with Instructor.
"""

from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel, Field

from src.llm.client import (
    LLMClient,
    LLMSettings,
    LLMConfigurationError,
    LLMConnectionError,
    get_llm_client
)

class SampleERPOrderLine(BaseModel):
    raw_text: str = Field(description="Raw customer line text")
    sku_candidate: str = Field(description="Suggested SKU")
    quantity: int = Field(description="Extracted quantity")
    unit: str = Field(description="Unit of measure")

def test_ollama_initialization():
    settings = LLMSettings(
        LLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="qwen2.5:7b-instruct-q4_K_M"
    )
    client = LLMClient(settings=settings)
    assert client.provider == "ollama"
    assert client.model_name == "qwen2.5:7b-instruct-q4_K_M"
    assert client.client.base_url.host == "localhost"

def test_openai_missing_key_raises_error():
    settings = LLMSettings(LLM_PROVIDER="openai", OPENAI_API_KEY=None)
    with pytest.raises(LLMConfigurationError) as exc_info:
        LLMClient(settings=settings, provider="openai")
    assert "OPENAI_API_KEY is not defined" in str(exc_info.value)

def test_openai_valid_key_initializes():
    settings = LLMSettings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="sk-test-mock-key",
        OPENAI_MODEL="gpt-4o-mini"
    )
    client = LLMClient(settings=settings, provider="openai")
    assert client.provider == "openai"
    assert client.model_name == "gpt-4o-mini"

def test_groq_missing_key_raises_error():
    settings = LLMSettings(LLM_PROVIDER="groq", GROQ_API_KEY=None)
    with pytest.raises(LLMConfigurationError) as exc_info:
        LLMClient(settings=settings, provider="groq")
    assert "GROQ_API_KEY is not defined" in str(exc_info.value)

def test_groq_valid_key_initializes():
    settings = LLMSettings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY="gsk-test-mock-key",
        GROQ_MODEL="llama-3.3-70b-versatile"
    )
    client = LLMClient(settings=settings, provider="groq")
    assert client.provider == "groq"
    assert client.model_name == "llama-3.3-70b-versatile"

def test_unsupported_provider_raises_error():
    with pytest.raises(LLMConfigurationError) as exc_info:
        LLMClient(provider="unsupported_engine")
    assert "Unsupported LLM provider" in str(exc_info.value)

def test_extract_structured_mocked():
    client = LLMClient(provider="ollama")
    expected = SampleERPOrderLine(
        raw_text="50 Kartons Sechskantschrauben M8x30",
        sku_candidate="ART-DIN-933-M8X30",
        quantity=50,
        unit="KTN"
    )
    client.instructor_client.chat.completions.create = MagicMock(return_value=expected)

    result = client.extract_structured(
        response_model=SampleERPOrderLine,
        messages=[{"role": "user", "content": "Bestellung: 50 Kartons Sechskantschrauben M8x30"}]
    )

    assert result.sku_candidate == "ART-DIN-933-M8X30"
    assert result.quantity == 50
    assert result.unit == "KTN"

def test_health_check_handles_offline_gracefully():
    client = LLMClient(provider="ollama")
    health = client.check_health()
    assert health["provider"] == "ollama"
    assert "status" in health
    assert "reachable" in health

def test_factory_function_caching():
    client1 = get_llm_client("ollama")
    client2 = get_llm_client("ollama")
    assert client1 is client2
