-- Nomenclatures (dernier export) : un composant d'un système. Grain : (parent, position).

with latest as (
    select {{ as_of_partition(source('erp', 'erp_stpo')) }} as extract_date
)

select
    {{ sap_material_id('stlnr') }}   as parent_material_id,
    posnr::integer                   as bom_position,
    {{ sap_material_id('idnrk') }}   as component_material_id,
    {{ sap_decimal('menge') }}       as component_quantity,
    meins                            as component_unit
from {{ source('erp', 'erp_stpo') }} as s
join latest on s._extract_date = latest.extract_date
