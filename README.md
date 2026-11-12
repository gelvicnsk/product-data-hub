# Product Data Hub

Projet personnel de Data Engineering : construire un **référentiel produit unifié**
(*golden record*) à partir de quatre systèmes d'entreprise simulés : ERP type SAP,
CRM type Salesforce, PLM et catalogue produit.

> Toutes les données sont **synthétiques** et les noms d'entreprises sont fictifs.
> Le projet n'a aucun lien avec une entreprise réelle.

## État d'avancement

| Étape | Contenu | État |
|---|---|---|
| 1. Socle | Docker, PostgreSQL, générateurs de données, faux CRM | fait |
| 2. Ingestion batch | chargement idempotent, registre de fichiers, watermark CRM | fait |
| 3. dbt | staging, rapprochement, golden record, tests, contrôle des anomalies | fait |
| 4. Elementary | observabilité : volume, fraîcheur, changement de schéma, rapport | fait |
| 5. Historisation | snapshots SCD type 2 | à venir |
| 6. Airflow | DAG quotidien | à venir |
| 7. API | FastAPI, SQLAlchemy 2.x, Alembic, Keycloak | à venir |
| 8. Kubernetes | déploiement avec kind + kustomize | à venir |

## Démarrage rapide (WSL / Linux)

Prérequis : Docker, Python 3.11+, `make`, `openssl`.

```bash
make env            # crée .env avec des mots de passe aléatoires
make install        # environnement virtuel .venv
make generate       # simule 30 journées des 4 sources -> data/landing, data/crm_db
make up             # PostgreSQL (port 5433) + faux CRM (port 8010)
make ingest         # charge toutes les journées dans le schéma raw
make test-db        # crée la base de test (une seule fois)
make test           # tests unitaires + intégration
make dbt-deps       # paquets dbt (une seule fois)
make dbt-build      # modèles + tests dbt
make check-anomalies  # chaque anomalie et chaque incident sont-ils détectés ?
make edr-report     # rapport d'observabilité Elementary -> data/edr/report.html
```

`make pipeline` enchaîne simulation, ingestion, dbt et contrôle des anomalies.

Ensuite : `make psql`, puis par exemple
`SELECT * FROM meta.load_log ORDER BY load_id DESC LIMIT 10;`

## Les sources simulées

| Source | Format | Mode d'extraction | Tables raw |
|---|---|---|---|
| ERP (type SAP) | CSV `;`, décimale `,`, dates `AAAAMMJJ`, MATNR sur 18 caractères | fichiers déposés chaque nuit, registre `meta.processed_files` | `erp_mara`, `erp_mbew`, `erp_mard`, `erp_stpo` |
| PLM | JSON | export complet quotidien | `plm_lifecycle` |
| Catalogue | CSV `,` | export complet quotidien | `catalog_products` |
| CRM (type Salesforce) | API REST paginée (`nextRecordsUrl`) | incrémental par watermark sur `LastModifiedDate` | `crm_accounts`, `crm_quotes`, `crm_quote_lines` |

Les anomalies injectées volontairement sont décrites dans [docs/anomalies.md](docs/anomalies.md)
et listées à chaque génération dans `data/anomalies.json`.

## Choix techniques de l'ingestion

- **raw garde les valeurs telles que reçues**, tout en texte. Seuls les noms de colonnes
  sont normalisés en snake_case. Le typage se fait dans dbt.
- **Idempotence** : une journée rechargée remplace sa partition (`_extract_date`) ;
  les versions CRM sont chargées en *upsert* sur `(id, last_modified_date)`.
  Suppression et insertion se font dans la même transaction.
- **Watermark à borne incluse** : les enregistrements à la frontière sont relus puis
  absorbés par l'upsert. On ne perd rien et on ne duplique rien. Le watermark avance
  dans la même transaction que les données : après un échec, on reprend au même point.
- **Évolution de schéma** : une colonne nouvelle est ajoutée à la table au lieu de faire
  échouer le chargement.
- **Traçabilité** : chaque chargement est journalisé dans `meta.load_log`, y compris
  les journées sans fichier (`skipped`).

## Transformation (dbt)

```
raw (texte, une partition par jour)
 └─ staging        typage, conventions SAP décodées, dernière version CRM
     └─ intermediate   rapprochement des identifiants, attributs consolidés
         └─ marts          dim_product (golden record), dim_account, fct_quote_lines,
                           fct_price_history, mart_eol_products_in_quotes,
                           mart_catalog_gaps, mart_margin_by_family
```

- **Rapprochement** : catalogue par SKU, puis par référence constructeur pour les fiches
  sans SKU ; un article non rapproché reste visible (`is_in_catalog = false`).
- **Une source de référence par attribut** : ERP pour le prix, PLM pour le cycle de vie,
  catalogue pour la description (repli sur l'ERP). Détail dans [docs/data_model.md](docs/data_model.md).
- **« À la date du devis »** : l'état PLM et le coût ERP sont pris dans l'export du jour du
  devis, pas dans l'état d'aujourd'hui.
- **Contrat** sur `dim_product` : noms, types et clé primaire garantis à l'API.
- **Sévérités** : les anomalies métier sont en `warn` (le pipeline continue), les tests
  d'intégrité en `error` (le pipeline s'arrête).
- **Tester les tests** : `scripts/check_anomalies.py` compare les échecs de chaque test aux
  anomalies injectées (`data/anomalies.json`) ; un test de référence recalcule le chiffre
  d'affaires depuis le CRM et casse si une jointure perd ou duplique des lignes.

## Observabilité (Elementary)

Les tests dbt vérifient des règles écrites à la main. Elementary surveille en plus
l'évolution des données dans le temps et détecte ce qu'aucune règle ne prévoyait :

| Test Elementary | Table | Incident simulé détecté |
|---|---|---|
| `volume_anomalies` | `raw.erp_mara` | jour sans export ERP (0 ligne le 18/10) |
| `freshness_anomalies` | `raw.erp_mara` | 48 h sans mise à jour après le 17/10 |
| `schema_changes_from_baseline` | `raw.erp_mara` | colonne SAP renommée (`maktx_long` ajoutée le 27/10) |
| `volume_anomalies` | `staging.stg_crm__quotes` | 2 devis le 24/10 au lieu de ~25 |

- **Temps simulé** : Elementary juge « les derniers jours » par rapport à l'heure du run.
  La variable `custom_run_started_at` (dbt_project.yml, surchargeable par `PIPELINE_RUN_AT`)
  place ce « maintenant » au lendemain de la dernière journée simulée.
- **Fenêtres** : 30 jours d'historique, 14 derniers jours examinés, seuil de 3 écarts types.
- **Réglage justifié** : pour les devis, les jours examinés sont exclus de l'apprentissage ;
  sinon la chute gonfle elle-même l'écart type (z = -2,99, sous le seuil). Pas pour l'ERP :
  son volume est constant, l'écart type d'apprentissage vaudrait 0 et aucun score ne serait
  calculable.

## Structure

```
sources/      simulation des systèmes source + faux CRM (FastAPI)
ingestion/    extraction et chargement dans raw
dbt/          transformation (étape 3)
dags/         orchestration Airflow (étape 6)
api/          API d'exposition (étape 7)
k8s/          déploiement Kubernetes (étape 8)
infra/        initialisation PostgreSQL, images
tests/        unit/ (sans base) et integration/ (base de test dédiée)
```
