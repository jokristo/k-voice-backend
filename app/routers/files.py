from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services import storage_service

router = APIRouter()


@router.get("/files/{path:path}")
def serve_file(path: str):
    file_path = storage_service.get_file_path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
