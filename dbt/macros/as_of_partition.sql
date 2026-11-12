{#
  Partition (journée d'export) à utiliser « à la date » var('as_of_date').
  Sans la variable : la dernière journée chargée.
  Avec : la dernière journée chargée à cette date ou avant (un jour sans export
  reprend donc la veille). Sert au staging et aux snapshots : Airflow traite chaque
  journée « comme à cette date », y compris lors d'un rattrapage (catchup) :
      dbt build    --vars '{as_of_date: 2026-10-05}'
      dbt snapshot --vars '{as_of_date: 2026-10-05}'
#}
{% macro as_of_partition(relation) -%}
    (
        select max(_extract_date)
        from {{ relation }}
        {%- if var('as_of_date', none) %}
        where _extract_date <= '{{ var("as_of_date") }}'::date
        {%- endif %}
    )
{%- endmacro %}
