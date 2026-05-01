import logging
import os
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from core_llm.observer_utils import setup_observability
from config import Settings

# ============================================================
# Logging
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MetaLLM")

# ============================================================
# ENABLE TELEMETRY FOR AI OBSERVABILITY
# ============================================================
if Settings().ENABLE_TELEMETRY:
    logger.info("Telemetry enabled for AI observability, PHOENIX_COLLECTOR_ENDPOINT: %s",
                Settings().PHOENIX_COLLECTOR_ENDPOINT)
    setup_observability()

# ============================================================
# MetaLLM Factory
# ============================================================
class MetaLLM:
    """
    Factory class to provide LLM and Embedding instances 
    based on the configured LLM_PROVIDER. <br>
    Currently supports "GOOGLE_GEMINI" and "OPENAI". <br>
    Usage: <br>
- `MetaLLM.get_llm(temperature=0.7)` to get a chat model instance. <br>
- `MetaLLM.get_embeddings(dimensions=1536)` to get an embeddings instance. <br>
    """

    @staticmethod
    def get_llm(temperature: float = 0.7) -> BaseChatModel:
        provider = os.getenv("LLM_PROVIDER", "GOOGLE_GEMINI").upper()
        model_name = os.getenv("LLM_MODEL_NAME")

        if provider == "OPENAI":
            # Initializes OpenAI Chat model (requires langchain-openai)
            return ChatOpenAI(
                model=model_name or "gpt-4o",
                temperature=temperature,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        else:
            # Default to Google Gemini (requires langchain-google-genai)
            return ChatGoogleGenerativeAI(
                model=model_name or "gemini-2.5-flash-lite",
                temperature=temperature,
                api_key=os.getenv("GOOGLE_GEMINI_API_KEY")
            )

    @staticmethod
    def get_embeddings(dimensions: int = 1536) -> Embeddings:
        provider = os.getenv("LLM_PROVIDER", "GOOGLE_GEMINI").upper()
        model_name = os.getenv("EMBEDDING_MODEL_NAME")

        if provider == "OPENAI":
            return OpenAIEmbeddings(
                model=model_name or "text-embedding-3-small",
                api_key=os.getenv("OPENAI_API_KEY"),
                dimensions=dimensions  # Specific to OpenAI
            )
        else:
            return GoogleGenerativeAIEmbeddings(
                model=model_name or "gemini-embedding-2",
                google_api_key=os.getenv("GOOGLE_GEMINI_API_KEY"),
                output_dimensionality=dimensions  # Specific to Google GenAI
            )
