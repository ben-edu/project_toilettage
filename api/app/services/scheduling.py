"""Génération des créneaux disponibles et calcul de durée.

Règles :
- durée effective = durée de base de la prestation x coefficient de taille ;
- un buffer de déplacement (défaut 30 min) est bloqué APRÈS chaque réservation ;
- les créneaux sont générés depuis les heures de travail quotidiennes ;
- un créneau n'est proposé que s'il ne chevauche aucune réservation existante
  (buffer inclus) ni aucune période d'indisponibilité (TimeOff).

Un seul agenda (un toiletteur), donc pas de dimension "ressource".
Fuseau : Europe/Paris.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.booking import (
    AppSetting,
    Booking,
    BookingStatus,
    DogSize,
    Service,
    SizeCoefficient,
    TimeOff,
    WorkingHours,
)
from app.schemas.booking import SlotOut

settings = get_settings()
PARIS = ZoneInfo("Europe/Paris")


def _get_setting_int(db: Session, key: str, default: int) -> int:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return default


def get_size_coefficient(db: Session, size: DogSize) -> float:
    row = db.execute(
        select(SizeCoefficient).where(SizeCoefficient.size == size)
    ).scalar_one_or_none()
    return row.coefficient if row else 1.0


def effective_duration_minutes(db: Session, service: Service, size: DogSize) -> int:
    """Durée effective arrondie à la minute supérieure."""
    coef = get_size_coefficient(db, size)
    raw = service.duration_minutes * coef
    return int(-(-raw // 1))  # ceil


def _working_intervals_for_day(
    db: Session, day: datetime
) -> list[tuple[datetime, datetime]]:
    """Renvoie les intervalles travaillés (tz-aware) pour un jour donné."""
    wh = db.execute(
        select(WorkingHours).where(
            WorkingHours.weekday == day.weekday(),
            WorkingHours.active.is_(True),
        )
    ).scalar_one_or_none()

    if wh is None:
        # Repli sur la config par défaut si aucune ligne en base.
        start = day.replace(
            hour=settings.work_start_hour, minute=0, second=0, microsecond=0
        )
        end = day.replace(
            hour=settings.work_end_hour, minute=0, second=0, microsecond=0
        )
        # Semaine seulement par défaut (lun-ven) si rien n'est configuré.
        if day.weekday() >= 5:
            return []
        return [(start, end)]

    start = day.replace(
        hour=wh.start_time.hour, minute=wh.start_time.minute,
        second=0, microsecond=0,
    )
    end = day.replace(
        hour=wh.end_time.hour, minute=wh.end_time.minute,
        second=0, microsecond=0,
    )
    return [(start, end)]


def _busy_intervals(
    db: Session, date_from: datetime, date_to: datetime
) -> list[tuple[datetime, datetime]]:
    """Réservations actives (buffer inclus) + indisponibilités, en tz-aware."""
    busy: list[tuple[datetime, datetime]] = []

    bookings = db.execute(
        select(Booking).where(
            Booking.status.in_(
                [BookingStatus.pending, BookingStatus.confirmed]
            ),
            Booking.blocked_until > date_from,
            Booking.start_at < date_to,
        )
    ).scalars()
    for b in bookings:
        busy.append((_as_paris(b.start_at), _as_paris(b.blocked_until)))

    offs = db.execute(
        select(TimeOff).where(
            TimeOff.end_at > date_from, TimeOff.start_at < date_to
        )
    ).scalars()
    for o in offs:
        busy.append((_as_paris(o.start_at), _as_paris(o.end_at)))

    return busy


def _as_paris(dt: datetime) -> datetime:
    """Normalise en tz-aware Europe/Paris.

    Certains backends (ex. SQLite) ne conservent pas le tzinfo ; PostgreSQL avec
    timestamptz le conserve. On rend la comparaison sûre dans tous les cas.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=PARIS)
    return dt.astimezone(PARIS)


def _overlaps(
    start: datetime, end: datetime, intervals: list[tuple[datetime, datetime]]
) -> bool:
    start = _as_paris(start)
    end = _as_paris(end)
    return any(start < i_end and end > i_start for i_start, i_end in intervals)


def generate_slots(
    db: Session,
    service: Service,
    size: DogSize,
    date_from: datetime,
    date_to: datetime,
) -> list[SlotOut]:
    """Génère les créneaux de début possibles entre date_from et date_to.

    date_from / date_to sont tz-aware (Europe/Paris de préférence).
    """
    duration = effective_duration_minutes(db, service, size)
    buffer_min = _get_setting_int(
        db, "travel_buffer_minutes", settings.travel_buffer_minutes
    )
    granularity = _get_setting_int(
        db, "slot_granularity_minutes", settings.slot_granularity_minutes
    )

    # Normaliser en Europe/Paris.
    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=PARIS)
    if date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=PARIS)

    busy = _busy_intervals(db, date_from, date_to)
    now = datetime.now(PARIS)

    slots: list[SlotOut] = []
    day = date_from.replace(hour=0, minute=0, second=0, microsecond=0)

    while day <= date_to:
        for w_start, w_end in _working_intervals_for_day(db, day):
            cursor = w_start
            step = timedelta(minutes=granularity)
            svc_delta = timedelta(minutes=duration)
            buf_delta = timedelta(minutes=buffer_min)

            while cursor + svc_delta <= w_end:
                slot_start = cursor
                slot_end = cursor + svc_delta
                blocked_until = slot_end + buf_delta

                # Filtrer : passé, hors fenêtre demandée, chevauchement.
                if (
                    slot_start >= now
                    and slot_start >= date_from
                    and slot_end <= date_to
                    and not _overlaps(slot_start, blocked_until, busy)
                ):
                    slots.append(SlotOut(start_at=slot_start, end_at=slot_end))

                cursor += step
        day += timedelta(days=1)

    return slots


def is_slot_available(
    db: Session,
    service: Service,
    size: DogSize,
    start_at: datetime,
) -> tuple[bool, datetime, datetime, int]:
    """Vérifie qu'un créneau précis est libre au moment de la réservation.

    Retourne (disponible, end_at, blocked_until, effective_duration).
    Protège contre les réservations concurrentes sur le même créneau.
    """
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=PARIS)

    duration = effective_duration_minutes(db, service, size)
    buffer_min = _get_setting_int(
        db, "travel_buffer_minutes", settings.travel_buffer_minutes
    )
    end_at = start_at + timedelta(minutes=duration)
    blocked_until = end_at + timedelta(minutes=buffer_min)

    # Doit tomber dans un intervalle de travail.
    intervals = _working_intervals_for_day(db, start_at)
    within_hours = any(
        start_at >= w_start and end_at <= w_end for w_start, w_end in intervals
    )
    if not within_hours:
        return False, end_at, blocked_until, duration

    busy = _busy_intervals(
        db, start_at - timedelta(days=1), blocked_until + timedelta(days=1)
    )
    if _overlaps(start_at, blocked_until, busy):
        return False, end_at, blocked_until, duration

    return True, end_at, blocked_until, duration
