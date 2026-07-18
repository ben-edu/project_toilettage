"""Initialisation des tables et données de base.

Usage : python -m app.seed
Crée les tables (dev/staging ; en prod préférer Alembic) et insère :
- les coefficients de taille par défaut ;
- les prestations initiales (non définitives) ;
- des heures de travail par défaut (lun-ven 9h-18h).

Idempotent : ne recrée pas ce qui existe déjà.
"""

from datetime import time
import logging

from sqlalchemy import select, text

from app.core.database import Base, SessionLocal, engine
from app.models.booking import (
    DogSize,
    Service,
    SizeCoefficient,
    WorkingHours,
)

logger = logging.getLogger("toilettage.seed")

# Identifiant arbitraire pour le verrou consultatif PostgreSQL (évite que deux
# pods exécutent le seed simultanément). Ignoré sur SQLite (dev/tests).
_ADVISORY_LOCK_ID = 918273645

DEFAULT_SERVICES = [
    dict(slug="bain", name="Bain (shampooing)",
         description="Shampooing adapté, rinçage et séchage.",
         duration_minutes=45, price_cents=3500, sort_order=1),
    dict(slug="tonte", name="Tonte / toilettage",
         description="Coupe et mise en forme du pelage selon la race.",
         duration_minutes=75, price_cents=4500, sort_order=2),
    dict(slug="detartrage", name="Détartrage dentaire à la pince",
         description="Détartrage mécanique doux à la pince.",
         duration_minutes=30, price_cents=2000, sort_order=3),
    dict(slug="forfait-complet", name="Forfait complet (bain + tonte)",
         description="Bain complet suivi d'une tonte/toilettage.",
         duration_minutes=105, price_cents=6000, sort_order=4),
]

DEFAULT_COEFFICIENTS = [
    (DogSize.petit, 0.8),
    (DogSize.moyen, 1.0),
    (DogSize.grand, 1.3),
]

# Lundi(0) à vendredi(4), 9h-18h.
DEFAULT_HOURS = [(wd, time(9, 0), time(18, 0)) for wd in range(0, 5)]


def _is_postgres() -> bool:
    return engine.url.get_backend_name().startswith("postgresql")


def seed() -> None:
    """Crée les tables et insère les données de base (idempotent).

    Protégé par un verrou consultatif PostgreSQL pour éviter les courses entre
    pods au démarrage. Sûr à appeler à chaque démarrage de l'application.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Verrou consultatif : un seul pod seede à la fois (no-op sur SQLite).
        if _is_postgres():
            db.execute(text("SELECT pg_advisory_lock(:id)"), {"id": _ADVISORY_LOCK_ID})

        for size, coef in DEFAULT_COEFFICIENTS:
            exists = db.execute(
                select(SizeCoefficient).where(SizeCoefficient.size == size)
            ).scalar_one_or_none()
            if not exists:
                db.add(SizeCoefficient(size=size, coefficient=coef))

        for svc in DEFAULT_SERVICES:
            exists = db.execute(
                select(Service).where(Service.slug == svc["slug"])
            ).scalar_one_or_none()
            if not exists:
                db.add(Service(**svc))
            else:
                # Mise à jour des tarifs/durées de référence si l'admin ne les a
                # pas encore personnalisés (price_cents à 0 = non renseigné).
                if not exists.price_cents:
                    exists.price_cents = svc["price_cents"]

        for wd, start, end in DEFAULT_HOURS:
            exists = db.execute(
                select(WorkingHours).where(WorkingHours.weekday == wd)
            ).scalar_one_or_none()
            if not exists:
                db.add(WorkingHours(weekday=wd, start_time=start, end_time=end))

        db.commit()
        logger.info("Seed terminé avec succès.")
        print("Seed terminé avec succès.")
    finally:
        if _is_postgres():
            db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _ADVISORY_LOCK_ID})
            db.commit()
        db.close()


def seed_safe() -> None:
    """Appelle seed() en avalant les erreurs (pour le démarrage de l'app).

    Si la base n'est pas encore prête, on journalise sans faire planter le pod :
    les probes doivent pouvoir passer et un redémarrage réessaiera.
    """
    try:
        seed()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Seed au démarrage ignoré (réessai plus tard) : %s", exc)


if __name__ == "__main__":
    seed()
