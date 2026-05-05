import logging
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

import aiofiles
from fastapi import UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, base_path: str = settings.storage_local_path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile, subdir: Optional[str] = None) -> Tuple[str, int]:
        target_dir = self.base_path / subdir if subdir else self.base_path
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4()}_{upload.filename}"
        destination = target_dir / filename

        async with aiofiles.open(destination, "wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                await f.write(chunk)

        size = destination.stat().st_size
        relative_path = destination.relative_to(self.base_path)
        rel = relative_path.as_posix()
        logger.info(
            "storage save_upload subdir=%r relative=%s size_bytes=%s",
            subdir,
            rel,
            size,
        )
        return rel, size

    def get_file_path(self, relative_path: str) -> Path:
        return self.base_path / Path(relative_path)

    def get_public_url(self, relative_path: str) -> str:
        return f"/files/{relative_path}"


storage_service = StorageService()
