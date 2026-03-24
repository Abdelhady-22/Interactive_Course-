"""FastAPI application entry point."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import courses, paragraphs, assets, agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Interactive Course Platform",
    description=(
        "AI-powered layout director for interactive educational courses. "
        "Upload a video + script → AI agent decides optimal screen layouts → "
        "Review and approve → Publish for learners."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — permissive for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(courses.router)
app.include_router(paragraphs.router)
app.include_router(assets.router)
app.include_router(agent.router)


@app.get("/", tags=["Health"])
def root():
    """Health check and API info."""
    return {
        "name": "Interactive Course Platform",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """Health check."""
    return {"status": "ok"}
