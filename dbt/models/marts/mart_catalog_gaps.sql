-- Produits ERP mal couverts par le catalogue. Grain : un produit et un type de trou.

select
    product_id,
    matnr,
    mfr_part_number,
    product_name,
    family,
    material_type,
    is_suspected_duplicate,
    case
        when not is_in_catalog then 'missing_from_catalog'
        else 'missing_description'
    end as gap_type
from {{ ref('dim_product') }}
where not is_in_catalog
   or description_source <> 'catalog'
