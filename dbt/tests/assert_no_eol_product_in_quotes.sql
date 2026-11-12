-- Aucun devis ne devrait porter sur un produit déjà en fin de vie le jour du devis.
-- En warn : c'est une alerte métier pour l'équipe commerciale, pas une panne.
{{ config(severity='warn', meta={'anomaly': 'eol_product_in_quotes'}) }}

select quote_line_id, quote_number, product_id, lifecycle_state_at_quote, quote_date
from {{ ref('mart_eol_products_in_quotes') }}
