-- Fiches du catalogue produit (dernier export). Grain : une fiche.
-- Environ 5 % des fiches n'ont pas de SKU : elles seront rapprochées par la référence constructeur.

with latest as (
    select {{ as_of_partition(source('catalog', 'catalog_products')) }} as extract_date
)

select
    nullif(sku, '')                                     as sku,
    nullif(replace(sku, 'SKU-', ''), '')::bigint        as sku_material_id,
    upper(trim(mfr_part_number))                        as mfr_part_number,
    family,
    commercial_name,
    nullif(trim(description), '')                       as description,
    configurable = 'yes'                                as is_configurable
from {{ source('catalog', 'catalog_products') }} as c
join latest on c._extract_date = latest.extract_date
