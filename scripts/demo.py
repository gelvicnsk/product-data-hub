"""Démonstration de l'API en 1 minute (pour un entretien ou une revue).

    .venv/bin/python scripts/demo.py

Obtient un jeton Keycloak pour alice (reader) puis pour bob (data_steward), et montre :
le golden record, un historique de prix, le résumé qualité, le contrôle des rôles,
puis le cycle d'une demande de correction.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def keycloak_url() -> str:
    return f"http://localhost:{os.getenv('KEYCLOAK_PORT', '8180')}/realms/product-hub"


def api_url() -> str:
    return f"http://localhost:{os.getenv('API_PORT', '8002')}"


def token(user: str, password: str) -> str:
    response = httpx.post(
        f"{keycloak_url()}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "product-hub-cli",
            "username": user,
            "password": password,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def show(title: str, response: httpx.Response) -> None:
    print(f"\n== {title}  [{response.status_code}]")
    body = response.json()
    print(json.dumps(body, indent=2, ensure_ascii=False, default=str)[:900])


def check_api(api: httpx.Client) -> bool:
    """Vérifie que c'est bien NOTRE API qui répond sur ce port (et pas un autre projet)."""
    try:
        title = api.get("/openapi.json").json()["info"]["title"]
    except (httpx.HTTPError, ValueError, KeyError):
        title = None
    if title != "Product Data Hub API":
        print(
            f"Le port de {api.base_url} ne répond pas avec l'API du Product Data Hub "
            f"(titre reçu : {title!r}). Vérifier API_PORT dans .env et `docker compose ps`."
        )
        return False
    return True


def main() -> int:
    # .env doit être lu AVANT de calculer les URL (ports configurables)
    load_env()
    alice = {"Authorization": f"Bearer {token('alice', os.environ['KC_DEMO_READER_PASSWORD'])}"}
    bob = {"Authorization": f"Bearer {token('bob', os.environ['KC_DEMO_STEWARD_PASSWORD'])}"}

    with httpx.Client(base_url=api_url(), timeout=10) as api:
        if not check_api(api):
            return 1
        show("Sans jeton", api.get("/products"))
        page = api.get("/products", headers=alice, params={"suspected_duplicate": True, "page_size": 2})
        show("Doublons probables (alice, reader)", page)
        product_id = page.json()["items"][0]["product_id"]
        show("Historique de prix", api.get("/products/10000090/price-history", headers=alice))
        show("Résumé qualité", api.get("/quality/summary", headers=alice))
        payload = {
            "product_id": product_id,
            "field": "description",
            "proposed_value": "Doublon de fiche : à fusionner",
            "comment": "démo",
        }
        refused = api.post("/corrections", headers=alice, json=payload)
        show("alice tente une correction (attendu : 403)", refused)
        created = api.post("/corrections", headers=bob, json=payload)
        show("bob crée la demande (data_steward)", created)
        show(
            "bob l'accepte",
            api.patch(f"/corrections/{created.json()['id']}", headers=bob, json={"status": "accepted"}),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
