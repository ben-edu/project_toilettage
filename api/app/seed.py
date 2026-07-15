"""Initialisation des tables et données de base.

Usage : python -m app.seed
Crée les tables (dev/staging ; en prod préférer Alembic) et insère :
- les coefficients de taille par défaut ;
- les prestations initiales (non définitives) ;
- des heures de travail par défaut (lun-ven 9h-18h).

Idempotent : ne recrée pas ce qui existe déjà.
"""

from datetime import time

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.models.booking import (
    DogSize,
    Service,
    SizeCoefficient,
    WorkingHours,
)

DEFAULT_SERVICES = [
    dict(slug="bain", name="Bain (shampooing)",
         description="Shampooing adapté, rinçage et séchage.",
         duration_minutes=45, sort_order=1),
    dict(slug="tonte", name="Tonte / toilettage",
         description="Coupe et mise en forme du pelage selon la race.",
         duration_minutes=75, sort_order=2),
    dict(slug="detartrage", name="Détartrage dentaire à la pince",
         description="Détartrage mécanique doux à la pince.",
         duration_minutes=30, sort_order=3),
    dict(slug="forfait-complet", name="Forfait complet (bain + tonte)",
         description="Bain complet suivi d'une tonte/toilettage.",
         duration_minutes=105, sort_order=4),
]

DEFAULT_COEFFICIENTS = [
    (DogSize.petit, 0.8),
    (DogSize.moyen, 1.0),
    (DogSize.grand, 1.3),
]

# Lundi(0) à vendredi(4), 9h-18h.
DEFAULT_HOURS = [(wd, time(9, 0), time(18, 0)) for wd in range(0, 5)]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
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

        for wd, start, end in DEFAULT_HOURS:
            exists = db.execute(
                select(WorkingHours).where(WorkingHours.weekday == wd)
            ).scalar_one_or_none()
            if not exists:
                db.add(WorkingHours(weekday=wd, start_time=start, end_time=end))

        db.commit()
        print("Seed terminé avec succès.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
