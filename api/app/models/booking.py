"""Modèles de données — prestations, réservations, paramètres.

Conçu pour être configurable depuis l'admin :
- chaque prestation a sa propre durée de base ;
- la taille du chien applique un coefficient ;
- les paramètres (heures de travail, buffer, rayon) sont en base.
"""

from datetime import datetime, time
import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DogSize(str, enum.Enum):
    petit = "petit"
    moyen = "moyen"
    grand = "grand"


class BookingStatus(str, enum.Enum):
    pending = "pending"        # créée, en attente de confirmation
    confirmed = "confirmed"    # confirmée (email envoyé)
    cancelled = "cancelled"    # annulée
    completed = "completed"    # prestation réalisée


class Service(Base):
    """Une prestation proposée (bain, tonte, détartrage, forfait...)."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    # Durée de base en minutes (pour un chien "moyen" par convention).
    duration_minutes: Mapped[int] = mapped_column(Integer)
    # Prix indicatif en centimes d'euro (0 = sur devis). Phase 2 : paiement.
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bookings: Mapped[list["Booking"]] = relationship(back_populates="service")


class SizeCoefficient(Base):
    """Coefficient multiplicateur de durée selon la taille du chien.

    Ex : petit=0.8, moyen=1.0, grand=1.3. Configurable en admin.
    """

    __tablename__ = "size_coefficients"

    id: Mapped[int] = mapped_column(primary_key=True)
    size: Mapped[DogSize] = mapped_column(Enum(DogSize), unique=True)
    coefficient: Mapped[float] = mapped_column(Float, default=1.0)


class Booking(Base):
    """Une réservation client."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    service: Mapped["Service"] = relationship(back_populates="bookings")

    dog_size: Mapped[DogSize] = mapped_column(Enum(DogSize))
    dog_name: Mapped[str] = mapped_column(String(128), default="")

    # Client
    customer_name: Mapped[str] = mapped_column(String(128))
    customer_email: Mapped[str] = mapped_column(String(256))
    customer_phone: Mapped[str] = mapped_column(String(32), default="")

    # Adresse (vérifiée dans la zone de service)
    address: Mapped[str] = mapped_column(Text)
    postal_code: Mapped[str] = mapped_column(String(16), default="")
    city: Mapped[str] = mapped_column(String(128), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)

    # Créneau réservé (heure locale Europe/Paris, stockée en UTC-aware)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Fin = start + durée effective (déjà calculée avec le coefficient de taille).
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Fin du blocage agenda incluant le buffer de déplacement.
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    effective_duration_minutes: Mapped[int] = mapped_column(Integer)

    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), default=BookingStatus.pending, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WorkingHours(Base):
    """Heures de travail par jour de semaine (0=lundi .. 6=dimanche).

    Absence de ligne pour un jour = jour non travaillé.
    """

    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, unique=True)  # 0..6
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TimeOff(Base):
    """Périodes d'indisponibilité ponctuelles (congés, rendez-vous perso)."""

    __tablename__ = "time_off"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(256), default="")


class AppSetting(Base):
    """Paramètres généraux modifiables en admin (clé/valeur).

    Ex : travel_buffer_minutes, service_radius_km, slot_granularity_minutes.
    Permet de surcharger les valeurs par défaut de la config sans redéploiement.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
