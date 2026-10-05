"""FastAPI endpoints for health checks and uploaded-PDF analysis."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas import AnalysisResponse
from app.services.analysis import AnalysisError, AnalysisService, InvalidModelOutputError
from app.services.ollama import OllamaClientError

router = APIRouter()
analysis_service = AnalysisService()


@router.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalysisResponse, tags=["analysis"])
async def analyze_document(file: UploadFile = File(...)) -> AnalysisResponse:
    """Analyze an uploaded PDF using the configured local Ollama model."""
    if file.filename and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF uploads are supported.")
    try:
        return await analysis_service.analyze(file.file, filename=file.filename or "uploaded-document.pdf")
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidModelOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
