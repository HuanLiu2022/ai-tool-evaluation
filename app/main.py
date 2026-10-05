"""FastAPI application entry point for local technical-document analysis."""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="AI Tool Evaluation for Technical Document Analysis",
    version="0.1.0",
    description="Local PDF analysis using PyMuPDF and Ollama.",
)
app.include_router(router)
