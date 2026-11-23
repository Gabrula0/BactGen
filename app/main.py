import logging
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

app = FastAPI(title="BactGen Clinical Genomics API", version="1.0.0")

app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)
app.include_router(samples.router)
app.include_router(analyses.router)

STATIC_DIR = Path(__file__).parent / "static"
NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


@app.get("/", include_in_schema=False)
def serve_spa():
    return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE)


@app.get("/static/app.js", include_in_schema=False)
def serve_js():
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript", headers=NO_CACHE)


@app.get("/static/styles.css", include_in_schema=False)
def serve_css():
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css", headers=NO_CACHE)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "BactGenDB"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL is not responding",
        )
