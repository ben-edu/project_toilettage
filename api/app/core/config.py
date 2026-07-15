"""Configuration centrale de l'API toilettage.

Toutes les valeurs sensibles proviennent de l'environnement (ConfigMap + Secret
K8s en production, fichier .env en local). Aucun secret n'est codé en dur ici.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Application ---
    app_name: str = "Toilettage API"
    environment: str = Field(default="dev")  # dev | staging | prod
    api_prefix: str = "/api/v1"

    # --- Base de données (PostgreSQL) ---
    # En prod, fournie via Secret K8s (voir secret.example.yaml).
    postgres_host: str = Field(default="toilettage-db")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="toilettage")
    postgres_user: str = Field(default="toilettage")
    postgres_password: str = Field(default="change-me-in-secret")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- CORS : le frontend (Hestia) appelle l'API via le domaine public ---
    # Liste d'origines autorisées, séparées par des virgules.
    cors_origins: str = Field(
        default="https://toilettage.proxbenovh.cloud,"
        "https://staging.toilettage.proxbenovh.cloud"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- Zone géographique ---
    # Point de référence : Place du Martroi, Orléans.
    service_center_lat: float = Field(default=47.9027)
    service_center_lng: float = Field(default=1.9086)
    service_radius_km: float = Field(default=10.0)
    # User-Agent requis par la politique d'usage de Nominatim.
    nominatim_url: str = Field(default="https://nominatim.openstreetmap.org")
    nominatim_user_agent: str = Field(
        default="toilettage-orleans/1.0 (contact: admin@example.com)"
    )

    # --- Agenda / créneaux ---
    work_start_hour: int = Field(default=9)   # 09:00
    work_end_hour: int = Field(default=18)    # 18:00
    travel_buffer_minutes: int = Field(default=30)
    slot_granularity_minutes: int = Field(default=15)

    # --- Email (SMTP SORIA pour les tests au début) ---
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)
    groomer_notification_email: str = Field(default="")

    # --- Keycloak (protège l'admin uniquement ; public = pas de login) ---
    keycloak_url: str = Field(default="https://keycloak.soria-academie.fr")
    keycloak_realm: str = Field(default="toilettage")
    keycloak_client_id: str = Field(default="toilettage-admin")
    # Utilisé côté API pour valider les tokens (issuer / JWKS).

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
