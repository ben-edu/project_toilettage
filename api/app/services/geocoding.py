"""Géocodage d'adresse et vérification de la zone de service.

Utilise Nominatim (OpenStreetMap, gratuit). La politique d'usage de Nominatim
impose un User-Agent identifiable et un usage raisonnable (max ~1 req/s).
Pour la production à volume, envisager un Nominatim auto-hébergé.
"""

from math import asin, cos, radians, sin, sqrt

import httpx

from app.core.config import get_settings
from app.schemas.booking import GeocodeResult

settings = get_settings()

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance orthodromique (à vol d'oiseau) entre deux points, en km."""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


async def geocode_address(address: str) -> GeocodeResult | None:
    """Géocode une adresse et calcule la distance au centre de service.

    Retourne None si l'adresse est introuvable.
    """
    params = {
        "q": address,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "fr",
        "addressdetails": 1,
    }
    headers = {"User-Agent": settings.nominatim_user_agent}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.nominatim_url}/search", params=params, headers=headers
        )
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return None

    top = results[0]
    lat = float(top["lat"])
    lng = float(top["lon"])
    distance = haversine_km(
        settings.service_center_lat, settings.service_center_lng, lat, lng
    )

    return GeocodeResult(
        latitude=lat,
        longitude=lng,
        display_name=top.get("display_name", ""),
        distance_km=round(distance, 2),
        in_zone=distance <= settings.service_radius_km,
    )
