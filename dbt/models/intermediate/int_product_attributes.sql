-- Attributs consolidés de chaque produit, selon une source de référence par attribut :
--
-- | attribut                         | référence  | repli                         |
-- |----------------------------------|------------|-------------------------------|
-- | désignation, type, prix standard | ERP        | -                             |
-- | cycle de vie, révision           | PLM        | NOT_MANAGED pour les services |
-- | nom et description commerciale   | catalogue  | désignation ERP               |
-- | famille                          | catalogue  | groupe de marchandises ERP    |
-- | dernier prix de vente constaté   | CRM        | -                             |

with ids as (
    select * from {{ ref('int_product_id_map') }}
),

erp as (
    select * from {{ ref('stg_erp__materials') }}
),

price as (
    select material_id, standard_price, currency, extract_date
    from {{ ref('stg_erp__prices') }}
    where is_latest_extract
),

plm as (
    select material_id, revision, lifecycle_state, state_changed_at
    from {{ ref('stg_plm__lifecycle') }}
    where is_latest_extract
),

catalog as (
    select * from {{ ref('stg_catalog__products') }}
),

group_family as (
    select material_group, family from {{ ref('material_group_family') }}
),

last_sale as (
    select distinct on (lines.material_id)
        lines.material_id,
        lines.unit_price as last_accepted_unit_price,
        quotes.last_modified_at as last_accepted_at
    from {{ ref('stg_crm__quote_lines') }} as lines
    join {{ ref('stg_crm__quotes') }} as quotes on quotes.quote_id = lines.quote_id
    where quotes.quote_status = 'Accepted'
    order by lines.material_id, quotes.last_modified_at desc
)

select
    ids.material_id,
    ids.matnr,
    ids.mfr_part_number,
    coalesce(catalog.commercial_name, erp.material_description)          as product_name,
    coalesce(catalog.description, erp.material_description)              as description,
    case when catalog.description is not null then 'catalog' else 'erp' end as description_source,
    coalesce(catalog.family, group_family.family)                        as family,
    erp.material_type,
    erp.material_group,
    erp.base_unit,
    catalog.is_configurable,
    case
        when plm.lifecycle_state is not null then plm.lifecycle_state
        when erp.material_type = 'DIEN' then 'NOT_MANAGED'
        else 'UNKNOWN'
    end                                                                  as lifecycle_state,
    plm.revision,
    plm.state_changed_at                                                 as lifecycle_changed_at,
    price.standard_price,
    price.currency,
    coalesce(price.standard_price > 0, false)                            as has_valid_price,
    last_sale.last_accepted_unit_price,
    last_sale.last_accepted_at,
    ids.plm_part_number,
    ids.catalog_sku,
    ids.catalog_match_method,
    ids.is_in_plm,
    ids.is_in_catalog,
    ids.is_suspected_duplicate,
    erp.extract_date                                                     as erp_extract_date
from ids
join erp on erp.material_id = ids.material_id
left join price on price.material_id = ids.material_id
left join plm on plm.material_id = ids.material_id
left join catalog
    on (ids.catalog_match_method = 'sku' and catalog.sku = ids.catalog_sku)
    or (ids.catalog_match_method = 'mfr_part_number'
        and catalog.sku is null
        and catalog.mfr_part_number = ids.catalog_mfr_part_number)
left join group_family on group_family.material_group = erp.material_group
left join last_sale on last_sale.material_id = ids.material_id
