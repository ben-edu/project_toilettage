"""Point d'entrée FastAPI — API de réservation toilettage canin à domicile."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import admin, public

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Endpoints publics et admin sous le préfixe /api/v1.
app.include_router(public.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)


# --- Health checks (utilisés par les probes K8s) ---
@app.get("/api/v1/healthz", tags=["health"])
def healthz():
    return {"status": "ok", "environment": settings.environment}


@app.get("/api/v1/readyz", tags=["health"])
def readyz():
    # Vérification légère : l'app répond. La vérif DB peut être ajoutée ici.
    return {"status": "ready"}
