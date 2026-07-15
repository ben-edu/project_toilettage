"""Endpoints publics (aucune authentification)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.booking import Booking, BookingStatus, Service
from app.schemas.booking import (
    AvailabilityQuery,
    BookingCreate,
    BookingOut,
    GeocodeResult,
    ServiceOut,
    SlotOut,
)
from app.services import email as email_service
from app.services.geocoding import geocode_address
from app.services.scheduling import generate_slots, is_slot_available, PARIS

router = APIRouter(tags=["public"])


@router.get("/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    """Liste les prestations actives, triées."""
    rows = db.execute(
        select(Service)
        .where(Service.active.is_(True))
        .order_by(Service.sort_order, Service.id)
    ).scalars().all()
    return rows


@router.post("/geocode/check", response_model=GeocodeResult)
async def check_zone(address: str, db: Session = Depends(get_db)):
    """Géocode une adresse et indique si elle est dans la zone de service."""
    result = await geocode_address(address)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adresse introuvable. Merci de préciser (numéro, rue, ville).",
        )
    return result


@router.post("/availability", response_model=list[SlotOut])
def availability(query: AvailabilityQuery, db: Session = Depends(get_db)):
    """Retourne les créneaux disponibles pour une prestation + taille."""
    service = db.get(Service, query.service_id)
    if service is None or not service.active:
        raise HTTPException(status_code=404, detail="Prestation introuvable")

    slots = generate_slots(
        db, service, query.dog_size, query.date_from, query.date_to
    )
    return slots


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    """Crée une réservation après vérification zone + disponibilité."""
    service = db.get(Service, payload.service_id)
    if service is None or not service.active:
        raise HTTPException(status_code=404, detail="Prestation introuvable")

    # 1. Vérifier la zone géographique.
    geo = await geocode_address(payload.address)
    if geo is None:
        raise HTTPException(
            status_code=422,
            detail="Adresse introuvable. Merci de la préciser.",
        )
    if not geo.in_zone:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Désolé, votre adresse est à {geo.distance_km} km du centre "
                f"et se situe hors de notre zone de déplacement pour le moment."
            ),
        )

    # 2. Vérifier la disponibilité du créneau (anti-concurrence).
    available, end_at, blocked_until, duration = is_slot_available(
        db, service, payload.dog_size, payload.start_at
    )
    if not available:
        raise HTTPException(
            status_code=409,
            detail="Ce créneau vient d'être pris. Merci d'en choisir un autre.",
        )

    start_at = payload.start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=PARIS)

    booking = Booking(
        service_id=service.id,
        dog_size=payload.dog_size,
        dog_name=payload.dog_name,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
        address=payload.address,
        postal_code=payload.postal_code,
        city=payload.city,
        latitude=geo.latitude,
        longitude=geo.longitude,
        distance_km=geo.distance_km,
        start_at=start_at,
        end_at=end_at,
        blocked_until=blocked_until,
        effective_duration_minutes=duration,
        status=BookingStatus.confirmed,
        notes=payload.notes,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # 3. Emails (best-effort : n'empêche pas la réservation en cas d'échec).
    start_str = start_at.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M")
    try:
        await email_service.send_booking_confirmation(
            customer_email=booking.customer_email,
            customer_name=booking.customer_name,
            service_name=service.name,
            start_at_str=start_str,
            address=booking.address,
        )
        await email_service.send_groomer_notification(
            service_name=service.name,
            start_at_str=start_str,
            customer_name=booking.customer_name,
            customer_phone=booking.customer_phone,
            address=booking.address,
            dog_size=booking.dog_size.value,
            distance_km=booking.distance_km,
        )
    except Exception:  # noqa: BLE001 — email ne doit pas casser la réservation
        pass

    return booking
