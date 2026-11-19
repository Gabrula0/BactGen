import logging
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger("bactgen.errors")


def _get_req_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": f"HTTP_{exc.status_code}",
                "detail": str(exc.detail),
                "request_id": _get_req_id(request),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "VALIDATION_ERROR",
                "detail": "; ".join(errors),
                "request_id": _get_req_id(request),
            },
        )

    @app.exception_handler(IntegrityError)
    async def db_integrity_handler(request: Request, exc: IntegrityError):
        logger.warning("DB integrity conflict request_id=%s: %s", _get_req_id(request), exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error_code": "RESOURCE_CONFLICT",
                "detail": "The resource already exists or violates a unique constraint.",
                "request_id": _get_req_id(request),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def db_general_handler(request: Request, exc: SQLAlchemyError):
        logger.error("DB error request_id=%s", _get_req_id(request), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_code": "DATABASE_UNAVAILABLE",
                "detail": "Error connecting to the database. Please try again later.",
                "request_id": _get_req_id(request),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error request_id=%s", _get_req_id(request))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "detail": "Internal server error. Please try again later.",
                "request_id": _get_req_id(request),
            },
        )
