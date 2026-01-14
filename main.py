from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import ai, auth, files, health, organizations, sermons, users

app = FastAPI(title=settings.app_name)

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