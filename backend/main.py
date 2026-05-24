# backend/main.py

import logging
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # <-- IMPORT THIS
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config import get_settings
from api.travel_api_app import create_travel_app

settings = get_settings()
logger = logging.getLogger("main_orchestrator")

def start_application():
    master_app = FastAPI(title="LEO AI Ecosystem")

    # ========================================
    # GLOBAL MIDDLEWARE (CORS)
    # ========================================
    master_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Update this in production (e.g., ["http://localhost:3000"])
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 1. Mount Sub-APIs
    travel_app = create_travel_app()
    master_app.mount("/travel", travel_app)
    logger.info("🚀 Travel API App mounted at /travel")

    # 2. Mount Frontend at the True Root (/)
    if os.path.exists(settings.FRONTEND_DIR):
        # Serve the /assets directory
        master_app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIR), name="assets")
        logger.info(f"✅ Frontend assets mounted from: {settings.FRONTEND_DIR}")
        
        # Serve the index.html on the root path
        @master_app.get("/", include_in_schema=False)
        @master_app.get("/index.html", include_in_schema=False)
        async def serve_index():
            return FileResponse(os.path.join(settings.FRONTEND_DIR, "index.html"))
        
        # Serve the static files (CSS/JS) from the frontend directory
        @master_app.get("/static/{file_path:path}", include_in_schema=False)
        async def serve_static(file_path: str):
            static_file_path = os.path.join(settings.FRONTEND_DIR, "static", file_path)
            if not os.path.exists(static_file_path):
                logger.error(f"❌ Static file not found: {static_file_path}")
                return JSONResponse({"detail": "Static file not found"}, status_code=404)
            return FileResponse(static_file_path)
            
        # Optional: Catch-all for SPA routing (React/Vue/Angular)
        @master_app.exception_handler(404)
        async def custom_404_handler(request, __):
            if request.url.path.startswith(settings.API_PREFIX) or request.url.path.startswith("/travel"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(os.path.join(settings.FRONTEND_DIR, "index.html"))
            
    else:
        logger.warning(f"⚠️ Frontend directory missing at {settings.FRONTEND_DIR}")

    return master_app

app = start_application()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8888, reload=True)