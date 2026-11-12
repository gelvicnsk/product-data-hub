"""Simule N journées d'activité des quatre systèmes source.

    python -m sources.simulate_days            # paramètres de .env ou valeurs par défaut
    python -m sources.simulate_days --days 5   # surcharge ponctuelle

Sorties :
    data/landing/erp/AAAA-MM-JJ/{MARA,MBEW,MARD,STPO}_AAAAMMJJ.csv   exports ERP
    data/landing/plm/AAAA-MM-JJ/plm_lifecycle_AAAAMMJJ.json          export PLM
    data/landing/catalog/AAAA-MM-JJ/catalog_AAAAMMJJ.csv             export catalogue
    data/crm_db/{accounts,quotes,quote_lines}.jsonl                  « base » du faux CRM
    data/anomalies.json                                              anomalies injectées
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from sources import anomalies as an
from sources import generate_catalog, generate_crm, generate_erp, generate_plm
from sources.config import SimConfig


def crm_db_dir(cfg: SimConfig) -> Path:
    return cfg.landing_dir.parent / "crm_db"


def anomalies_path(cfg: SimConfig) -> Path:
    return cfg.landing_dir.parent / "anomalies.json"


def _write_csv(df: pd.DataFrame, path: Path, sep: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=sep, index=False, lineterminator="\n", encoding="utf-8")


def _sellable(
    materials: pd.DataFrame, lifecycle: pd.DataFrame, list_factor: dict[int, float]
) -> list[tuple[str, float]]:
    """Produits vendables aujourd'hui : prix positif, actif dans le PLM (ou service)."""
    state = dict(zip(lifecycle["material_id"], lifecycle["lifecycle_state"], strict=True))
    out = []
    for m in materials.itertuples(index=False):
        if m.material_id >= an.DUPLICATE_ID_START or m.standard_price <= 0:
            continue
        if state.get(m.material_id, "ACTIVE") != "ACTIVE":
            continue
        out.append((str(m.material_id), m.standard_price * list_factor[m.material_id]))
    return out


def simulate(cfg: SimConfig) -> an.AnomalyLog:
    rng = np.random.default_rng(cfg.seed)
    log = an.AnomalyLog()
    n_anom = cfg.anomalies

    # --- état initial -----------------------------------------------------------
    materials = generate_erp.build_materials(cfg, rng)
    bom = generate_erp.build_bom(materials, rng)
    stock = generate_erp.initial_stock(materials, rng)
    lifecycle = generate_plm.build_lifecycle(materials, cfg, rng)
    catalog = generate_catalog.build_catalog(materials, rng)
    list_factor = {
        int(i): float(f)
        for i, f in zip(materials["material_id"], rng.uniform(1.2, 1.6, size=len(materials)), strict=True)
    }

    # --- anomalies permanentes ----------------------------------------------------
    catalog = an.inject_catalog_gaps(
        catalog, n_anom["missing_from_catalog"], n_anom["missing_catalog_description"], rng, log
    )
    materials = an.inject_duplicate_materials(materials, n_anom["duplicate_material"], rng, log)
    frozen = an.inject_non_positive_prices(materials, n_anom["non_positive_price"], rng, log)

    # --- anomalies de devis, réparties dans le temps -------------------------------------
    unknown_days = an.schedule_days(n_anom["unknown_product_in_quotes"], cfg.days, rng)
    eol_days = an.schedule_days(n_anom["eol_product_in_quotes"], cfg.days, rng)
    unknown_counter = 0

    crm = generate_crm.CrmSimulator(rng)
    crm.create_accounts(cfg.n_accounts, cfg.start_date)

    for i, day in enumerate(cfg.dates):
        if i > 0:
            generate_erp.evolve_prices(materials, day, cfg, rng, frozen)
            generate_erp.evolve_stock(stock, rng)
            generate_plm.evolve_lifecycle(lifecycle, day, cfg, rng)
            crm.touch_accounts(day)
            crm.advance_quotes(day)

        # devis normaux
        sellable = _sellable(materials, lifecycle, list_factor)
        mean = 3 if i == cfg.quote_volume_drop_day else cfg.quotes_per_day
        for _ in range(int(rng.poisson(mean))):
            k = int(rng.integers(1, cfg.max_lines_per_quote + 1))
            picks = rng.choice(len(sellable), size=k, replace=False)
            crm.create_quote(day, [sellable[p] for p in picks])

        # devis anormaux prévus ce jour-là
        for _ in range(unknown_days.count(i)):
            code = an.unknown_product_code(unknown_counter)
            unknown_counter += 1
            quote_id = crm.create_quote(day, [(code, 999.0)])
            log.add("unknown_product_in_quotes", [{"quote_id": quote_id, "product_code": code}])
        eol = lifecycle[lifecycle["lifecycle_state"] == "END_OF_LIFE"]["material_id"].to_numpy()
        for _ in range(eol_days.count(i)):
            mid = int(rng.choice(eol))
            price = float(materials.loc[materials["material_id"] == mid, "standard_price"].iloc[0])
            quote_id = crm.create_quote(day, [(str(mid), price * list_factor[mid])])
            log.add(
                "eol_product_in_quotes",
                [{"quote_id": quote_id, "product_code": str(mid), "date": day.isoformat()}],
            )

        _write_day_files(cfg, i, day, materials, bom, stock, lifecycle, catalog, log)

    crm.write(crm_db_dir(cfg))
    if cfg.quote_volume_drop_day < cfg.days:
        an.record_incident(log, "quote_volume_drop", cfg.dates[cfg.quote_volume_drop_day])
    log.write(anomalies_path(cfg))
    return log


def _write_day_files(
    cfg: SimConfig,
    i: int,
    day: date,
    materials: pd.DataFrame,
    bom: pd.DataFrame,
    stock: pd.DataFrame,
    lifecycle: pd.DataFrame,
    catalog: pd.DataFrame,
    log: an.AnomalyLog,
) -> None:
    stamp = day.strftime("%Y%m%d")
    folder = day.isoformat()

    if i == cfg.erp_missing_day:
        an.record_incident(log, "erp_missing_export", day)
    else:
        renamed = i == cfg.erp_renamed_column_day
        if renamed:
            an.record_incident(log, "erp_renamed_column", day)
        for table, df in generate_erp.erp_exports(materials, bom, stock, renamed).items():
            _write_csv(df, cfg.landing_dir / "erp" / folder / f"{table}_{stamp}.csv", sep=";")

    plm_path = cfg.landing_dir / "plm" / folder / f"plm_lifecycle_{stamp}.json"
    plm_path.parent.mkdir(parents=True, exist_ok=True)
    plm_path.write_text(json.dumps(generate_plm.plm_export(lifecycle), indent=1) + "\n", encoding="utf-8")

    _write_csv(
        generate_catalog.catalog_export(catalog),
        cfg.landing_dir / "catalog" / folder / f"catalog_{stamp}.csv",
        sep=",",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days", type=int, help="nombre de journées à simuler")
    parser.add_argument("--start-date", type=date.fromisoformat, help="AAAA-MM-JJ")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    cfg = SimConfig.from_env()
    overrides = {
        k: v
        for k, v in {"days": args.days, "start_date": args.start_date, "seed": args.seed}.items()
        if v is not None
    }
    cfg = replace(cfg, **overrides)

    # repartir d'une zone de dépôt vide : la simulation est rejouée entièrement
    for path in (cfg.landing_dir, crm_db_dir(cfg)):
        if path.exists():
            shutil.rmtree(path)

    log = simulate(cfg)
    print(f"{cfg.days} journées simulées à partir du {cfg.start_date} (graine {cfg.seed})")
    for kind, n in log.counts.items():
        print(f"  anomalie {kind:<30} {n}")
    for kind, d in log.incidents.items():
        print(f"  incident {kind:<30} {d}")


if __name__ == "__main__":
    main()
