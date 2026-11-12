"""Configuration de l'API, lue dans l'environnement (voir .env.example). Aucun secret en dur."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "product_hub"

    # Deux rôles PostgreSQL distincts (moindre privilège) :
    #   lecture : marts en lecture seule ; écriture : uniquement les tables de app.
    api_db_user: str = "api_reader"
    api_db_password: str = Field(default="", repr=False)
    api_writer_db_user: str = "api_writer"
    api_writer_db_password: str = Field(default="", repr=False)

    # Keycloak (OpenID Connect)
    auth_enabled: bool = True
    keycloak_issuer: str = "http://localhost:8180/realms/product-hub"
    # URL des clés publiques ; vide = <issuer>/protocol/openid-connect/certs.
    # Utile en conteneur : l'API joint Keycloak par http://keycloak:8080 alors que
    # les jetons portent l'URL publique (http://localhost:8180) comme émetteur.
    keycloak_jwks_url: str = ""
    keycloak_audience: str = "product-hub-api"

    @property
    def jwks_url(self) -> str:
        return self.keycloak_jwks_url or f"{self.keycloak_issuer}/protocol/openid-connect/certs"

    def database_url(self, *, writer: bool = False) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.api_writer_db_user if writer else self.api_db_user,
            password=self.api_writer_db_password if writer else self.api_db_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
