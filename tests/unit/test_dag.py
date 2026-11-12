"""Le DAG Airflow se charge-t-il, avec la bonne structure ? (ignoré si Airflow est absent)"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("airflow", reason="Airflow n'est pas installé dans cet environnement")

DAGS = Path(__file__).resolve().parents[2] / "dags"


@pytest.fixture(scope="module")
def dag():
    from airflow.models.dagbag import DagBag

    bag = DagBag(dag_folder=str(DAGS))
    assert bag.import_errors == {}
    return bag.dags["product_hub_daily"]


def test_daily_catchup_in_order(dag):
    assert dag.catchup is True
    assert dag.max_active_runs == 1  # les journées sont rejouées une par une


def test_task_order(dag):
    assert dag.get_task("ingest").downstream_task_ids == {"dbt_snapshot"}
    assert dag.get_task("dbt_snapshot").downstream_task_ids == {"dbt_build"}
    assert dag.get_task("dbt_build").downstream_task_ids == {"quality_gate"}


def test_each_day_is_processed_as_of_its_date(dag):
    assert "--date {{ ds }}" in dag.get_task("ingest").bash_command
    assert "as_of_date: {{ ds }}" in dag.get_task("dbt_snapshot").bash_command
    assert "as_of_date: {{ ds }}" in dag.get_task("dbt_build").bash_command
