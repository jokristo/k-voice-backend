# PostgreSQL en production (Render)

Guide rapide si vous déployez avec **PostgreSQL** (configuration par défaut du `render.yaml` actuel).

---

## Ce qui change par rapport à SQLite

| | SQLite (dev) | PostgreSQL (prod) |
|---|--------------|-------------------|
| Données métier | Fichier `kvoice.db` | Base Render `kvoice-db` |
| Fichiers audio | Dossier `storage/` ou `/data/storage` | Toujours sur le **disque** `/data` du web service |
| Driver Python | inclus | `psycopg2-binary` dans `requirements.txt` |
| Migrations | `alembic upgrade head` au démarrage | idem |

---

## Étapes Render

### 1. Créer la base

Via **Blueprint** : `render.yaml` crée `kvoice-db` automatiquement.

**Manuel** : Dashboard → **New +** → **PostgreSQL** → nom `kvoice-db`.

### 2. Lier l’API

Sur le service **kvoice-api** → **Environment** :

- **`DATABASE_URL`** = **Internal Database URL** (onglet de la base PostgreSQL)
- Ne pas utiliser l’URL « External » sauf debug depuis votre machine

Le blueprint fait déjà :

```yaml
DATABASE_URL:
  fromDatabase:
    name: kvoice-db
    property: connectionString
```

### 3. Disque pour l’audio

Toujours ajouter un **Disk** sur le web service :

- Mount path : `/data`
- Variable : `STORAGE_LOCAL_PATH=/data/storage`

Sans disque, les uploads audio disparaissent au redeploy (la base PostgreSQL, elle, reste).

### 4. Premier déploiement

Variables obligatoires :

```env
OPENAI_API_KEY=...
CORS_ORIGINS=https://VOTRE-FRONT.onrender.com
RUN_BOOTSTRAP=true
SUPER_ADMIN_EMAIL=vous@example.com
SUPER_ADMIN_PASSWORD=<mot de passe fort>
```

Logs attendus :

```text
Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade ...
Bootstrapping super_admin...
Created super_admin: ...
Starting uvicorn on 0.0.0.0:8000
```

Puis **`RUN_BOOTSTRAP=false`** et redeploy.

### 5. Super-admin

Détails : **`SUPER_ADMIN_RENDER.md`**.

---

## Vérifier que PostgreSQL est bien utilisé

1. Logs au démarrage : pas d’erreur Alembic / psycopg2.
2. Dashboard Render → base **kvoice-db** → onglet **Data** (tables après migrations).
3. Login frontend avec le compte bootstrap.

---

## Migration depuis SQLite (existant)

Si vous aviez déjà des données en SQLite sur Render :

1. Exporter les données (script custom ou dump manuel des tables).
2. Créer PostgreSQL, configurer `DATABASE_URL`.
3. `alembic upgrade head` sur une base vide.
4. Importer les données ou repartir à zéro + `RUN_BOOTSTRAP=true`.

Pour un **nouveau** déploiement, inutile : PostgreSQL part vide, bootstrap crée le super-admin.

---

## Local : tester comme en prod

```bash
cd k-voice-backend
pip install -r requirements.txt

export DATABASE_URL=postgresql://postgres:kvoice@localhost:5432/kvoice
alembic upgrade head
export SUPER_ADMIN_EMAIL=admin@test.com SUPER_ADMIN_PASSWORD=admin
python scripts/bootstrap_super_admin.py
uvicorn main:app --reload
```

---

## Références techniques

- Normalisation URL : `app/core/config.py` (`postgres://` → `postgresql://`)
- Pool connexions : `app/core/database.py`
- Enum `super_admin` PostgreSQL : migration `0003_super_admin_role.py`
- Déploiement complet : `DEPLOY_RENDER.md`
