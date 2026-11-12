"""Vérifie que chaque anomalie injectée est détectée par son test dbt (« tester les tests »).

    python scripts/check_anomalies.py            # après `dbt build`

Compare :
  - data/anomalies.json            : ce que la simulation a injecté (nombre par type) ;
  - dbt/target/manifest.json       : quel test surveille quelle anomalie (config.meta.anomaly) ;
  - dbt/target/run_results.json    : combien de lignes chaque test a remontées.

Code retour 1 si une anomalie n'est pas détectée, ou pas avec le bon nombre.
Les incidents de livraison (export manquant, colonne renommée, chute de volume)
seront couverts par Elementary à l'étape 4 : ils sont listés à part.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Fichier introuvable : {path.relative_to(ROOT)} (lancer la simulation et dbt build)")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    injected = load(ROOT / "data" / "anomalies.json")
    manifest = load(ROOT / "dbt" / "target" / "manifest.json")
    results = load(ROOT / "dbt" / "target" / "run_results.json")

    # test -> anomalie surveillée
    watched: dict[str, str] = {}
    for uid, node in manifest["nodes"].items():
        anomaly = node.get("config", {}).get("meta", {}).get("anomaly")
        if node.get("resource_type") == "test" and anomaly:
            watched[uid] = anomaly

    detected: dict[str, list[tuple[str, int]]] = {}
    for result in results["results"]:
        if result["unique_id"] in watched:
            failures = result.get("failures") or 0
            name = result["unique_id"].split(".")[2]
            detected.setdefault(watched[result["unique_id"]], []).append((name, failures))

    ok = True
    print(f"{'anomalie':<30} {'injectées':>9} {'détectées':>9}  test")
    for anomaly, expected in sorted(injected["counts"].items()):
        tests = detected.get(anomaly, [])
        found = max((n for _, n in tests), default=0)
        status = "OK " if found == expected else "KO "
        ok &= found == expected
        names = ", ".join(t for t, _ in tests) or "aucun test ne surveille cette anomalie"
        print(f"{status}{anomaly:<27} {expected:>9} {found:>9}  {names}")

    print("\nIncidents de livraison (surveillance Elementary, étape 4) :")
    for incident, day in sorted(injected.get("incidents", {}).items()):
        print(f"    {incident:<27} {day}")

    if ok:
        print("\nToutes les anomalies sont détectées.")
    else:
        print("\nAu moins une anomalie n'est pas détectée correctement.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
