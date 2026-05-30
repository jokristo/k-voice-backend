import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import SessionLocal
from app.routers import ai, auth, billing, config_public, files, health, organizations, sermons, users
from app.services.audio_retention import purge_expired_audio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
# Réduire le bruit des libs HTTP si besoin
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("kvoice")


async def _audio_retention_loop():
    interval = max(60, settings.audio_retention_sweep_interval_s)
    while True:
        await asyncio.sleep(interval)
        if not settings.audio_retention_enabled:
            continue
        db = SessionLocal()
        try:
            purge_expired_audio(db)
        except Exception:
            logger.exception("audio retention sweep failed")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    purge_task = None
    if settings.audio_retention_enabled:
        db = SessionLocal()
        try:
            n = purge_expired_audio(db)
            if n:
                logger.info("audio retention startup purged=%s", n)
        finally:
            db.close()
        purge_task = asyncio.create_task(_audio_retention_loop())
    yield
    if purge_task:
        purge_task.cancel()
        try:
            await purge_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    start = time.perf_counter()
    method, path = request.method, request.url.path
    logger.info("--> %s %s", method, path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("!! exception in %s %s", method, path)
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    if response.status_code >= 400:
        logger.warning("<-- %s %s status=%s in %.0fms", method, path, response.status_code, elapsed_ms)
    else:
        logger.info("<-- %s %s status=%s in %.0fms", method, path, response.status_code, elapsed_ms)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "422 validation %s %s errors=%s",
        request.method,
        request.url.path,
        jsonable_encoder(exc.errors()),
    )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health.router, tags=["health"])
app.include_router(config_public.router, prefix="/config", tags=["config"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(sermons.router, prefix="/sermons", tags=["sermons"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
app.include_router(files.router, tags=["files"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Sermon Management API"}