"""Données de référence de la simulation : familles, sites, noms fictifs.

Tous les noms d'entreprises sont inventés (assemblage de syllabes) pour ne
jamais attribuer de faux devis à une organisation réelle.
"""

from __future__ import annotations

import numpy as np

# famille commerciale -> (groupe de marchandises SAP MATKL, préfixe constructeur, prix min, prix max)
FAMILIES: dict[str, tuple[str, str, float, float]] = {
    "Serveurs rack": ("SRV-RACK", "RK", 4_000, 45_000),
    "Serveurs lame": ("SRV-BLADE", "BL", 6_000, 60_000),
    "Stockage": ("STORAGE", "ST", 1_500, 120_000),
    "Réseau": ("NETWORK", "NW", 300, 25_000),
    "Processeurs": ("CPU", "CP", 400, 12_000),
    "Mémoire": ("MEMORY", "MM", 80, 3_000),
    "Accélérateurs": ("GPU", "GX", 2_000, 40_000),
    "Refroidissement": ("COOLING", "CL", 500, 80_000),
    "Logiciels": ("SOFTWARE", "SW", 100, 20_000),
    "Services": ("SERVICES", "SV", 500, 50_000),
}

# poids de chaque famille dans le référentiel article
FAMILY_WEIGHTS: dict[str, float] = {
    "Serveurs rack": 0.14,
    "Serveurs lame": 0.06,
    "Stockage": 0.10,
    "Réseau": 0.10,
    "Processeurs": 0.12,
    "Mémoire": 0.14,
    "Accélérateurs": 0.08,
    "Refroidissement": 0.08,
    "Logiciels": 0.10,
    "Services": 0.08,
}

# type d'article SAP (MTART) selon la famille :
# FERT = produit fini vendu, HALB = composant (nomenclature), DIEN = service / licence
COMPONENT_FAMILIES = {"Processeurs", "Mémoire", "Accélérateurs"}
SERVICE_FAMILIES = {"Logiciels", "Services"}
SYSTEM_FAMILIES = {"Serveurs rack", "Serveurs lame", "Stockage"}  # ont une nomenclature


def material_type(family: str) -> str:
    if family in COMPONENT_FAMILIES:
        return "HALB"
    if family in SERVICE_FAMILIES:
        return "DIEN"
    return "FERT"


# sites (WERKS) et magasins (LGORT)
PLANTS = ["FR01", "FR02", "DE01", "PL01"]
STORAGE_LOCATIONS = ["0001", "0002"]

PLM_STATES = ["PROTOTYPE", "ACTIVE", "END_OF_LIFE", "RETIRED"]
PLM_STATE_WEIGHTS = [0.08, 0.78, 0.10, 0.04]
PLM_TEAM_BY_FAMILY = {
    "Serveurs rack": "Compute",
    "Serveurs lame": "Compute",
    "Processeurs": "Compute",
    "Mémoire": "Compute",
    "Accélérateurs": "Compute",
    "Stockage": "Storage",
    "Réseau": "Network",
    "Refroidissement": "Cooling",
}

QUOTE_STATUSES = ["Draft", "Presented", "Accepted", "Rejected"]
COUNTRIES = ["FR", "DE", "ES", "IT", "PL", "NL", "BE", "CH", "GB", "SE"]
SEGMENTS = ["Recherche", "Industrie", "Défense", "Santé", "Finance", "Énergie", "Public"]

_SYLLABLES = [
    "al",
    "ber",
    "cor",
    "dra",
    "el",
    "fen",
    "gal",
    "hor",
    "ix",
    "jor",
    "kal",
    "lum",
    "mor",
    "nex",
    "or",
    "pra",
    "quil",
    "ron",
    "sol",
    "tar",
    "ul",
    "ver",
    "wen",
    "zan",
]
_SUFFIXES = ["Labs", "Systems", "Industries", "Research", "Analytics", "Group", "Tech", "Institute"]

_ADJECTIVES = ["Nova", "Titan", "Atlas", "Orion", "Vega", "Helix", "Quanta", "Polar", "Zenith"]
_NOUNS = {
    "Serveurs rack": "rack server",
    "Serveurs lame": "blade server",
    "Stockage": "storage array",
    "Réseau": "network switch",
    "Processeurs": "CPU",
    "Mémoire": "memory module",
    "Accélérateurs": "GPU accelerator",
    "Refroidissement": "liquid cooling unit",
    "Logiciels": "software license",
    "Services": "support service",
}


def fictitious_company(rng: np.random.Generator) -> str:
    """Nom d'entreprise inventé, par ex. 'Kalnexor Analytics'."""
    n = int(rng.integers(2, 4))
    stem = "".join(rng.choice(_SYLLABLES, size=n))
    return f"{stem.capitalize()} {rng.choice(_SUFFIXES)}"


def product_name(rng: np.random.Generator, family: str) -> str:
    """Désignation technique ERP, par ex. 'ORION GPU accelerator G4'."""
    return f"{rng.choice(_ADJECTIVES).upper()} {_NOUNS[family]} G{int(rng.integers(1, 9))}"
