# Créer un super-admin sur Render (K-Voice API)

Ce guide concerne le service **backend** (`k-voice-backend`) déployé sur Render. Le super-admin se connecte ensuite sur le **frontend** (`ecclesiato`) avec le même email / mot de passe.

---

## Prérequis

1. L’API est déployée sur Render (Docker) et répond sur `/health` :
   ```bash
   curl https://VOTRE-API.onrender.com/health
   # {"status":"ok","ffmpeg":true}
   ```
2. Les **migrations** ont tourné au démarrage (`alembic upgrade head` via `scripts/render_start.sh`).
3. **PostgreSQL** : la base Render `kvoice-db` est liée via `DATABASE_URL` (voir `POSTGRES_PROD.md`).
4. Un **disque persistant** sur `/data` sert aux **fichiers audio** (`STORAGE_LOCAL_PATH=/data/storage`), pas à PostgreSQL.

---

## Méthode 1 — Bootstrap automatique (recommandé au 1er déploiement)

Au démarrage du conteneur, si `RUN_BOOTSTRAP=true`, le script `scripts/render_start.sh` exécute `scripts/bootstrap_super_admin.py`.

### Variables dans le dashboard Render (service API → Environment)

| Variable | Exemple | Obligatoire |
|----------|---------|-------------|
| `RUN_BOOTSTRAP` | `true` (puis `false` après succès) | Oui pour la 1ère fois |
| `SUPER_ADMIN_EMAIL` | `vous@example.com` | Oui |
| `SUPER_ADMIN_PASSWORD` | mot de passe fort (12+ caractères) | Oui |
| `SUPER_ADMIN_NAME` | `Super Admin` | Non |

### Étapes

1. Render → service **kvoice-api** → **Environment**.
2. Ajouter / modifier les variables ci-dessus.
3. **Save** puis **Manual Deploy** (ou attendre le redeploy auto).
4. Ouvrir **Logs** et vérifier une ligne du type :
   ```text
   Bootstrapping super_admin...
   Created super_admin: vous@example.com
   ```
   ou `Upgraded user to super_admin: ...`
5. **Important** : repasser `RUN_BOOTSTRAP` à `false` et redéployer une fois le compte créé. Sinon, à chaque redeploy le mot de passe peut être réécrit si `SUPER_ADMIN_PASSWORD` est toujours défini.

### Connexion frontend

1. URL frontend : `https://VOTRE-FRONT.onrender.com/login`
2. Email / mot de passe = `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD`
3. Accès admin : `https://VOTRE-FRONT.onrender.com/admin` (rôle `super_admin` uniquement)

Variables frontend à aligner :

```env
NEXT_PUBLIC_API_URL=https://VOTRE-API.onrender.com
NEXTAUTH_URL=https://VOTRE-FRONT.onrender.com
NEXTAUTH_SECRET=<secret généré>
```

Sur l’API, `CORS_ORIGINS` doit inclure l’URL du frontend, par ex. :

```env
CORS_ORIGINS=https://VOTRE-FRONT.onrender.com
```

---

## Méthode 2 — Shell Render (compte perdu ou bootstrap désactivé)

Quand `RUN_BOOTSTRAP=false` ou vous devez recréer / promouvoir un utilisateur sans redeploy bootstrap.

### Étapes

1. Render → service API → onglet **Shell** (plan payant ; sur le plan gratuit, utiliser la méthode 1 avec `RUN_BOOTSTRAP=true` temporairement).
2. Dans le shell du conteneur :

   ```bash
   cd /app
   export SUPER_ADMIN_EMAIL="vous@example.com"
   export SUPER_ADMIN_PASSWORD="VotreMotDePasseSecurise"
   export SUPER_ADMIN_NAME="Super Admin"
   python scripts/bootstrap_super_admin.py
   ```

3. Sortie attendue :
   - `Created organization: K-Voice Platform (...)` ou `Organization exists: ...`
   - `Created super_admin: ...` ou `Upgraded user to super_admin: ...`

4. Se connecter sur le frontend avec ces identifiants.

### Comportement du script

- Crée l’organisation plateforme `kvoice-platform` si elle n’existe pas.
- Si l’email existe déjà : passe le rôle à `super_admin` et met à jour le mot de passe si `SUPER_ADMIN_PASSWORD` est défini.
- Si l’email n’existe pas : crée l’utilisateur `super_admin`.

Fichier source : `scripts/bootstrap_super_admin.py`.

---

## Méthode 3 — Localement contre la base Render (avancé)

Uniquement si vous exposez temporairement `DATABASE_URL` (PostgreSQL Render) ou copiez la base SQLite — déconseillé en prod. Préférer les méthodes 1 ou 2.

---

## Vérifications après création

| Test | Commande / action |
|------|-------------------|
| API vivante | `curl https://VOTRE-API.onrender.com/health` |
| Login API | `POST https://VOTRE-API.onrender.com/auth/login` avec email / password (JSON) → `access_token` |
| Login UI | Page `/login` du frontend |
| Rôle admin | Menu **Admin** visible ; URL `/admin` accessible |

Exemple login API :

```bash
curl -s -X POST "https://VOTRE-API.onrender.com/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"vous@example.com","password":"VotreMotDePasse"}'
```

---

## Sécurité

- Ne jamais committer `SUPER_ADMIN_PASSWORD` dans Git.
- Utiliser les **secrets** Render (Environment → Secret).
- Désactiver `RUN_BOOTSTRAP` après la première création.
- Changer le mot de passe par défaut (`admin`) avant toute mise en production.
- En production : **PostgreSQL** Render (config par défaut dans `render.yaml`) — voir `POSTGRES_PROD.md`.

---

## Dépannage

| Problème | Cause probable | Action |
|----------|----------------|--------|
| Login « identifiants incorrects » | Mauvais email/mot de passe ou bootstrap non exécuté | Vérifier les logs ; relancer bootstrap (méthode 1 ou 2) |
| Pas de menu Admin | Compte pas `super_admin` | Relancer `bootstrap_super_admin.py` avec le bon email |
| Base vide après redeploy | `DATABASE_URL` non liée à PostgreSQL | Lier la base Render (Internal URL) ; vérifier `alembic upgrade head` dans les logs |
| Audio perdus après redeploy | Pas de disque `/data` | Disk mount `/data` + `STORAGE_LOCAL_PATH=/data/storage` |
| CORS / erreur réseau frontend | `CORS_ORIGINS` incorrect | Mettre l’URL exacte du frontend (https, sans slash final) |
| Bootstrap à chaque deploy | `RUN_BOOTSTRAP=true` en permanence | Passer à `false` après création du compte |

---

## Références

- PostgreSQL prod : `POSTGRES_PROD.md`
- Déploiement complet API + frontend : `DEPLOY_RENDER.md`
- Dockerfile : `Dockerfile` + `scripts/render_start.sh`
- Blueprint Render : `render.yaml`
