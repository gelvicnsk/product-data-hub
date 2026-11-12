{#
  Historique (SCD type 2) du prix standard ERP par article et par site.

  Stratégie « check » : une nouvelle version est créée quand le prix change.
  updated_at = journée d'export observée : dbt_valid_from porte donc la date MÉTIER
  du changement, pas l'heure à laquelle dbt a tourné. C'est ce qui permet de rejouer
  l'historique jour par jour (Airflow, rattrapage) et d'obtenir les bonnes dates.
#}
{% snapshot snap_material_price %}

{{ config(
    schema='snapshots',
    unique_key='price_key',
    strategy='check',
    check_cols=['standard_price'],
    updated_at='observed_at',
) }}

select
    {{ sap_material_id('matnr') }} || '-' || bwkey     as price_key,
    {{ sap_material_id('matnr') }}                     as material_id,
    bwkey                                              as plant,
    {{ sap_decimal('stprs') }}                         as standard_price,
    waers                                              as currency,
    _extract_date::timestamp                           as observed_at
from {{ source('erp', 'erp_mbew') }}
where _extract_date = {{ as_of_partition(source('erp', 'erp_mbew')) }}

{% endsnapshot %}
