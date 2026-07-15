# Toilettage Canin à Domicile — Orléans

Site de réservation pour un service de toilettage canin à domicile (Orléans + 10 km
autour de la Place du Martroi). Le toiletteur se déplace chez le client.

- **Phase 1** : réservation de créneaux (sans paiement).
- **Phase 2** : paiement en ligne.

Voir `CLAUDE.md` (conventions), `PROJECT_TOILETTAGE.md` (périmètre) et
`INFRA_PATTERNS.md` (patterns réels du cluster).

## Architecture (hybride)

```text
Navigateur ──HTTPS──> Frontend (Hestia/BM1)
Navigateur ──HTTPS──> api.toilettage.proxbenovh.cloud
                         └─> HAProxy → OPNsense → Traefik (BM2)
                               └─> Service → Pod FastAPI
                                     ├─ PostgreSQL (namespace toilettage)
                                     └─ Keycloak (realm dédié, admin only)
```

- **Frontend** : site statique FR sur Hestia (déployé via Jenkins/rsync).
- **API** : FastAPI sur K3s, namespace `toilettage`.
- **DB** : PostgreSQL dédié (StatefulSet) dans le même namespace.
- **Auth admin** : Keycloak (realm `toilettage`). Réservation publique = sans login.

## Structure

```text
api/                    # FastAPI (déployé sur K3s)
  app/
    core/               # config, database, auth Keycloak
    models/             # SQLAlchemy (services, réservations, horaires…)
    schemas/            # Pydantic
    services/           # géocodage, planification, email
    routers/            # public/ + admin/
    main.py             # entrée FastAPI
    seed.py             # données de base
  tests/                # pytest
  Dockerfile
  requirements.txt
kubernetes/toilettage/  # namespace, postgres, configmap, secret.example, deploy, svc, ingress
frontend/               # site public (placeholder — design en phase suivante)
Jenkinsfile             # pipeline multibranch
```

## Développement local (API)

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # remplir POSTGRES_* (jamais committé)
# Postgres local rapide :
#   docker run -d --name pg -e POSTGRES_USER=toilettage \
#     -e POSTGRES_PASSWORD=change-me-locally -e POSTGRES_DB=toilettage \
#     -p 5432:5432 postgres:16-alpine
python -m app.seed          # crée tables + prestations par défaut
uvicorn app.main:app --reload
# Docs : http://localhost:8000/api/docs
```

Tests :

```bash
cd api && PYTHONPATH=. pytest -q
```

## Points d'API (Phase 1)

Public (`/api/v1`) :
- `GET  /services` — prestations actives
- `POST /geocode/check?address=...` — vérifie la zone
- `POST /availability` — créneaux disponibles (service + taille + fenêtre)
- `POST /bookings` — crée une réservation (vérifie zone + créneau, envoie emails)

Admin (`/api/v1/admin`, protégé Keycloak) :
- `GET/PATCH /bookings` — voir/mettre à jour les réservations
- `GET/POST/PATCH /services` — gérer les prestations
- `GET/PUT /working-hours` — gérer les horaires

## Flux de branches

`feature/*` → `dev` (staging) → validation → merge `main` (prod).
Jenkins déploie automatiquement `dev` et `main`.

## Règles de sécurité

- Jamais de secrets dans Git (`.env`, Secrets K8s réels). Utiliser `*.example`.
- rsync Hestia toujours avec `--exclude='.env'`.
- Trafic navigateur → API toujours via domaine public → Traefik.
