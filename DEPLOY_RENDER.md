# Déploiement sur Render — K-Voice

Deux services Render : **API** (`k-voice-backend`, Docker + **PostgreSQL**) et **frontend** (`ecclesiato`, Node).

---

## 1. API backend (Docker + PostgreSQL)

### Architecture prod

| Composant | Render | Rôle |
|-----------|--------|------|
| **PostgreSQL** | Base `kvoice-db` | Utilisateurs, orgs, sermons, transcriptions |
| **Disque `/data`** | 10 Go monté sur le web service | Fichiers audio (`STORAGE_LOCAL_PATH=/data/storage`) |
| **Web service** | Docker `kvoice-api` | FastAPI + ffmpeg + migrations Alembic |

La base **n’est plus** sur le disque local : seuls les fichiers audio utilisent `/data`.

### Fichiers fournis

| Fichier | Rôle |
|---------|------|
| `Dockerfile` | Python 3.11 + ffmpeg + `psycopg2-binary` |
| `scripts/render_start.sh` | `alembic upgrade head` + uvicorn |
| `render.yaml` | Blueprint : PostgreSQL + API + disque storage |
| `requirements.txt` | `psycopg2-binary` pour PostgreSQL |

### Option A — Blueprint (recommandé)

1. Repo Git → Render → **New Blueprint**.
2. Root directory : `k-voice-backend` (si monorepo).
3. Render crée automatiquement :
   - la base **kvoice-db**
   - le service **kvoice-api** avec `DATABASE_URL` liée à la base
4. Renseigner les secrets (`sync: false`) :
   - `OPENAI_API_KEY`
   - `CORS_ORIGINS` → `https://votre-frontend.onrender.com`
   - `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` (si `RUN_BOOTSTRAP=true`)
5. Premier deploy → vérifier les logs : migrations + bootstrap super-admin.
6. Mettre **`RUN_BOOTSTRAP=false`** après création du compte.

### Option B — Configuration manuelle

1. **New → PostgreSQL** → noter l’**Internal Database URL**.
2. **New → Web Service** → Docker, Dockerfile `./Dockerfile`.
3. **Environment** :
   ```env
   DATABASE_URL=<Internal Database URL depuis Render>
   STORAGE_LOCAL_PATH=/data/storage
   SECRET_KEY=<généré>
   OPENAI_API_KEY=...
   TRANSCRIPTION_PROVIDER=openai
   NLP_PROVIDER=openai
   CORS_ORIGINS=https://votre-frontend.onrender.com
   RUN_BOOTSTRAP=true
   SUPER_ADMIN_EMAIL=...
   SUPER_ADMIN_PASSWORD=...
   ```
4. **Disque** : ajouter un disk mount `/data` (fichiers audio).
5. **Health check** : `/health`

Render injecte souvent une URL `postgres://…` : l’API la convertit automatiquement en `postgresql://…`.

### Variables importantes

```env
DATABASE_URL=postgresql://...   # fourni par Render (base liée)
STORAGE_LOCAL_PATH=/data/storage
SECRET_KEY=<généré>
OPENAI_API_KEY=...
TRANSCRIPTION_PROVIDER=openai
NLP_PROVIDER=openai
CORS_ORIGINS=https://votre-frontend.onrender.com
```

### Super-admin

Voir **`SUPER_ADMIN_RENDER.md`**.

### Vérification

```bash
curl https://kvoice-api.onrender.com/health
# {"status":"ok","ffmpeg":true}
```

---

## 2. Frontend Next.js (`ecclesiato`)

- **Runtime** : Node 20
- **Root Directory** : `ecclesiato`
- **Build** : `npm ci && npm run build:render`
- **Start** : `npm run start:render`

```env
NEXT_PUBLIC_API_URL=https://kvoice-api.onrender.com
NEXTAUTH_URL=https://ecclesiato.onrender.com
NEXTAUTH_SECRET=<généré>
```

---

## 3. Ordre de déploiement

1. Déployer l’**API** (PostgreSQL + Docker) → noter l’URL.
2. `CORS_ORIGINS` = URL du frontend.
3. Déployer le **frontend** avec `NEXT_PUBLIC_API_URL`.
4. Connexion super-admin → `/admin`.

---

## 4. Développement local (SQLite)

Par défaut en local :

```env
database_url=sqlite:///./kvoice.db
storage_local_path=storage
```

Pour tester PostgreSQL en local (Docker) :

```bash
docker run -d --name kvoice-pg -e POSTGRES_PASSWORD=kvoice -e POSTGRES_DB=kvoice -p 5432:5432 postgres:16
```

```env
DATABASE_URL=postgresql://postgres:kvoice@localhost:5432/kvoice
```

Puis :

```bash
alembic upgrade head
python scripts/bootstrap_super_admin.py
```

---

## 5. Limitations Render

- **Disque** : obligatoire pour les fichiers audio (pas pour PostgreSQL).
- **Timeouts HTTP** : transcriptions longues ; le traitement continue en arrière-plan si l’instance reste active.
- **faster-whisper** : garder `TRANSCRIPTION_PROVIDER=openai` en prod.
- **Secrets** : uniquement via le dashboard Render, jamais dans Git.

---

## 6. Dépannage PostgreSQL

| Problème | Solution |
|----------|----------|
| `No module named 'psycopg2'` | Redéployer après mise à jour `requirements.txt` (rebuild Docker) |
| Erreur enum `super_admin` | `alembic upgrade head` (migration `0003` ajoute la valeur sur PostgreSQL) |
| Connexion refusée | Utiliser l’**Internal** Database URL sur le service API (même région) |
| `postgres://` vs `postgresql://` | Géré automatiquement dans `app/core/config.py` |
