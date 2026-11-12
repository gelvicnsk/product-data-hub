"""Environnement Alembic : ne gère QUE le schéma app.

Les migrations tournent avec le rôle propriétaire (POSTGRES_USER), car elles créent
des tables. L'API, elle, se connecte ensuite avec des rôles sans droit de DDL.
Les schémas marts, staging, raw... appartiennent à dbt et à l'ingestion : ils sont
exclus de l'autogénération, sinon Alembic proposerait de les supprimer.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import URL, create_engine, text

from api.models import AppBase

config = context.config
target_metadata = AppBase.metadata
SCHEMA = "app"


def database_url() -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "hub_admin"),
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        database=os.getenv("ALEMBIC_DB", os.getenv("POSTGRES_DB", "product_hub")),
    )


def include_name(name, type_, parent_names) -> bool:
    if type_ == "schema":
        return name == SCHEMA
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=database_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_name=include_name,
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            version_table_schema=SCHEMA,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
