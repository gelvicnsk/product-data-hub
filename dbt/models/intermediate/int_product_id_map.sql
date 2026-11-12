-- Rapprochement des identifiants : pour chaque article ERP, son code PLM et sa fiche catalogue.
-- Grain : un article ERP (material_id).
--
-- Règles de rapprochement avec le catalogue, dans l'ordre :
--   1. par SKU            : SKU-<material_id>      (cas normal)
--   2. par référence constructeur (MFRPN), seulement pour les fiches sans SKU
-- Un article non rapproché reste visible (is_in_catalog = false) au lieu d'être perdu.

with erp as (
    select material_id, matnr, mfr_part_number
    from {{ ref('stg_erp__materials') }}
),

plm as (
    select material_id, part_number
    from {{ ref('stg_plm__lifecycle') }}
    where is_latest_extract
),

catalog as (
    select sku, sku_material_id, mfr_part_number
    from {{ ref('stg_catalog__products') }}
),

by_sku as (
    select erp.material_id, catalog.sku, catalog.mfr_part_number as catalog_mfr_part_number
    from erp
    join catalog on catalog.sku_material_id = erp.material_id
),

by_mfr_part_number as (
    select erp.material_id, catalog.sku, catalog.mfr_part_number as catalog_mfr_part_number
    from erp
    join catalog
        on catalog.sku is null
        and catalog.mfr_part_number = erp.mfr_part_number
    where erp.material_id not in (select material_id from by_sku)
),

catalog_match as (
    select *, 'sku' as match_method from by_sku
    union all
    select *, 'mfr_part_number' as match_method from by_mfr_part_number
),

shared_mfr_part_numbers as (
    -- plusieurs codes ERP pour une même référence constructeur : doublon probable
    select mfr_part_number
    from erp
    group by mfr_part_number
    having count(*) > 1
)

select
    erp.material_id,
    erp.matnr,
    erp.mfr_part_number,
    plm.part_number                                     as plm_part_number,
    catalog_match.sku                                   as catalog_sku,
    catalog_match.catalog_mfr_part_number,
    catalog_match.match_method                          as catalog_match_method,
    plm.material_id is not null                         as is_in_plm,
    catalog_match.material_id is not null               as is_in_catalog,
    shared.mfr_part_number is not null                  as is_suspected_duplicate
from erp
left join plm on plm.material_id = erp.material_id
left join catalog_match on catalog_match.material_id = erp.material_id
left join shared_mfr_part_numbers as shared on shared.mfr_part_number = erp.mfr_part_number
