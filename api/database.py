"""Moteurs et sessions SQLAlchemy 2.x : un pour la lecture, un pour l'écriture."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.reader: Engine = create_engine(settings.database_url(), pool_pre_ping=True)
        self.writer: Engine = create_engine(settings.database_url(writer=True), pool_pre_ping=True)
        self.read_session = sessionmaker(self.reader, expire_on_commit=False)
        self.write_session = sessionmaker(self.writer, expire_on_commit=False)

    def dispose(self) -> None:
        self.reader.dispose()
        self.writer.dispose()


def get_db(request: Request) -> Database:
    return request.app.state.db


def read_session(db: Annotated[Database, Depends(get_db)]) -> Iterator[Session]:
    with db.read_session() as session:
        yield session


def write_session(db: Annotated[Database, Depends(get_db)]) -> Iterator[Session]:
    with db.write_session() as session:
        yield session
