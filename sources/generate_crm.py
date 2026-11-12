"""Simulation du CRM (type Salesforce) : comptes, devis, lignes de devis.

Le CRM garde chaque version d'un enregistrement (une version par modification,
datée par LastModifiedDate). Le faux CRM (sources/mock_crm) s'en sert pour
répondre « comme à une date donnée » et pour filtrer sur LastModifiedDate,
ce qui permet de simuler une extraction incrémentale jour après jour.

Les noms de champs suivent les conventions Salesforce (Id, AccountId,
CreatedDate, LastModifiedDate…) ; ProductCode = identifiant article sans les
zéros SAP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from sources import reference as ref

ENTITIES = ("accounts", "quotes", "quote_lines")


def sf_id(prefix: str, n: int) -> str:
    """Identifiant au format Salesforce : 18 caractères, préfixe d'objet sur 3."""
    return f"{prefix}{n:012d}AAA"


def sf_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


@dataclass
class CrmSimulator:
    rng: np.random.Generator
    records: dict[str, list[dict]] = field(default_factory=lambda: {e: [] for e in ENTITIES})
    _open_quotes: dict[str, dict] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=lambda: {e: 0 for e in ENTITIES})
    _account_ids: list[str] = field(default_factory=list)

    def _next_id(self, entity: str, prefix: str) -> str:
        self._counters[entity] += 1
        return sf_id(prefix, self._counters[entity])

    def _timestamp(self, day: date) -> datetime:
        return datetime.combine(
            day,
            time(int(self.rng.integers(7, 20)), int(self.rng.integers(0, 60)), int(self.rng.integers(0, 60))),
        )

    # --- comptes ------------------------------------------------------------
    def create_accounts(self, n: int, day: date) -> None:
        names: set[str] = set()
        while len(names) < n:
            names.add(ref.fictitious_company(self.rng))
        for name in sorted(names):
            created = datetime.combine(day - timedelta(days=int(self.rng.integers(10, 1500))), time(10, 0))
            account_id = self._next_id("accounts", "001")
            self._account_ids.append(account_id)
            self.records["accounts"].append(
                {
                    "Id": account_id,
                    "Name": name,
                    "BillingCountry": str(self.rng.choice(ref.COUNTRIES)),
                    "Industry": str(self.rng.choice(ref.SEGMENTS)),
                    "CreatedDate": sf_datetime(created),
                    "LastModifiedDate": sf_datetime(created),
                }
            )

    def touch_accounts(self, day: date, rate: float = 0.01) -> None:
        """Quelques comptes modifiés dans la journée (changement de segment)."""
        latest = {a["Id"]: a for a in self.records["accounts"]}
        n = self.rng.binomial(len(latest), rate)
        for account_id in self.rng.choice(sorted(latest), size=n, replace=False):
            version = dict(latest[account_id])
            version["Industry"] = str(self.rng.choice(ref.SEGMENTS))
            version["LastModifiedDate"] = sf_datetime(self._timestamp(day))
            self.records["accounts"].append(version)

    # --- devis --------------------------------------------------------------
    def create_quote(self, day: date, products: list[tuple[str, float]]) -> str:
        """Crée un devis et ses lignes. products = [(ProductCode, prix catalogue)]."""
        created = self._timestamp(day)
        quote_id = self._next_id("quotes", "0Q0")
        quote = {
            "Id": quote_id,
            "Name": f"Q-{self._counters['quotes']:06d}",
            "AccountId": str(self.rng.choice(self._account_ids)),
            "Status": "Draft",
            "ExpirationDate": (day + timedelta(days=30)).isoformat(),
            "CurrencyIsoCode": "EUR",
            "CreatedDate": sf_datetime(created),
            "LastModifiedDate": sf_datetime(created),
        }
        self.records["quotes"].append(quote)
        self._open_quotes[quote_id] = quote
        for code, list_price in products:
            discount = float(self.rng.choice([0, 0, 5, 10, 15, 20]))
            self.records["quote_lines"].append(
                {
                    "Id": self._next_id("quote_lines", "0QL"),
                    "QuoteId": quote_id,
                    "ProductCode": code,
                    "Quantity": int(self.rng.choice([1, 1, 2, 4, 8, 16])),
                    "ListPrice": round(list_price, 2),
                    "Discount": discount,
                    "UnitPrice": round(list_price * (1 - discount / 100), 2),
                    "CreatedDate": sf_datetime(created),
                    "LastModifiedDate": sf_datetime(created),
                }
            )
        return quote_id

    def advance_quotes(self, day: date, rate: float = 0.15) -> None:
        """Draft -> Presented -> Accepted ou Rejected : une nouvelle version par changement."""
        for quote_id in sorted(self._open_quotes):
            if self.rng.random() > rate:
                continue
            version = dict(self._open_quotes[quote_id])
            if version["Status"] == "Draft":
                version["Status"] = "Presented"
            else:
                version["Status"] = "Accepted" if self.rng.random() < 0.5 else "Rejected"
            version["LastModifiedDate"] = sf_datetime(self._timestamp(day))
            self.records["quotes"].append(version)
            if version["Status"] in ("Accepted", "Rejected"):
                del self._open_quotes[quote_id]
            else:
                self._open_quotes[quote_id] = version

    # --- persistance (la « base » du faux CRM) --------------------------------
    def write(self, crm_db_dir: Path) -> None:
        crm_db_dir.mkdir(parents=True, exist_ok=True)
        for entity, rows in self.records.items():
            path = crm_db_dir / f"{entity}.jsonl"
            with path.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_crm_db(crm_db_dir: Path) -> dict[str, pd.DataFrame]:
    """Relit les versions stockées (utilisé par le faux CRM et les tests)."""
    out = {}
    for entity in ENTITIES:
        path = crm_db_dir / f"{entity}.jsonl"
        out[entity] = pd.read_json(path, lines=True, dtype=False) if path.exists() else pd.DataFrame()
    return out
