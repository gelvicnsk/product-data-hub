#!/usr/bin/env bash
# Point d'entrée de l'image pipeline.
#   run_pipeline.sh simulate   génère les 30 journées des sources dans /data
#   run_pipeline.sh init       ingestion de toutes les journées + dbt build + contrôle
#   run_pipeline.sh daily      même chose, idempotent (CronJob quotidien)
set -euo pipefail

mode="${1:-daily}"
data_dir="$(dirname "${LANDING_DIR:-/data/landing}")"

wait_for_crm() {
  for _ in $(seq 1 60); do
    python -c "import urllib.request; urllib.request.urlopen('${CRM_API_URL}/health')" 2>/dev/null && return 0
    echo "en attente du faux CRM (${CRM_API_URL})..."; sleep 5
  done
  echo "faux CRM injoignable" >&2; return 1
}

case "$mode" in
  simulate)
    python -m sources.simulate_days
    ;;
  init|daily)
    wait_for_crm
    python -m ingestion.run --all
    cd dbt
    dbt build --profiles-dir . --target-path "${data_dir}/dbt-target"
    cd ..
    # le script lit dbt/target : on lui indique où dbt a écrit ses résultats
    DBT_TARGET_DIR="${data_dir}/dbt-target" ANOMALIES_FILE="${data_dir}/anomalies.json" \
      python scripts/check_anomalies.py
    ;;
  *)
    echo "mode inconnu : $mode (simulate | init | daily)" >&2; exit 2 ;;
esac
