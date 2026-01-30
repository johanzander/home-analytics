"""
Home Analytics Add-on Backend Application

Simple FastAPI application serving a Home Analytics endpoint.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# Import API router
from api import router as api_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Get ingress prefix from environment variable (set by Home Assistant)
INGRESS_PREFIX = os.environ.get("INGRESS_PREFIX", "")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan manager for startup/shutdown."""
    # Startup
    logger.info("Home Analytics Add-on starting")
    logger.info(f"Ingress prefix: {INGRESS_PREFIX}")

    # Log registered routes
    routes = [
        f"{getattr(route, 'path', '?')} - {getattr(route, 'methods', ['MOUNT'])}"
        for route in app.routes
    ]
    logger.info(f"Registered routes: {routes}")

    yield

    # Shutdown
    logger.info("Home Analytics Add-on shutting down")


# Create FastAPI app with root_path for Home Assistant ingress
app = FastAPI(
    title="Home Analytics Add-on",
    description="A simple Home Assistant Add-on template",
    version="0.1.0",
    lifespan=lifespan,
    root_path=INGRESS_PREFIX,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api", tags=["api"])

# Mount static files for frontend assets
static_directory = "/app/frontend"  # In production
if not os.path.exists(static_directory):
    static_directory = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

# Mount assets directory (Vite builds to assets/)
assets_directory = os.path.join(static_directory, "assets")
if os.path.exists(assets_directory):
    app.mount("/assets", StaticFiles(directory=assets_directory), name="assets")


# Handle root path
@app.get("/", response_model=None)
async def root() -> FileResponse | HTMLResponse:
    """Serve the frontend index.html."""
    # Check production path first
    frontend_path = "/app/frontend/index.html"
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)

    # Check development path
    dev_path = os.path.join(
        os.path.dirname(__file__), "..", "frontend", "dist", "index.html"
    )
    if os.path.exists(dev_path):
        return FileResponse(dev_path)

    # Fallback for development when frontend isn't built
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Home Analytics Add-on</title></head>
    <body>
        <h1>Home Analytics Add-on</h1>
        <p>Frontend not built yet. Run <code>cd frontend && npm run build</code></p>
        <p>API endpoints: <a href="/api/hello">/api/hello</a> | <a href="/docs">/docs</a></p>
    </body>
    </html>
    """)


@app.get("/api/root")
async def api_root() -> dict:
    """Root endpoint returning Home Analytics message."""
    return {"message": "Home Analytics from Home Assistant Add-on!"}


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
