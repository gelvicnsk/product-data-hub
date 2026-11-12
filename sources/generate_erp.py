"""Simulation de l'ERP (type SAP) : référentiel article, prix, stocks, nomenclatures.

Les exports reprennent les noms de tables et de colonnes SAP, ainsi que leurs
conventions : séparateur ';', décimale ',', dates au format AAAAMMJJ,
numéro d'article (MATNR) sur 18 caractères complétés par des zéros.

| Fichier | Table SAP | Contenu                                   |
|---------|-----------|-------------------------------------------|
| MARA    | MARA+MAKT | données générales de l'article            |
| MBEW    | MBEW      | valorisation : prix standard par site     |
| MARD    | MARD      | stock par site et magasin                 |
| STPO    | STPO      | postes de nomenclature (composants)       |
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from sources import reference as ref
from sources.config import SimConfig

MATERIAL_ID_START = 10_000_000


def matnr(material_id: int) -> str:
    """Numéro d'article SAP : 18 caractères, complété à gauche par des zéros."""
    return str(material_id).zfill(18)


def sap_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def sap_decimal(x: float) -> str:
    """Montant au format SAP exporté en France : décimale avec une virgule."""
    return f"{x:.2f}".replace(".", ",")


def build_materials(cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Référentiel article interne de la simulation (vérité terrain).

    Colonnes : material_id, family, matkl, mtart, meins, maktx, mfrpn,
    standard_price, plant, created_on.
    """
    families = list(ref.FAMILY_WEIGHTS)
    weights = np.array(list(ref.FAMILY_WEIGHTS.values()))
    chosen = rng.choice(families, size=cfg.n_materials, p=weights / weights.sum())

    rows = []
    used_mfrpn: set[str] = set()
    for i, family in enumerate(chosen):
        matkl, prefix, pmin, pmax = ref.FAMILIES[family]
        # prix log-uniforme : beaucoup d'articles peu chers, quelques très chers
        price = float(np.exp(rng.uniform(np.log(pmin), np.log(pmax))))
        while True:
            mfrpn = f"{prefix}-{int(rng.integers(10_000, 99_999))}-{rng.choice(list('ABCDEFGH'))}"
            if mfrpn not in used_mfrpn:
                used_mfrpn.add(mfrpn)
                break
        mtart = ref.material_type(family)
        rows.append(
            {
                "material_id": MATERIAL_ID_START + i,
                "family": family,
                "matkl": matkl,
                "mtart": mtart,
                "meins": "LE" if mtart == "DIEN" else "ST",
                "maktx": ref.product_name(rng, family),
                "mfrpn": mfrpn,
                "standard_price": round(price, 2),
                "plant": str(rng.choice(ref.PLANTS)),
                "created_on": cfg.start_date - timedelta(days=int(rng.integers(30, 2_000))),
                "changed_on": None,
            }
        )
    return pd.DataFrame(rows)


def build_bom(materials: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Nomenclatures : chaque système (serveur, stockage) a 3 à 6 composants."""
    systems = materials[materials["family"].isin(ref.SYSTEM_FAMILIES)]
    components = materials[materials["mtart"] == "HALB"]["material_id"].to_numpy()
    rows = []
    for parent in systems["material_id"]:
        n = int(rng.integers(3, 7))
        for pos, comp in enumerate(rng.choice(components, size=n, replace=False), start=1):
            rows.append(
                {
                    "parent_id": int(parent),
                    "component_id": int(comp),
                    "position": pos * 10,
                    "quantity": int(rng.choice([1, 2, 4, 8])),
                }
            )
    return pd.DataFrame(rows)


def initial_stock(materials: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    goods = materials[materials["mtart"] != "DIEN"]
    rows = []
    for _, m in goods.iterrows():
        for lgort in ref.STORAGE_LOCATIONS[: int(rng.integers(1, 3))]:
            rows.append(
                {
                    "material_id": int(m["material_id"]),
                    "plant": m["plant"],
                    "lgort": lgort,
                    "quantity": int(rng.poisson(40)),
                }
            )
    return pd.DataFrame(rows)


def evolve_prices(
    materials: pd.DataFrame, day: date, cfg: SimConfig, rng: np.random.Generator, frozen_ids: set[int]
) -> None:
    """Modifie en place le prix d'environ 1 % des articles (hausse ou baisse de 2 à 10 %)."""
    eligible = materials.index[~materials["material_id"].isin(frozen_ids)]
    n = rng.binomial(len(eligible), cfg.daily_price_change_rate)
    if n == 0:
        return
    idx = rng.choice(eligible, size=n, replace=False)
    factor = 1 + rng.choice([-1, 1], size=n) * rng.uniform(0.02, 0.10, size=n)
    materials.loc[idx, "standard_price"] = (materials.loc[idx, "standard_price"] * factor).round(2)
    materials.loc[idx, "changed_on"] = day


def evolve_stock(stock: pd.DataFrame, rng: np.random.Generator) -> None:
    """Marche aléatoire du stock : sorties et réceptions de la journée."""
    delta = rng.integers(-5, 6, size=len(stock))
    stock["quantity"] = (stock["quantity"] + delta).clip(lower=0)


def erp_exports(
    materials: pd.DataFrame, bom: pd.DataFrame, stock: pd.DataFrame, renamed_column: bool = False
) -> dict[str, pd.DataFrame]:
    """Tables exportées par l'ERP pour une journée, au format SAP."""
    mara = pd.DataFrame(
        {
            "MATNR": materials["material_id"].map(matnr),
            "MAKTX": materials["maktx"],
            "MTART": materials["mtart"],
            "MATKL": materials["matkl"],
            "MEINS": materials["meins"],
            "MFRPN": materials["mfrpn"],
            "ERSDA": materials["created_on"].map(sap_date),
            "LAEDA": materials["changed_on"].map(lambda d: sap_date(d) if d else ""),
        }
    )
    if renamed_column:
        # incident simulé : une mise à jour de l'export renomme la désignation
        mara = mara.rename(columns={"MAKTX": "MAKTX_LONG"})

    mbew = pd.DataFrame(
        {
            "MATNR": materials["material_id"].map(matnr),
            "BWKEY": materials["plant"],
            "STPRS": materials["standard_price"].map(sap_decimal),
            "PEINH": "1",
            "WAERS": "EUR",
        }
    )
    mard = pd.DataFrame(
        {
            "MATNR": stock["material_id"].map(matnr),
            "WERKS": stock["plant"],
            "LGORT": stock["lgort"],
            "LABST": stock["quantity"].map(lambda q: f"{q},000"),
        }
    )
    stpo = pd.DataFrame(
        {
            "STLNR": bom["parent_id"].map(matnr),
            "POSNR": bom["position"].map(lambda p: str(p).zfill(4)),
            "IDNRK": bom["component_id"].map(matnr),
            "MENGE": bom["quantity"].map(lambda q: f"{q},000"),
            "MEINS": "ST",
        }
    )
    return {"MARA": mara, "MBEW": mbew, "MARD": mard, "STPO": stpo}
