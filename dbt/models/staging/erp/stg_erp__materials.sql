-- Référentiel article ERP, état du dernier export reçu. Grain : un article (material_id).

with latest as (
    select max(_extract_date) as extract_date from {{ source('erp', 'erp_mara') }}
),

mara as (
    select m.*
    from {{ source('erp', 'erp_mara') }} as m
    join latest on m._extract_date = latest.extract_date
)

select
    {{ sap_material_id('matnr') }}                         as material_id,
    matnr,
    -- la désignation a été exportée sous MAKTX_LONG un jour : on prend celle qui existe
    {{ coalesce_existing_columns(source('erp', 'erp_mara'), ['maktx', 'maktx_long']) }} as material_description,
    mtart                                                  as material_type,
    matkl                                                  as material_group,
    meins                                                  as base_unit,
    upper(trim(mfrpn))                                     as mfr_part_number,
    {{ sap_date('ersda') }}                                as created_on,
    {{ sap_date('laeda') }}                                as changed_on,
    _extract_date                                          as extract_date
from mara
