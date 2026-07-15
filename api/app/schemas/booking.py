"""Schémas Pydantic (validation entrée/sortie API)."""

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.booking import BookingStatus, DogSize


# --- Prestations ---
class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str
    duration_minutes: int
    price_cents: int
    active: bool
    sort_order: int


class ServiceCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    duration_minutes: int = Field(gt=0, le=600)
    price_cents: int = Field(default=0, ge=0)
    active: bool = True
    sort_order: int = 0


class ServiceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=600)
    price_cents: int | None = Field(default=None, ge=0)
    active: bool | None = None
    sort_order: int | None = None


# --- Disponibilités / créneaux ---
class SlotOut(BaseModel):
    start_at: datetime
    end_at: datetime


class AvailabilityQuery(BaseModel):
    service_id: int
    dog_size: DogSize
    date_from: datetime
    date_to: datetime


# --- Géocodage / vérification de zone ---
class GeocodeResult(BaseModel):
    latitude: float
    longitude: float
    display_name: str
    distance_km: float
    in_zone: bool


# --- Réservation ---
class BookingCreate(BaseModel):
    service_id: int
    dog_size: DogSize
    dog_name: str = ""
    customer_name: str = Field(min_length=1, max_length=128)
    customer_email: EmailStr
    customer_phone: str = Field(default="", max_length=32)
    address: str = Field(min_length=3)
    postal_code: str = ""
    city: str = ""
    # Créneau choisi par le client (début).
    start_at: datetime
    notes: str = ""


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    dog_size: DogSize
    dog_name: str
    customer_name: str
    customer_email: str
    customer_phone: str
    address: str
    city: str
    latitude: float
    longitude: float
    distance_km: float
    start_at: datetime
    end_at: datetime
    effective_duration_minutes: int
    status: BookingStatus
    created_at: datetime


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


# --- Paramètres / heures de travail (admin) ---
class WorkingHoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    active: bool = True


class WorkingHoursOut(WorkingHoursIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
