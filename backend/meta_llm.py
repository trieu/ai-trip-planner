import os
from typing import Union
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

class MetaLLM:
    """
    Factory class to provide LLM and Embedding instances 
    based on the configured LLM_PROVIDER.
    """
    
    @staticmethod
    def get_llm(temperature: float = 0.7):
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
                google_api_key=os.getenv("GOOGLE_GEMINI_API_KEY")
            )

    @staticmethod
    def get_embeddings():
        provider = os.getenv("LLM_PROVIDER", "GOOGLE_GEMINI").upper()
        model_name = os.getenv("EMBEDDING_MODEL_NAME")

        if provider == "OPENAI":
            return OpenAIEmbeddings(
                model=model_name or "text-embedding-3-small",
                api_key=os.getenv("OPENAI_API_KEY")
            )
        else:
            return GoogleGenerativeAIEmbeddings(
                model=model_name or "models/text-embedding-004",
                google_api_key=os.getenv("GOOGLE_GEMINI_API_KEY")
            )