"""Endpoints d'administration (protégés par Keycloak, realm dédié).

Panneau minimal mais extensible : lister/gérer les réservations, prestations,
heures de travail. Toute route dépend de require_admin.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.database import get_db
from app.models.booking import (
    Booking,
    BookingStatus,
    Service,
    WorkingHours,
)
from app.schemas.booking import (
    BookingOut,
    BookingStatusUpdate,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    WorkingHoursIn,
    WorkingHoursOut,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# --- Réservations ---
@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    status_filter: BookingStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Booking).order_by(Booking.start_at)
    if status_filter:
        stmt = stmt.where(Booking.status == status_filter)
    if date_from:
        stmt = stmt.where(Booking.start_at >= date_from)
    if date_to:
        stmt = stmt.where(Booking.start_at <= date_to)
    return db.execute(stmt).scalars().all()


@router.patch("/bookings/{booking_id}", response_model=BookingOut)
def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    booking.status = payload.status
    db.commit()
    db.refresh(booking)
    return booking


# --- Prestations ---
@router.get("/services", response_model=list[ServiceOut])
def admin_list_services(db: Session = Depends(get_db)):
    return db.execute(
        select(Service).order_by(Service.sort_order, Service.id)
    ).scalars().all()


@router.post("/services", response_model=ServiceOut, status_code=201)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    if db.execute(
        select(Service).where(Service.slug == payload.slug)
    ).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="slug déjà utilisé")
    service = Service(**payload.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch("/services/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: int, payload: ServiceUpdate, db: Session = Depends(get_db)
):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Prestation introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service


# --- Heures de travail ---
@router.get("/working-hours", response_model=list[WorkingHoursOut])
def list_working_hours(db: Session = Depends(get_db)):
    return db.execute(
        select(WorkingHours).order_by(WorkingHours.weekday)
    ).scalars().all()


@router.put("/working-hours/{weekday}", response_model=WorkingHoursOut)
def set_working_hours(
    weekday: int, payload: WorkingHoursIn, db: Session = Depends(get_db)
):
    if weekday != payload.weekday:
        raise HTTPException(status_code=422, detail="weekday incohérent")
    row = db.execute(
        select(WorkingHours).where(WorkingHours.weekday == weekday)
    ).scalar_one_or_none()
    if row is None:
        row = WorkingHours(**payload.model_dump())
        db.add(row)
    else:
        row.start_time = payload.start_time
        row.end_time = payload.end_time
        row.active = payload.active
    db.commit()
    db.refresh(row)
    return row
