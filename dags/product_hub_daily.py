"""DAG quotidien du Product Data Hub (Airflow 3).

    ingest  ->  dbt_snapshot  ->  dbt_build  ->  quality_gate

Chaque run traite UNE journée, « comme à cette date » ({{ ds }}) :
  - ingest        charge les fichiers du jour et les modifications CRM jusqu'au soir ;
  - dbt_snapshot  enregistre les changements de prix et d'état PLM (SCD type 2) ;
  - dbt_build     reconstruit staging -> marts au {{ ds }} et lance les tests,
                  dont les tests d'anomalies Elementary (fenêtre jugée au lendemain matin) ;
  - quality_gate  le dernier jour seulement : chaque anomalie injectée est-elle détectée ?
                  puis rapport Elementary.

Rattrapage (catchup) : la période simulée est dans le passé ; à l'activation du DAG,
Airflow crée un run par journée et les exécute DANS L'ORDRE (max_active_runs=1), ce qui
rejoue l'historique jour par jour : watermark CRM, snapshots et Elementary voient le temps
passer comme en production. Chaque tâche est idempotente : un run relancé ne duplique rien.

Le code du projet et les outils du pipeline (dbt, ingestion) tournent dans un
environnement Python séparé de celui d'Airflow (voir infra/airflow/Dockerfile).
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = os.getenv("PROJECT_DIR", "/opt/product-hub")
PIPELINE_BIN = os.getenv("PIPELINE_BIN", "/opt/airflow/pipeline-venv/bin")

SIM_START = date.fromisoformat(os.getenv("SIM_START_DATE", "2026-10-01"))
SIM_DAYS = int(os.getenv("SIM_DAYS", "30"))
SIM_END = SIM_START + timedelta(days=SIM_DAYS - 1)

DBT = f"cd {PROJECT_DIR}/dbt && {PIPELINE_BIN}/dbt"
AS_OF = "--vars '{as_of_date: {{ ds }}}'"

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="product_hub_daily",
    description="Ingestion, snapshots, dbt et contrôle qualité d'une journée",
    schedule="@daily",
    start_date=pendulum.datetime(SIM_START.year, SIM_START.month, SIM_START.day, tz="UTC"),
    end_date=pendulum.datetime(SIM_END.year, SIM_END.month, SIM_END.day, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args=default_args,
    tags=["product-hub", "batch"],
    doc_md=__doc__,
) as dag:
    ingest = BashOperator(
        task_id="ingest",
        bash_command=f"cd {PROJECT_DIR} && {PIPELINE_BIN}/python -m ingestion.run --date {{{{ ds }}}}",
        doc_md="Charge la journée dans raw. Code retour 1 si un chargement échoue : Airflow relance.",
    )

    dbt_snapshot = BashOperator(
        task_id="dbt_snapshot",
        bash_command=f"{DBT} snapshot --profiles-dir . {AS_OF}",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT} build --profiles-dir . --exclude resource_type:snapshot {AS_OF}",
        # Elementary juge les anomalies « au lendemain matin » de la journée traitée
        env={"PIPELINE_RUN_AT": "{{ macros.ds_add(ds, 1) }}T06:00:00"},
        append_env=True,
    )

    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command=(
            f'if [ "{{{{ ds }}}}" != "{SIM_END.isoformat()}" ]; then '
            'echo "Contrôle global réservé à la dernière journée simulée"; exit 0; fi; '
            f"cd {PROJECT_DIR} && {PIPELINE_BIN}/python scripts/check_anomalies.py && "
            f"{PIPELINE_BIN}/edr report --profiles-dir dbt --project-dir dbt "
            "--file-path data/edr/report.html --open-browser false"
        ),
    )

    ingest >> dbt_snapshot >> dbt_build >> quality_gate
