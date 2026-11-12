# Modèle de données

## Schémas PostgreSQL

| Schéma | Rôle | Écrit par |
|---|---|---|
| `raw` | données reçues, valeurs en texte, une partition par journée (`_extract_date`) | ingestion |
| `staging` | typage, décodage des formats SAP, dernière version des enregistrements CRM | dbt |
| `intermediate` | rapprochement des identifiants, règles de gestion | dbt |
| `marts` | tables exposées (lues par l'API avec le rôle `api_reader`) | dbt |
| `meta` | `load_log`, `processed_files`, `extract_watermark` | ingestion |
| `app` | base applicative de l'API (étape 7, Alembic) | API |

## Identifiants d'un même produit

| Système | Identifiant | Exemple |
|---|---|---|
| ERP | `MATNR` (18 caractères) | `000000000010000123` |
| ERP / catalogue | référence constructeur (`MFRPN`) | `GX-48213-C` |
| PLM | `part_number` | `PN-10000123` |
| Catalogue | `sku` (absent sur ~5 % des fiches) | `SKU-10000123` |
| CRM | `ProductCode` | `10000123` |

`product_id` dans les marts = `MATNR` sans les zéros de tête.

## Règles du golden record (`dim_product`)

| Attribut | Source de référence | Repli |
|---|---|---|
| désignation, type, groupe, prix standard | ERP | - |
| cycle de vie, révision | PLM | `NOT_MANAGED` (services), `UNKNOWN` (produit physique absent du PLM) |
| nom et description commerciale | catalogue | désignation ERP (`description_source = 'erp'`) |
| famille | catalogue | groupe de marchandises ERP (seed `material_group_family`) |
| dernier prix de vente accepté | CRM | - |

Indicateurs de qualité portés par chaque fiche : `is_in_plm`, `is_in_catalog`,
`catalog_match_method`, `is_suspected_duplicate`, `has_valid_price`.

## Tables de faits

- `fct_quote_lines` : une ligne de devis, avec l'état PLM **le jour du devis**
  (`lifecycle_state_at_quote`) et le coût ERP connu ce jour-là (dernier export disponible).
- `fct_price_history` : une période de validité par prix standard (`valid_from`, `valid_to`),
  reconstruite à partir des exports quotidiens.
