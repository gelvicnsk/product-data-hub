"""API du Product Data Hub.

uvicorn api.main:app --port 8001        # documentation interactive : /docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text

from api.auth import TokenVerifier
from api.config import Settings, get_settings
from api.database import Database, get_db
from api.routers import corrections, products, quality


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = Database(settings)
        app.state.token_verifier = TokenVerifier(settings)
        yield
        app.state.db.dispose()

    app = FastAPI(
        title="Product Data Hub API",
        version="1.0.0",
        description="Golden record produit consolidé depuis l'ERP, le PLM, le catalogue et le CRM "
        "(données synthétiques). Authentification : jeton Keycloak (Bearer).",
        lifespan=lifespan,
    )
    app.include_router(products.router)
    app.include_router(quality.router)
    app.include_router(corrections.router)

    @app.get("/health", tags=["supervision"])
    def health(db: Annotated[Database, Depends(get_db)]) -> dict:
        with db.reader.connect() as conn:
            conn.execute(text("select 1"))
        return {"status": "ok"}

    return app


app = create_app()
