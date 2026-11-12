{#
  Historique (SCD type 2) de l'état PLM : une version par changement d'état
  ou de révision. Même principe que snap_material_price (date métier).
#}
{% snapshot snap_product_lifecycle %}

{{ config(
    schema='snapshots',
    unique_key='part_number',
    strategy='check',
    check_cols=['lifecycle_state', 'revision'],
    updated_at='observed_at',
) }}

select
    part_number,
    nullif(replace(part_number, 'PN-', ''), '')::bigint as material_id,
    revision,
    lifecycle_state,
    state_changed_at::timestamp                         as state_changed_at,
    _extract_date::timestamp                            as observed_at
from {{ source('plm', 'plm_lifecycle') }}
where _extract_date = {{ as_of_partition(source('plm', 'plm_lifecycle')) }}

{% endsnapshot %}
