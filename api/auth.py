"""Authentification par jeton Keycloak (OpenID Connect, JWT signé RS256).

Pour chaque requête protégée :
1. lire le jeton « Authorization: Bearer <jwt> » ;
2. vérifier la signature avec la clé publique du realm (JWKS, mise en cache) ;
3. vérifier l'émetteur (iss), l'audience (aud = product-hub-api) et l'expiration ;
4. vérifier que l'utilisateur a le rôle demandé (realm_access.roles).

Rôles du realm product-hub :
  reader        lecture du golden record et des indicateurs qualité
  data_steward  reader + création et revue des demandes de correction
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import Settings

bearer = HTTPBearer(auto_error=False, description="Jeton d'accès Keycloak")


@dataclass(frozen=True)
class User:
    username: str
    roles: frozenset[str] = field(default_factory=frozenset)


class TokenVerifier:
    """Valide les jetons ; les clés publiques sont récupérées puis gardées en cache."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks = jwt.PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=600)

    def signing_key(self, token: str):
        return self._jwks.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> User:
        try:
            claims = jwt.decode(
                token,
                self.signing_key(token),
                algorithms=["RS256"],
                audience=self.settings.keycloak_audience,
                issuer=self.settings.keycloak_issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWKClientError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"Clés Keycloak indisponibles : {exc}"
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"Jeton invalide : {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        roles = frozenset(claims.get("realm_access", {}).get("roles", []))
        return User(username=claims.get("preferred_username", claims["sub"]), roles=roles)


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        # mode démo sans Keycloak (AUTH_ENABLED=false) : jamais en production
        return User(username="anonymous", roles=frozenset({"reader", "data_steward"}))
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Jeton manquant", headers={"WWW-Authenticate": "Bearer"}
        )
    return request.app.state.token_verifier.verify(credentials.credentials)


def require_role(role: str) -> Callable[[User], User]:
    def _check(user: Annotated[User, Depends(current_user)]) -> User:
        if role not in user.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Rôle requis : {role}")
        return user

    return _check
