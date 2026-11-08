"""
BetriebsPilot AI - Multi-Provider LLM Client with Instructor Integration
Supports local Ollama (default on-premise), OpenAI, and Groq with strict Pydantic
structured extraction, zero-temperature GoBD compliance, and automatic validation retries.
"""

import os
import logging
from typing import Type, TypeVar, List, Dict, Any, Optional, Literal
from pathlib import Path

import httpx
import openai
from openai import OpenAI
import instructor
from instructor.core import InstructorRetryException
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("betriebspilot.llm")

# Generic type for Pydantic response models
T = TypeVar("T", bound=BaseModel)

# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------
class LLMError(Exception):
    """Base exception for LLM operations."""
    pass

class LLMConfigurationError(LLMError):
    """Raised when provider configuration or API keys are missing/invalid."""
    pass

class LLMConnectionError(LLMError):
    """Raised when the LLM service endpoint cannot be reached."""
    pass

class LLMExtractionError(LLMError):
    """Raised when structured extraction fails to validate against the schema."""
    pass

# ------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------
class LLMSettings(BaseSettings):
    """Configuration settings for LLM providers, loaded from .env or environment."""
    
    # Provider selection
    llm_provider: Literal["ollama", "openai", "groq"] = Field(
        default="ollama",
        validation_alias="LLM_PROVIDER"
    )
    
    # Local Ollama Settings
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(
        default="qwen2.5:7b",
        validation_alias="OLLAMA_MODEL"
    )
    
    # OpenAI Cloud Settings
    openai_api_key: Optional[str] = Field(
        default=None,
        validation_alias="OPENAI_API_KEY"
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias="OPENAI_MODEL"
    )
    openai_base_url: Optional[str] = Field(
        default=None,
        validation_alias="OPENAI_BASE_URL"
    )
    
    # Groq Cloud Settings
    groq_api_key: Optional[str] = Field(
        default=None,
        validation_alias="GROQ_API_KEY"
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias="GROQ_MODEL"
    )
    
    # Operational Guardrails (Strict temperature 0.0 for GoBD compliance)
    temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    max_retries: int = Field(default=3, validation_alias="LLM_MAX_RETRIES")
    timeout_seconds: float = Field(default=60.0, validation_alias="LLM_TIMEOUT_SECONDS")
    debug: bool = Field(default=False, validation_alias="DEBUG")

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# ------------------------------------------------------------------------------
# LLM Client Implementation
# ------------------------------------------------------------------------------
class LLMClient:
    """
    Unified LLM Client providing Instructor-powered structured extraction and
    unstructured chat completions across Ollama, OpenAI, and Groq.
    """

    def __init__(self, settings: Optional[LLMSettings] = None, provider: Optional[str] = None):
        self.settings = settings or LLMSettings()
        self.provider = (provider or self.settings.llm_provider).lower()
        self.client: OpenAI
        self.instructor_client: instructor.Instructor
        self.model_name: str

        self._initialize_provider()

    def _initialize_provider(self):
        """Initializes raw OpenAI client and wraps it with Instructor based on provider."""
        timeout = httpx.Timeout(self.settings.timeout_seconds, connect=10.0)

        if self.provider == "ollama":
            base_url = f"{self.settings.ollama_base_url.rstrip('/')}/v1"
            self.model_name = self.settings.ollama_model
            logger.info(f"Initializing Local Ollama provider at {base_url} (model: {self.model_name})")

            # Ollama exposes an OpenAI-compatible endpoint at /v1
            self.client = OpenAI(
                base_url=base_url,
                api_key="ollama", # Ollama ignores api_key, but OpenAI client requires non-empty string
                timeout=timeout
            )
            # Use JSON mode for Ollama local models with instructor
            self.instructor_client = instructor.from_openai(
                self.client,
                mode=instructor.Mode.JSON
            )

        elif self.provider == "openai":
            if not self.settings.openai_api_key:
                raise LLMConfigurationError(
                    "LLM_PROVIDER is set to 'openai', but OPENAI_API_KEY is not defined in your environment or .env file."
                )
            self.model_name = self.settings.openai_model
            base_url = self.settings.openai_base_url
            logger.info(f"Initializing OpenAI provider (model: {self.model_name})")

            self.client = OpenAI(
                api_key=self.settings.openai_api_key,
                base_url=base_url,
                timeout=timeout
            )
            self.instructor_client = instructor.from_openai(
                self.client,
                mode=instructor.Mode.TOOLS
            )

        elif self.provider == "groq":
            if not self.settings.groq_api_key:
                raise LLMConfigurationError(
                    "LLM_PROVIDER is set to 'groq', but GROQ_API_KEY is not defined in your environment or .env file."
                )
            self.model_name = self.settings.groq_model
            logger.info(f"Initializing Groq provider (model: {self.model_name})")

            self.client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.settings.groq_api_key,
                timeout=timeout
            )
            self.instructor_client = instructor.from_openai(
                self.client,
                mode=instructor.Mode.TOOLS
            )

        else:
            raise LLMConfigurationError(
                f"Unsupported LLM provider '{self.provider}'. Must be one of: 'ollama', 'openai', 'groq'."
            )

    def extract_structured(
        self,
        response_model: Type[T],
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_retries: Optional[int] = None,
        **kwargs: Any
    ) -> T:
        """
        Extracts structured data from an LLM prompt and validates it into a Pydantic model.
        Automatically retries with validation feedback if the model output violates the schema.
        """
        temp = temperature if temperature is not None else self.settings.temperature
        retries = max_retries if max_retries is not None else self.settings.max_retries

        if self.settings.debug:
            logger.debug(f"Calling structured extraction with model '{self.model_name}' (temp: {temp}):\n{messages}")

        try:
            structured_response = self.instructor_client.chat.completions.create(
                model=self.model_name,
                response_model=response_model,
                messages=messages,
                temperature=temp,
                max_retries=retries,
                **kwargs
            )
            return structured_response

        except httpx.ConnectError as e:
            msg = f"Failed to connect to LLM provider '{self.provider}' at endpoint."
            if self.provider == "ollama":
                msg += f" Ensure Ollama is running at {self.settings.ollama_base_url} (run 'ollama serve' or check Docker)."
            raise LLMConnectionError(msg) from e

        except openai.NotFoundError as e:
            msg = f"Model '{self.model_name}' was not found on provider '{self.provider}'."
            if self.provider == "ollama":
                msg += f" Please pull the model first using 'ollama pull {self.model_name}' or check OLLAMA_MODEL in .env."
            logger.error(msg)
            raise LLMConfigurationError(msg) from e

        except InstructorRetryException as e:
            raise LLMExtractionError(
                f"Failed to extract valid {response_model.__name__} schema after {retries} retries: {e}"
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error during structured extraction with {self.provider}: {e}")
            raise LLMError(f"LLM extraction failed: {str(e)}") from e

    def generate_text(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs: Any
    ) -> str:
        """Generates plain text completion (unstructured) using the underlying provider."""
        temp = temperature if temperature is not None else self.settings.temperature
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temp,
                **kwargs
            )
            return response.choices[0].message.content or ""
        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f"Failed to connect to LLM provider '{self.provider}'."
            ) from e
        except Exception as e:
            raise LLMError(f"LLM text generation failed: {str(e)}") from e

    def check_health(self) -> Dict[str, Any]:
        """
        Verifies provider connectivity and checks if the configured model is available.
        Returns health status dict.
        """
        try:
            # Simple 1-token probe
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1
            )
            return {
                "status": "healthy",
                "provider": self.provider,
                "model": self.model_name,
                "reachable": True
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider,
                "model": self.model_name,
                "reachable": False,
                "error": str(e)
            }


# ------------------------------------------------------------------------------
# Factory Function
# ------------------------------------------------------------------------------
_client_instances: Dict[str, LLMClient] = {}

def get_llm_client(provider: Optional[str] = None, settings: Optional[LLMSettings] = None) -> LLMClient:
    """
    Factory function providing cached LLMClient instances per provider.
    """
    prov = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
    if prov not in _client_instances:
        _client_instances[prov] = LLMClient(settings=settings, provider=prov)
    return _client_instances[prov]
