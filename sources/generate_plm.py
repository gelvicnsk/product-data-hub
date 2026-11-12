"""Simulation du PLM : cycle de vie et révisions des produits physiques.

Le PLM ne connaît que les articles physiques (FERT et HALB), sous son propre
identifiant : part_number = 'PN-' + identifiant interne (sans les zéros SAP).
Export quotidien complet au format JSON.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from sources import reference as ref
from sources.config import SimConfig

# transitions autorisées du cycle de vie
NEXT_STATE = {"PROTOTYPE": "ACTIVE", "ACTIVE": "END_OF_LIFE", "END_OF_LIFE": "RETIRED"}


def part_number(material_id: int) -> str:
    return f"PN-{material_id}"


def build_lifecycle(materials: pd.DataFrame, cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    physical = materials[materials["mtart"] != "DIEN"]
    n = len(physical)
    states = rng.choice(ref.PLM_STATES, size=n, p=ref.PLM_STATE_WEIGHTS)
    changed = [
        datetime.combine(cfg.start_date - timedelta(days=int(d)), time(9, 0))
        for d in rng.integers(1, 700, size=n)
    ]
    return pd.DataFrame(
        {
            "material_id": physical["material_id"].to_numpy(),
            "revision": rng.choice(list("ABCD"), size=n, p=[0.5, 0.3, 0.15, 0.05]),
            "lifecycle_state": states,
            "state_changed_at": changed,
            "owner_team": physical["family"].map(ref.PLM_TEAM_BY_FAMILY).to_numpy(),
        }
    )


def evolve_lifecycle(lifecycle: pd.DataFrame, day: date, cfg: SimConfig, rng: np.random.Generator) -> None:
    """Fait avancer quelques produits dans leur cycle de vie ; parfois une nouvelle révision."""
    movable = lifecycle.index[lifecycle["lifecycle_state"] != "RETIRED"]
    n = rng.binomial(len(movable), cfg.daily_lifecycle_change_rate)
    when = datetime.combine(day, time(int(rng.integers(8, 18)), int(rng.integers(0, 60))))
    for idx in rng.choice(movable, size=n, replace=False):
        lifecycle.at[idx, "lifecycle_state"] = NEXT_STATE[lifecycle.at[idx, "lifecycle_state"]]
        lifecycle.at[idx, "state_changed_at"] = when

    n_rev = rng.binomial(len(lifecycle), 0.001)
    for idx in rng.choice(lifecycle.index, size=n_rev, replace=False):
        current = lifecycle.at[idx, "revision"]
        if current < "Z":
            lifecycle.at[idx, "revision"] = chr(ord(current) + 1)


def plm_export(lifecycle: pd.DataFrame) -> list[dict]:
    return [
        {
            "part_number": part_number(int(r.material_id)),
            "revision": r.revision,
            "lifecycle_state": r.lifecycle_state,
            "state_changed_at": r.state_changed_at.isoformat(timespec="seconds"),
            "owner_team": r.owner_team,
        }
        for r in lifecycle.itertuples(index=False)
    ]
