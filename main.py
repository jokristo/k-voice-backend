import logging
import time

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routers import ai, auth, files, health, organizations, sermons, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
# Réduire le bruit des libs HTTP si besoin
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(title=settings.app_name)
logger = logging.getLogger("kvoice")


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
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(sermons.router, prefix="/sermons", tags=["sermons"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
app.include_router(files.router, tags=["files"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Sermon Management API"}