# Déploiement sur Render — K-Voice

Deux services Render séparés : **API** (`k-voice-backend`) et **frontend** (`ecclesiato`).

## 1. API backend (Docker)

### Fichiers fournis

| Fichier | Rôle |
|---------|------|
| `Dockerfile` | Python 3.11 + **ffmpeg** + dépendances pip |
| `scripts/render_start.sh` | Migrations Alembic + démarrage uvicorn |
| `render.yaml` | Blueprint Render (disque persistant, variables) |
| `requirements.txt` | Paquets Python uniquement (pas ffmpeg) |

### Créer le service

**Option A — Blueprint**

1. Repo Git connecté à Render.
2. New → **Blueprint** → pointer le dossier `k-voice-backend` (ou repo racine si mono-repo).
3. Render lit `render.yaml`.
4. Renseigner les secrets marqués `sync: false` :
   - `OPENAI_API_KEY`
   - `CORS_ORIGINS` → URL du frontend, ex. `https://ecclesiato.onrender.com` ou JSON `["https://..."]`
   - `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` (si `RUN_BOOTSTRAP=true`)

**Option B — Web Service Docker manuel**

- **Root Directory** : `k-voice-backend` (si monorepo)
- **Environment** : Docker
- **Dockerfile path** : `./Dockerfile`
- **Health check** : `/health`
- **Disk** : monter `/data` (10 Go) — SQLite + fichiers audio

### Variables d'environnement importantes

```env
DATABASE_URL=sqlite:////data/kvoice.db
STORAGE_LOCAL_PATH=/data/storage
SECRET_KEY=<généré>
OPENAI_API_KEY=your-openai-api-key-here
TRANSCRIPTION_PROVIDER=openai
NLP_PROVIDER=openai
CORS_ORIGINS=https://votre-frontend.onrender.com
MAX_UPLOAD_SIZE_MB=100
AUDIO_COMPRESSION_ENABLED=true
```

Après le premier déploiement, mettre `RUN_BOOTSTRAP=false` pour ne pas réinitialiser le super-admin à chaque redeploy.

### PostgreSQL (recommandé en prod)

1. Créer une base **PostgreSQL** sur Render.
2. Remplacer `DATABASE_URL` par la connection string Render (`postgresql://...`).
3. Redéployer — `alembic upgrade head` s’exécute au démarrage.

### Vérification

```bash
curl https://kvoice-api.onrender.com/health
# {"status":"ok","ffmpeg":true}
```

---

## 2. Frontend Next.js (`ecclesiato`)

### Fichiers fournis

| Fichier | Rôle |
|---------|------|
| `render.yaml` | Build / start Node |
| `package.json` | Scripts `build:render` et `start:render` |

### Créer le service

- **Runtime** : Node 20
- **Root Directory** : `ecclesiato`
- **Build** : `npm ci && npm run build:render`
- **Start** : `npm run start:render`

### Variables

```env
NEXT_PUBLIC_API_URL=https://kvoice-api.onrender.com
NEXTAUTH_URL=https://ecclesiato.onrender.com
NEXTAUTH_SECRET=<généré>
```

Le frontend **ne utilise pas** `requirements.txt` — uniquement `package.json`.

---

## 3. Ordre de déploiement

1. Déployer l’**API** → noter l’URL.
2. Configurer `CORS_ORIGINS` sur l’API avec l’URL frontend (même avant deploy front si connue).
3. Déployer le **frontend** avec `NEXT_PUBLIC_API_URL` pointant vers l’API.
4. Se connecter avec le compte super_admin bootstrap.

---

## 4. Limitations Render

- **Disque** : sans disk mount, SQLite et `storage/` sont perdus à chaque redeploy.
- **Timeouts** : transcriptions longues peuvent dépasser le timeout HTTP ; le job background continue tant que l’instance reste vivante.
- **faster-whisper** : lourd sur CPU ; en prod garder `TRANSCRIPTION_PROVIDER=openai`.
- **Secrets** : ne jamais committer `.env` — utiliser le dashboard Render.

---

## 5. requirements.txt — rappel

Contient les libs **pip** seulement. Dépendances système installées dans le **Dockerfile** :

- `ffmpeg` / `ffprobe` (compression + durée audio)
