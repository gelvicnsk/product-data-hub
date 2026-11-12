-- Golden record produit : une fiche unique par article, consolidée depuis les 4 sources.
-- Contrat activé (voir _marts.yml) : noms et types de colonnes garantis aux consommateurs.

select
    material_id                 as product_id,
    matnr,
    mfr_part_number,
    product_name,
    description,
    description_source,
    family,
    material_type,
    material_group,
    base_unit,
    is_configurable,
    lifecycle_state,
    revision,
    lifecycle_changed_at,
    standard_price,
    currency,
    has_valid_price,
    last_accepted_unit_price,
    last_accepted_at,
    plm_part_number,
    catalog_sku,
    catalog_match_method,
    is_in_plm,
    is_in_catalog,
    is_suspected_duplicate,
    erp_extract_date
from {{ ref('int_product_attributes') }}
