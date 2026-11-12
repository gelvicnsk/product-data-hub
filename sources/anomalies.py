"""Anomalies injectées volontairement dans les sources.

Chaque anomalie est enregistrée dans data/anomalies.json avec son nombre et
les identifiants concernés : les tests dbt et Elementary doivent toutes les
retrouver. C'est ce qui permet de « tester les tests ».
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

DUPLICATE_ID_START = 19_000_000
UNKNOWN_PRODUCT_START = 18_000_000


@dataclass
class AnomalyLog:
    counts: dict[str, int] = field(default_factory=dict)
    details: dict[str, list] = field(default_factory=dict)
    incidents: dict[str, str] = field(default_factory=dict)

    def add(self, kind: str, items: list) -> None:
        self.details.setdefault(kind, []).extend(items)
        self.counts[kind] = len(self.details[kind])

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"counts": self.counts, "details": self.details, "incidents": self.incidents}
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
        )


def inject_duplicate_materials(
    materials: pd.DataFrame, n: int, rng: np.random.Generator, log: AnomalyLog
) -> pd.DataFrame:
    """Recrée n articles finis sous un second code ERP (même référence constructeur)."""
    originals = materials[materials["mtart"] == "FERT"].sample(n=n, random_state=rng)
    copies = originals.copy()
    copies["material_id"] = [DUPLICATE_ID_START + i for i in range(n)]
    log.add(
        "duplicate_material",
        [
            {"original_material_id": int(o), "duplicate_material_id": int(c), "mfrpn": p}
            for o, c, p in zip(
                originals["material_id"], copies["material_id"], originals["mfrpn"], strict=True
            )
        ],
    )
    return pd.concat([materials, copies], ignore_index=True)


def inject_non_positive_prices(
    materials: pd.DataFrame, n: int, rng: np.random.Generator, log: AnomalyLog
) -> set[int]:
    """Met n prix à zéro ou en négatif ; renvoie les articles dont le prix ne bougera plus."""
    candidates = materials[materials["material_id"] < DUPLICATE_ID_START]
    idx = rng.choice(candidates.index, size=n, replace=False)
    materials.loc[idx, "standard_price"] = rng.choice([0.0, -1.0, -150.0], size=n)
    ids = [int(x) for x in materials.loc[idx, "material_id"]]
    log.add("non_positive_price", ids)
    return set(ids)


def inject_catalog_gaps(
    catalog: pd.DataFrame, n_missing: int, n_empty: int, rng: np.random.Generator, log: AnomalyLog
) -> pd.DataFrame:
    """Retire n_missing articles du catalogue et vide la description de n_empty autres."""
    idx = rng.choice(catalog.index, size=n_missing + n_empty, replace=False)
    missing, empty = idx[:n_missing], idx[n_missing:]
    log.add("missing_from_catalog", [int(x) for x in catalog.loc[missing, "material_id"]])
    log.add("missing_catalog_description", [int(x) for x in catalog.loc[empty, "material_id"]])
    catalog = catalog.copy()
    catalog.loc[empty, "description"] = ""
    return catalog.drop(index=missing).reset_index(drop=True)


def schedule_days(n_items: int, n_days: int, rng: np.random.Generator) -> list[int]:
    """Répartit des anomalies de devis sur des jours tirés au hasard (jamais le jour 0)."""
    if n_days < 2:
        return [0] * n_items
    return sorted(int(d) for d in rng.integers(1, n_days, size=n_items))


def unknown_product_code(i: int) -> str:
    return str(UNKNOWN_PRODUCT_START + i)


def record_incident(log: AnomalyLog, kind: str, day: date) -> None:
    log.incidents[kind] = day.isoformat()
