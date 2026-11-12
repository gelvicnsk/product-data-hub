# Anomalies injectées

Les anomalies sont injectées volontairement par `sources/simulate_days.py`. À chaque
génération, leur liste exacte (nombre et identifiants) est écrite dans
`data/anomalies.json`. Chaque anomalie doit être détectée par au moins un test :
c'est ainsi qu'on vérifie que les tests fonctionnent (« tester les tests »).

## Anomalies de données

| Anomalie | Nombre (défaut) | Source | Détection prévue |
|---|---|---|---|
| `unknown_product_in_quotes` : article de devis absent de l'ERP | 6 | CRM | test de relation dbt (étape 3) |
| `eol_product_in_quotes` : produit en fin de vie toujours vendu | 8 | PLM + CRM | mart dédié + test en `warn` (étape 3) |
| `missing_catalog_description` : description commerciale vide | 25 | Catalogue | test de complétude (étape 3) |
| `missing_from_catalog` : article ERP absent du catalogue | 40 | Catalogue | `mart_catalog_gaps` (étape 3) |
| `duplicate_material` : même produit sous deux codes ERP | 4 | ERP | unicité de la référence constructeur (étape 3) |
| `non_positive_price` : prix standard nul ou négatif | 5 | ERP | test d'expression (étape 3) |

## Incidents de livraison

| Incident | Jour (défaut) | Effet | Détection prévue |
|---|---|---|---|
| `erp_missing_export` | 2026-10-18 | aucun fichier ERP ce jour-là ; `meta.load_log` en `skipped` | Elementary `freshness_anomalies` (étape 4) |
| `quote_volume_drop` | 2026-10-24 | environ 3 devis au lieu de 25 | Elementary `volume_anomalies` (étape 4) |
| `erp_renamed_column` | 2026-10-27 | `MAKTX` devient `MAKTX_LONG` dans MARA ; la colonne est ajoutée à raw | Elementary `schema_changes` (étape 4) |

Les volumes et les jours se règlent dans `sources/config.py`.
