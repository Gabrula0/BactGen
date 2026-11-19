import logging
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import register_exception_handlers
from app.middleware import RequestLoggingMiddleware
from app.routers import analyses, samples

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="BactGen Clinical Genomics API",
    version="1.0.0",
)

app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)
app.include_router(samples.router)
app.include_router(analyses.router)


@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "BactGenDB"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL no responde",
        )
