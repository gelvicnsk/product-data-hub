"""Paramètres de la simulation des systèmes source.

Toutes les valeurs ont un défaut et peuvent être surchargées par variable
d'environnement (voir .env.example). Même graine + mêmes paramètres = mêmes
fichiers générés, à l'octet près.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class SimConfig:
    seed: int = 42
    start_date: date = date(2026, 10, 1)
    days: int = 30
    landing_dir: Path = Path("data/landing")

    # volumes
    n_materials: int = 2000
    n_accounts: int = 300
    quotes_per_day: int = 25  # moyenne, tirée selon une loi de Poisson
    max_lines_per_quote: int = 6

    # dynamique quotidienne
    daily_price_change_rate: float = 0.01  # part des articles dont le prix change chaque jour
    daily_lifecycle_change_rate: float = 0.002  # part des articles qui changent d'état PLM chaque jour

    # anomalies (voir sources/anomalies.py et docs/anomalies.md)
    anomalies: dict[str, int] = field(
        default_factory=lambda: {
            "unknown_product_in_quotes": 6,  # article de devis absent de l'ERP
            "eol_product_in_quotes": 8,  # produit en fin de vie toujours vendu
            "missing_catalog_description": 25,  # description commerciale vide
            "missing_from_catalog": 40,  # article ERP absent du catalogue
            "duplicate_material": 4,  # même article, deux codes ERP
            "non_positive_price": 5,  # prix nul ou négatif
        }
    )
    # numéros de jour (0 = start_date) où un incident de livraison est simulé
    erp_missing_day: int = 17  # pas d'export ERP ce jour-là
    quote_volume_drop_day: int = 23  # chute du volume de devis
    erp_renamed_column_day: int = 26  # une colonne SAP renommée dans l'export

    @property
    def dates(self) -> list[date]:
        from datetime import timedelta

        return [self.start_date + timedelta(days=i) for i in range(self.days)]

    @classmethod
    def from_env(cls) -> SimConfig:
        start = os.getenv("SIM_START_DATE")
        return cls(
            seed=_env_int("SIM_SEED", cls.seed),
            start_date=date.fromisoformat(start) if start else cls.start_date,
            days=_env_int("SIM_DAYS", cls.days),
            landing_dir=Path(os.getenv("LANDING_DIR", str(cls.landing_dir))),
        )
