"""Requêtes d'analyse DuckDB sur l'export du Product Data Hub (make analytics d'abord).

    python -m analytics.demo_queries          # ou : make duckdb-demo

Montre ce que DuckDB apporte pour l'analyse locale : lecture directe de Parquet,
QUALIFY, PIVOT, fonctions de fenêtre, le tout sans serveur.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

ANALYTICS_DIR = Path(os.getenv("ANALYTICS_DIR", "data/analytics"))

QUERIES = {
    "1. Marge des devis acceptés par famille (base DuckDB)": """
        SELECT family AS famille,
               accepted_quote_count AS devis,
               revenue AS ca_eur,
               margin AS marge_eur,
               margin_pct AS "marge_%",
               rank() OVER (ORDER BY margin DESC) AS rang
        FROM mart_margin_by_family
        ORDER BY rang
    """,
    "2. Produits aux prix les plus instables (Parquet lu directement + QUALIFY)": """
        SELECT h.product_id,
               p.product_name AS produit,
               count(*) - 1 AS changements,
               min(h.standard_price) AS prix_min,
               max(h.standard_price) AS prix_max,
               round(100 * (max(h.standard_price) / min(h.standard_price) - 1), 1)::DECIMAL(6, 1) AS "écart_%"
        FROM read_parquet('{dir}/fct_price_history.parquet') AS h
        JOIN dim_product AS p USING (product_id)
        WHERE h.standard_price > 0
        GROUP BY h.product_id, p.product_name
        QUALIFY row_number() OVER (ORDER BY changements DESC, "écart_%" DESC) <= 8
    """,
    "3. Chiffre d'affaires des devis par famille et par statut (PIVOT)": """
        PIVOT (
            SELECT coalesce(p.family, 'Non rapproché') AS famille, q.quote_status, q.line_amount
            FROM fct_quote_lines AS q
            LEFT JOIN dim_product AS p ON p.product_id = q.material_id
        )
        ON quote_status IN ('Draft', 'Presented', 'Accepted', 'Rejected')
        USING round(sum(line_amount) / 1000)::INTEGER AS k_eur
        ORDER BY famille
    """,
    "4. Historique SCD2 d'un produit (snapshot dbt)": """
        SELECT material_id, plant, standard_price,
               dbt_valid_from::DATE AS valide_du,
               dbt_valid_to::DATE AS valide_au
        FROM snap_material_price
        WHERE material_id = (SELECT material_id FROM snap_material_price
                             GROUP BY material_id ORDER BY count(*) DESC, material_id LIMIT 1)
        ORDER BY dbt_valid_from
    """,
}


def main() -> None:
    db = duckdb.connect(str(ANALYTICS_DIR / "hub.duckdb"), read_only=True)
    for title, sql in QUERIES.items():
        print(f"\n{title}")
        db.sql(sql.format(dir=ANALYTICS_DIR)).show(max_width=140)


if __name__ == "__main__":
    main()
