from contextlib import asynccontextmanager
import logging
import os



from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse  # Added for serving files
from fastapi.staticfiles import StaticFiles # Added for serving directory assets

from config import get_settings

# Import route modules
from api.routes import trip_routes, persona_routes, health_routes, auth_routes



# ========================================
# Configuration
# ========================================
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ========================================
# Lifespan Events
# ========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Application starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER}")
    logger.info(f"API Prefix: {settings.API_PREFIX} | Host: {settings.HOST}:{settings.PORT}")
    
    settings.log_config()
    
    yield
    
    # Shutdown
    logger.info("🛑 Application shutting down...")


# ========================================
# Application Initialization
# ========================================
app = FastAPI(
    title="AI Trip Planner API",
    description="Personalized travel itinerary planning with AI",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# ========================================
# Static Files
# ========================================

# Serve frontend files
if os.path.exists(settings.FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIR), name="assets")
    logger.info(f"✅ Frontend assets mounted from: {settings.FRONTEND_DIR}")
else:
    logger.warning(f"⚠️  Frontend directory not found: {settings.FRONTEND_DIR}")

# ========================================
# Routes
# ========================================

API_BASE = f"{settings.API_PREFIX}/{settings.API_VERSION}"

# Health routes
app.include_router(
    health_routes.router,
    prefix=API_BASE,
    tags=["health"],
)

# Trip planning routes
app.include_router(
    trip_routes.router,
    prefix=API_BASE,
    tags=["trips"],
)

# Auth routes
app.include_router(
    auth_routes.router,
    prefix=settings.API_PREFIX,
    tags=["auth"],
)

# Persona report routes
if settings.ENABLE_PERSONA_REPORTS:
    app.include_router(
        persona_routes.router,
        prefix=API_BASE,
        tags=["personas"],
    )
    
# ========================================
# Root Routes
# ========================================

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def serve_index():
    """Serve the frontend index.html."""
    index_path = os.path.join(settings.FRONTEND_DIR, "index.html")
    
    if not os.path.exists(index_path):
        logger.error(f"Frontend index.html not found: {index_path}")
        return {
            "error": "Frontend not found",
            "detail": f"Check FRONTEND_DIR config: {settings.FRONTEND_DIR}"
        }
    
    return FileResponse(index_path)

# ========================================
# Error Handlers
# ========================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return {
        "error": "Internal Server Error",
        "detail": str(exc) if settings.is_development else "An error occurred"
    }
    
# ========================================
# Startup Checks
# ========================================

@app.on_event("startup")
async def startup_checks():
    """Perform startup validation checks."""
    logger.info("🔍 Running startup checks...")
    
    # Check API keys
    if settings.LLM_PROVIDER == "OPENAI" and not settings.OPENAI_API_KEY:
        logger.error("❌ OPENAI_API_KEY not set but LLM_PROVIDER=OPENAI")
        raise RuntimeError("Missing OPENAI_API_KEY")
    
    if settings.LLM_PROVIDER == "GOOGLE_GEMINI" and not settings.GOOGLE_GEMINI_API_KEY:
        logger.error("❌ GOOGLE_GEMINI_API_KEY not set but LLM_PROVIDER=GOOGLE_GEMINI")
        raise RuntimeError("Missing GOOGLE_GEMINI_API_KEY")
    
    # Check data directories
    os.makedirs(settings.PERSONA_DATA_DIR, exist_ok=True)
    os.makedirs(settings.REPORTS_DATA_DIR, exist_ok=True)
    os.makedirs(settings.TEMPLATES_DIR, exist_ok=True)
    logger.info("✅ Data directories ready")
    
    logger.info("✅ Startup checks passed")

# ========================================
# Main Entry Point
# ========================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS if settings.is_production else 1,
        log_level=settings.LOG_LEVEL.lower(),
    )