-- Un prix standard nul ou négatif fausse les marges : on liste les produits concernés.
{{ config(severity='warn', meta={'anomaly': 'non_positive_price'}) }}

select product_id, matnr, standard_price
from {{ ref('dim_product') }}
where standard_price <= 0
