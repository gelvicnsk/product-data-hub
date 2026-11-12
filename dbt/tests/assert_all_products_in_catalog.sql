-- Tout produit ERP doit avoir une fiche catalogue. Les doublons probables sont exclus :
-- ils relèvent d'un autre test (unicité de la référence constructeur).
{{ config(severity='warn', meta={'anomaly': 'missing_from_catalog'}) }}

select product_id, matnr, product_name
from {{ ref('mart_catalog_gaps') }}
where gap_type = 'missing_from_catalog'
  and not is_suspected_duplicate
