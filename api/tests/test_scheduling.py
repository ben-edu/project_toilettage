"""Tests de la logique de planification (durée, créneaux, buffer, chevauchement).

Utilise SQLite en mémoire de fichier, indépendant de PostgreSQL.
Lancer : cd api && PYTHONPATH=. pytest -q
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

# Forcer SQLite avant l'import des modules applicatifs.
import app.core.config as cfg

cfg.Settings.database_url = property(lambda self: "sqlite:///./test_toilettage.db")

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.booking import (  # noqa: E402
    Booking,
    BookingStatus,
    DogSize,
    Service,
    SizeCoefficient,
    WorkingHours,
)
from app.services import scheduling  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    session.add(Service(slug="bain", name="Bain", duration_minutes=45, sort_order=1))
    for s, c in [(DogSize.petit, 0.8), (DogSize.moyen, 1.0), (DogSize.grand, 1.3)]:
        session.add(SizeCoefficient(size=s, coefficient=c))
    for wd in range(0, 5):
        session.add(
            WorkingHours(weekday=wd, start_time=time(9, 0), end_time=time(18, 0))
        )
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _next_monday() -> datetime:
    now = datetime.now(PARIS)
    ahead = (0 - now.weekday()) % 7 or 7
    return (now + timedelta(days=ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def test_duration_coefficient(db):
    svc = db.query(Service).first()
    assert scheduling.effective_duration_minutes(db, svc, DogSize.petit) == 36
    assert scheduling.effective_duration_minutes(db, svc, DogSize.moyen) == 45
    assert scheduling.effective_duration_minutes(db, svc, DogSize.grand) == 59


def test_slots_within_working_hours(db):
    svc = db.query(Service).first()
    monday = _next_monday()
    slots = scheduling.generate_slots(
        db, svc, DogSize.moyen, monday, monday + timedelta(days=1)
    )
    assert slots, "au moins un créneau attendu"
    assert slots[0].start_at.hour == 9
    # Dernier créneau se termine au plus tard à 18h.
    assert all(s.end_at.hour <= 18 for s in slots)


def test_buffer_blocks_following_slots(db):
    svc = db.query(Service).first()
    monday = _next_monday()
    ok, end_at, blocked, dur = scheduling.is_slot_available(
        db, svc, DogSize.moyen, monday.replace(hour=10)
    )
    assert ok
    db.add(
        Booking(
            service_id=svc.id,
            dog_size=DogSize.moyen,
            customer_name="Test",
            customer_email="t@t.fr",
            address="x",
            latitude=47.9,
            longitude=1.9,
            distance_km=1.0,
            start_at=monday.replace(hour=10),
            end_at=end_at,
            blocked_until=blocked,
            effective_duration_minutes=dur,
            status=BookingStatus.confirmed,
        )
    )
    db.commit()

    # 10:00-10:45 + buffer 30 => bloqué jusqu'à 11:15
    assert not scheduling.is_slot_available(db, svc, DogSize.moyen, monday.replace(hour=10))[0]
    assert not scheduling.is_slot_available(db, svc, DogSize.moyen, monday.replace(hour=11))[0]
    assert scheduling.is_slot_available(db, svc, DogSize.moyen, monday.replace(hour=11, minute=15))[0]


def test_haversine_zero():
    from app.services.geocoding import haversine_km

    assert haversine_km(47.9027, 1.9086, 47.9027, 1.9086) < 0.001
