"""Structured error handling middleware and error response models."""
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --- Error Codes ---

class ErrorCode:
    """Standard error codes returned by the API."""
    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    DECISION_NOT_FOUND = "DECISION_NOT_FOUND"
    PARAGRAPH_NOT_FOUND = "PARAGRAPH_NOT_FOUND"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    COURSE_NOT_PUBLISHABLE = "COURSE_NOT_PUBLISHABLE"
    COURSE_NO_PARAGRAPHS = "COURSE_NO_PARAGRAPHS"

    # Agent errors (5xx)
    AGENT_LLM_UNAVAILABLE = "AGENT_LLM_UNAVAILABLE"
    AGENT_LLM_TIMEOUT = "AGENT_LLM_TIMEOUT"
    AGENT_PARSE_ERROR = "AGENT_PARSE_ERROR"
    AGENT_PROCESSING_FAILED = "AGENT_PROCESSING_FAILED"

    # Server errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


# --- Error Response Model ---

class ErrorDetail(BaseModel):
    """Structured error response body."""
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    """API error envelope."""
    error: ErrorDetail


# --- Custom Exceptions ---

class AppError(Exception):
    """Base application error with structured error code."""
    def __init__(self, code: str, message: str, status_code: int = 400, detail: str | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found."""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code=f"{resource.upper()}_NOT_FOUND",
            message=f"{resource} not found: {resource_id}",
            status_code=404,
        )


class AgentError(AppError):
    """Agent processing error."""
    def __init__(self, code: str, message: str, detail: str | None = None):
        super().__init__(code=code, message=message, status_code=503, detail=detail)


# --- Middleware Registration ---

def register_error_handlers(app: FastAPI):
    """Register global error handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning(f"AppError [{exc.code}]: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorDetail(code=exc.code, message=exc.message, detail=exc.detail)
            ).model_dump(),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        msg = str(exc)
        # Map known ValueError messages to error codes
        code = ErrorCode.VALIDATION_ERROR
        status = 400
        if "not found" in msg.lower():
            code = ErrorCode.COURSE_NOT_FOUND
            status = 404
        elif "no paragraphs" in msg.lower():
            code = ErrorCode.COURSE_NO_PARAGRAPHS
        elif "not yet approved" in msg.lower():
            code = ErrorCode.COURSE_NOT_PUBLISHABLE

        logger.warning(f"ValueError [{code}]: {msg}")
        return JSONResponse(
            status_code=status,
            content=ErrorResponse(
                error=ErrorDetail(code=code, message=msg)
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error: {exc}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="An internal server error occurred.",
                    detail=str(exc) if logger.isEnabledFor(logging.DEBUG) else None,
                )
            ).model_dump(),
        )
