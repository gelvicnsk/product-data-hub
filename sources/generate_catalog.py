"""Simulation du catalogue produit (descriptions commerciales).

Le catalogue identifie les produits par un SKU commercial ('SKU-' + identifiant)
et par la référence constructeur (mfr_part_number, identique au champ SAP MFRPN).
Environ 5 % des lignes n'ont pas de SKU : le rapprochement doit alors se faire
sur la référence constructeur (règle de repli testée dans dbt).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_TAGLINES = [
    "conçu pour les charges de calcul intensif",
    "optimisé pour l'efficacité énergétique",
    "adapté aux environnements de recherche",
    "haute densité pour les centres de données",
    "évolutif et facile à maintenir",
]


def _commercial_name(maktx: str) -> str:
    """'ORION GPU accelerator G4' -> 'Orion GPU accelerator G4'."""
    first, _, rest = maktx.partition(" ")
    return f"{first.capitalize()} {rest}"


def sku(material_id: int) -> str:
    return f"SKU-{material_id}"


def build_catalog(materials: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for m in materials.itertuples(index=False):
        has_sku = rng.random() > 0.05
        name = _commercial_name(m.maktx)
        rows.append(
            {
                "material_id": m.material_id,
                "sku": sku(m.material_id) if has_sku else "",
                "mfr_part_number": m.mfrpn,
                "family": m.family,
                "commercial_name": name,
                "description": f"{name}, {rng.choice(_TAGLINES)}.",
                "configurable": bool(m.family in {"Serveurs rack", "Serveurs lame", "Stockage"}),
            }
        )
    return pd.DataFrame(rows)


def catalog_export(catalog: pd.DataFrame) -> pd.DataFrame:
    """Colonnes publiées par le catalogue (l'identifiant interne n'en fait pas partie)."""
    return catalog.drop(columns=["material_id"]).assign(
        configurable=lambda df: df["configurable"].map({True: "yes", False: "no"})
    )
