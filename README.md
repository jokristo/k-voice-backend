# K-Voice API (FastAPI)

Backend service for sermon capture, storage, transcription, and post-processing with FastAPI, SQLAlchemy, and Alembic.

## Features
- Organizations, users, sermons, and sermon outputs with UUID identifiers.
- JWT-based auth (access + refresh), role guards (`admin`, `editor`, `member`).
- Audio upload with local storage backend and simple MIME validation.
- Upload taille max configurable (`max_upload_size_mb`, défaut 50 MB) et tentative de calcul de durée via `ffprobe` si disponible.
- Background tasks for transcription and NLP post-processing (stubs ready for Whisper/model integration).
- SQLite by default (configurable via `DATABASE_URL`/`database_url`).
- Alembic migrations aligned with the data model.

## Quickstart
1) Install dependencies (ideally in a virtualenv):
```bash
pip install -r requirements.txt
```
2) Configure env vars (optional). Example `.env`:
```
database_url=sqlite:///./kvoice.db
secret_key=change-me
access_token_expire_minutes=30
refresh_token_expire_minutes=10080
storage_local_path=storage
cors_origins=["http://localhost:3000"]
```
3) Run migrations:
```bash
alembic upgrade head
```
4) Start the API:
```bash
uvicorn app.main:app --reload
```

## Key Endpoints
- `GET /health`
- Auth: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`
- Organizations: `GET/POST/PATCH/DELETE /organizations`
- Users: `GET /users`, `POST /users`, `GET/PATCH/DELETE /users/{id}`
- Sermons:
  - `POST /sermons`
  - `POST /sermons/{id}/upload` (multipart audio)
  - `POST /sermons/{id}/transcribe` (background)
  - `GET /sermons`, `GET /sermons/{id}`, `PATCH /sermons/{id}`
- AI:
  - `POST /ai/transcribe` (upload or `sermonId`)
  - `POST /ai/process/{sermonId}` (background post-processing)
- Files: `GET /files/{path}`

## Example cURL
Assuming an `Authorization: Bearer $TOKEN` header (from `/auth/login`).

Create sermon metadata:
```bash
curl -X POST http://localhost:8000/sermons \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Sunday Sermon","speaker":"Pr. John","date":"2024-01-07","organization_id":"<org-id>","recorded_by_id":"<user-id>"}'
```

Upload audio:
```bash
curl -X POST http://localhost:8000/sermons/<sermon-id>/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./sample.webm"
```

Start transcription:
```bash
curl -X POST http://localhost:8000/sermons/<sermon-id>/transcribe \
  -H "Authorization: Bearer $TOKEN"
```

Process transcript into summary/key points:
```bash
curl -X POST http://localhost:8000/ai/process/<sermon-id> \
  -H "Authorization: Bearer $TOKEN"
```

Fetch sermon with output:
```bash
curl http://localhost:8000/sermons/<sermon-id> -H "Authorization: Bearer $TOKEN"
```

## Notes
- Transcription and NLP are stubbed for local Whisper/LLM integration—replace implementations in `app/services/ai_service.py` and `app/services/nlp_service.py`.
- Storage is local by default (`storage/`); swap out `StorageService` for S3-like behavior as needed.
- CORS defaults to `http://localhost:3000` to align with a Next.js front-end.
# k-voice-backend
