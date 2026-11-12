{{ config(indexes=[{"columns": ["material_id", "extract_date"]}]) }}

-- Prix standard ERP, une ligne par article et par journée d'export.
-- On garde toutes les journées : c'est la base de l'historique des prix.

select
    {{ sap_material_id('matnr') }}           as material_id,
    bwkey                                    as plant,
    {{ sap_decimal('stprs') }}               as standard_price,
    nullif(peinh, '')::integer               as price_unit,
    waers                                    as currency,
    _extract_date                            as extract_date,
    _extract_date = {{ as_of_partition(source('erp', 'erp_mbew')) }} as is_latest_extract
from {{ source('erp', 'erp_mbew') }}
{%- if var('as_of_date', none) %}
where _extract_date <= '{{ var("as_of_date") }}'::date
{%- endif %}
