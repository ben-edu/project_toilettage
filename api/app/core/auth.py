"""Validation des tokens Keycloak pour protéger les endpoints admin.

Le réseau public de réservation ne nécessite AUCUNE authentification.
Seuls les endpoints /admin/* exigent un token Bearer valide émis par le realm
dédié Keycloak.

La validation se fait via JWKS (clés publiques du realm) : l'API n'a pas besoin
du secret client pour vérifier une signature. Les clés sont mises en cache.
"""

import time

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError

from app.core.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=True)

_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL = 3600  # 1 h


async def _get_jwks() -> dict:
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(settings.keycloak_jwks_url)
        resp.raise_for_status()
        jwks = resp.json()
    _jwks_cache["keys"] = jwks
    _jwks_cache["fetched_at"] = now
    return jwks


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Dépendance FastAPI : valide le token et renvoie les claims.

    Lève 401 si le token est invalide/expiré.
    """
    token = credentials.credentials
    jwks = await _get_jwks()

    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Clé de signature inconnue",
            )
        claims = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            issuer=settings.keycloak_issuer,
            options={"verify_aud": False},  # aud non strict côté API
        )
    except (JWTError, KeyError, StopIteration) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
        ) from exc

    return claims
