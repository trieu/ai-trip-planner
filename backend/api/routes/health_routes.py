"""
Health check and status endpoints.
"""

from fastapi import APIRouter
from datetime import datetime
from config import get_settings

router = APIRouter(prefix="/health")
settings = get_settings()


@router.get("")
@router.get("/status")
async def health_check():
    """
    Health check endpoint.
    Returns application status and configuration info.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "version": "1.0.0",
    }


@router.get("/config")
async def get_config():
    """
    Get current configuration (non-sensitive fields).
    """
    return {
        "host": settings.HOST,
        "port": settings.PORT,
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL_NAME,
        "cache_enabled": settings.ENABLE_CACHING,
        "persona_reports_enabled": settings.ENABLE_PERSONA_REPORTS,
        "rag_enabled": settings.ENABLE_RAG,
        "api_prefix": settings.api_url_prefix,
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check for Kubernetes/orchestration.
    Returns 200 if app is ready to accept traffic.
    """
    return {"ready": True}
