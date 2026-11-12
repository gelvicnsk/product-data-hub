{{ config(indexes=[{"columns": ["material_id", "extract_date"]}]) }}

-- Cycle de vie PLM, une ligne par produit et par journée d'export.
-- Gardé jour par jour pour connaître l'état d'un produit à une date donnée
-- (par exemple : était-il déjà en fin de vie le jour du devis ?).

select
    nullif(replace(part_number, 'PN-', ''), '')::bigint as material_id,
    part_number,
    revision,
    lifecycle_state,
    state_changed_at::timestamp                         as state_changed_at,
    owner_team,
    _extract_date                                       as extract_date,
    _extract_date = {{ as_of_partition(source('plm', 'plm_lifecycle')) }} as is_latest_extract
from {{ source('plm', 'plm_lifecycle') }}
{%- if var('as_of_date', none) %}
where _extract_date <= '{{ var("as_of_date") }}'::date
{%- endif %}
