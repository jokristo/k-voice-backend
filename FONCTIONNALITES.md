# K-Voice — Documentation des fonctionnalités

## Vue d'ensemble

**K-Voice** est une API REST backend destinée à la gestion de sermons audio pour des organisations (églises, communautés). Elle permet de :

- Enregistrer et organiser des sermons
- Uploader des fichiers audio
- Transcrire automatiquement l'audio en texte
- Générer un résumé et des métadonnées à partir de la transcription
- Gérer des utilisateurs et des organisations avec des rôles différenciés

**Stack technique :** FastAPI, SQLAlchemy, SQLite (par défaut), JWT, stockage local des fichiers, intégration IA (Gemini, OpenAI Whisper, ou faster-whisper local).

---

## Architecture

```
Client (frontend)
    ↓
API FastAPI (K-Voice)
    ├── Authentification JWT
    ├── Gestion organisations / utilisateurs
    ├── Gestion sermons + upload audio
    ├── Transcription IA (3 fournisseurs)
    ├── Traitement NLP (résumé, points clés…)
    └── Stockage local + service de fichiers
    ↓
Base de données SQLite (configurable)
```

---

## Authentification & sécurité

### Endpoints (`/auth`)

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/auth/register` | Inscription d'un nouvel utilisateur |
| `POST` | `/auth/login` | Connexion (email + mot de passe) |
| `POST` | `/auth/refresh` | Renouvellement des tokens JWT |

### Fonctionnalités

- **Hash des mots de passe** avec bcrypt
- **Tokens JWT** : access token (30 min par défaut) + refresh token (7 jours)
- **OAuth2 Bearer** pour protéger les routes
- **CORS** configurable (origine par défaut : `http://localhost:3000`)
- **Journalisation HTTP** de toutes les requêtes (méthode, chemin, statut, durée)

---

## Rôles & permissions

| Rôle | Description |
|------|-------------|
| `admin` | Accès global : toutes les organisations, CRUD utilisateurs/organisations |
| `editor` | Peut créer/modifier des sermons, uploader de l'audio, lancer transcription et traitement NLP |
| `member` | Lecture seule (sermons et utilisateurs de son organisation) |

### Règles d'accès

- Les **non-admins** ne voient que les ressources de **leur organisation**
- La création/modification de sermons requiert le rôle `admin` ou `editor`
- La suppression d'utilisateurs est réservée aux `admin`
- Un utilisateur peut modifier son propre profil sans être admin

---

## Organisations

### Endpoints (`/organizations`)

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| `GET` | `/organizations` | Authentifié | Liste toutes les organisations |
| `POST` | `/organizations` | Admin | Crée une organisation |
| `GET` | `/organizations/{org_id}` | Authentifié | Détail d'une organisation |
| `PATCH` | `/organizations/{org_id}` | Admin | Met à jour une organisation |
| `DELETE` | `/organizations/{org_id}` | Admin | Supprime une organisation |

### Données gérées

- Nom, slug (unique), adresse, téléphone, email, logo
- Horodatage `created_at` / `updated_at`
- Relation avec utilisateurs et sermons (suppression en cascade)

---

## Utilisateurs

### Endpoints (`/users`)

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| `GET` | `/users` | Authentifié | Liste les utilisateurs (filtrable par `org_id`) |
| `POST` | `/users` | Admin | Crée un utilisateur |
| `GET` | `/users/{user_id}` | Authentifié | Détail d'un utilisateur |
| `PATCH` | `/users/{user_id}` | Soi-même ou admin | Met à jour un utilisateur |
| `DELETE` | `/users/{user_id}` | Admin | Supprime un utilisateur |

### Données gérées

- Email (unique), nom, rôle, avatar, organisation
- Mot de passe (hashé, jamais exposé en réponse)

---

## Sermons

Cœur métier de l'application.

### Endpoints (`/sermons`)

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| `GET` | `/sermons` | Authentifié | Liste les sermons (filtres disponibles) |
| `POST` | `/sermons` | Admin/Editor | Crée un sermon |
| `GET` | `/sermons/{sermon_id}` | Authentifié | Détail d'un sermon |
| `PATCH` | `/sermons/{sermon_id}` | Admin/Editor | Met à jour un sermon |
| `POST` | `/sermons/{sermon_id}/upload` | Admin/Editor | Upload du fichier audio |
| `POST` | `/sermons/{sermon_id}/transcribe` | Admin/Editor | Lance la transcription (tâche de fond) |

### Filtres de liste (`GET /sermons`)

- `org_id` — organisation (admin uniquement pour filtrer librement)
- `status` — statut du sermon
- `speaker` — recherche partielle sur le prédicateur
- `date` — date exacte du sermon

### Données d'un sermon

- Titre, prédicateur (`speaker`), date, description
- Métadonnées audio : URL, taille, durée, format
- Statut de traitement
- Organisation et utilisateur enregistreur
- Horodatages : création, mise à jour, transcription, traitement NLP
- **Output** associé (transcription + analyse)

### Statuts d'un sermon

| Statut | Signification |
|--------|---------------|
| `pending` | Créé, en attente d'audio ou de traitement |
| `transcribing` | Transcription en cours |
| `processing` | Transcription terminée, traitement NLP en cours ou prêt |
| `completed` | Traitement NLP terminé |
| `failed` | Erreur lors de la transcription ou du traitement |

### Upload audio (`POST /sermons/{id}/upload`)

- Formats acceptés : WebM, OGG, MP3, WAV, MP4, FLAC, AAC, M4A, Opus
- Détection MIME par content-type ou extension de fichier
- Taille max configurable (défaut : **50 Mo**)
- Calcul automatique de la **durée** via `ffprobe` (si disponible)
- Stockage par organisation (`storage/{organization_id}/`)

---

## Intelligence artificielle

### Transcription (`/ai`)

| Méthode | Route | Accès | Description |
|---------|-------|-------|-------------|
| `POST` | `/ai/transcribe` | Authentifié | Transcription synchrone (fichier ou sermon existant) |
| `POST` | `/ai/process/{sermon_id}` | Admin/Editor | Traitement NLP en arrière-plan |

### Fournisseurs de transcription (configurable)

| Fournisseur | Variable | Description |
|-------------|----------|-------------|
| **Gemini** (défaut) | `TRANSCRIPTION_PROVIDER=gemini` | Upload audio vers Google Gemini + prompt de transcription |
| **OpenAI** | `TRANSCRIPTION_PROVIDER=openai` | API Whisper (`whisper-1`) |
| **Local** | `TRANSCRIPTION_PROVIDER=local` | faster-whisper sur la machine (CPU/CUDA) |

### Résultat de transcription

- Texte complet (`transcript`)
- Liste de mots avec index (`transcript_words`)
- Nombre de mots (`word_count`)
- Temps de traitement (`processing_time`)
- Modèle IA utilisé (`ai_model`)

### Traitement NLP (`POST /ai/process/{sermon_id}`)

Analyse la transcription et produit :

- **Résumé** (`summary`)
- **Points clés** (`key_points`)
- **Thèmes principaux** (`main_themes`)
- **Versets clés** (`key_verses`)
- **Références** (`references`)
- Temps de lecture estimé (`estimated_read_time`, basé sur 180 mots/min)

> **Note :** Le traitement NLP actuel est une implémentation simplifiée (découpage par phrases). Une intégration LLM plus avancée est prévue.

---

## Fichiers & stockage

### Endpoints

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/files/{path}` | Sert un fichier stocké localement |

### Fonctionnalités

- Stockage local dans le dossier `storage/` (configurable)
- Noms de fichiers uniques (UUID + nom original)
- URLs publiques de type `/files/{chemin_relatif}`
- Upload asynchrone par chunks (aiofiles)

---

## Santé de l'API

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/health` | Vérification que l'API est opérationnelle (`{"status": "ok"}`) |

---

## Workflow typique

```
1. Créer une organisation          POST /organizations
2. Créer un utilisateur            POST /users ou POST /auth/register
3. Se connecter                    POST /auth/login
4. Créer un sermon                 POST /sermons
5. Uploader l'audio                POST /sermons/{id}/upload
6. Lancer la transcription         POST /sermons/{id}/transcribe
   → statut: transcribing → processing
7. Lancer le traitement NLP        POST /ai/process/{id}
   → statut: processing → completed
8. Consulter le résultat           GET /sermons/{id}
   (transcript, résumé, points clés…)
```

---

## Configuration (variables d'environnement)

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DATABASE_URL` | `sqlite:///./kvoice.db` | URL de la base de données |
| `SECRET_KEY` | — | Clé secrète JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Durée du access token |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | `10080` (7 j) | Durée du refresh token |
| `CORS_ORIGINS` | `http://localhost:3000` | Origines CORS autorisées |
| `STORAGE_LOCAL_PATH` | `storage` | Dossier de stockage |
| `MAX_UPLOAD_SIZE_MB` | `50` | Taille max des uploads |
| `TRANSCRIPTION_PROVIDER` | `gemini` | `gemini`, `openai` ou `local` |
| `DEFAULT_AI_MODEL` | `gemini-2.0-flash` | Modèle Gemini |
| `GEMINI_API_KEY` | — | Clé API Google Gemini |
| `OPENAI_API_KEY` | — | Clé API OpenAI |
| `OPENAI_TRANSCRIPTION_MODEL` | `whisper-1` | Modèle Whisper OpenAI |
| `LOCAL_WHISPER_MODEL_SIZE` | `base` | Taille du modèle faster-whisper |
| `LOCAL_WHISPER_DEVICE` | `auto` | `auto`, `cpu` ou `cuda` |
| `LOCAL_WHISPER_LANGUAGE` | — | Code langue ISO (ex. `fr`) |

---

## Modèle de données

```
Organization
├── User (1:N)
└── Sermon (1:N)
    └── SermonOutput (1:1)
        ├── transcript, transcript_words
        ├── summary, key_points
        ├── main_themes, key_verses, references
        └── word_count, estimated_read_time, ai_model
```

---

## Dépendances principales

- **fastapi** + **uvicorn** — API HTTP
- **sqlalchemy** + **alembic** — ORM et migrations
- **python-jose** + **passlib** — JWT et hash de mots de passe
- **google-generativeai** — Transcription Gemini
- **openai** — Transcription Whisper
- **faster-whisper** — Transcription locale
- **aiofiles** — Upload asynchrone
