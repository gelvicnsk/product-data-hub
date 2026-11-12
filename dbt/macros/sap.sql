{# Conversions des formats SAP exportés (texte) vers des types SQL. #}

{# '000000000010000123' -> 10000123 #}
{% macro sap_material_id(column) -%}
    nullif(ltrim({{ column }}, '0'), '')::bigint
{%- endmacro %}

{# '1234,50' -> 1234.50  (décimale française) #}
{% macro sap_decimal(column) -%}
    replace({{ column }}, ',', '.')::numeric(18, 3)
{%- endmacro %}

{# '20231127' -> date ; vide -> null #}
{% macro sap_date(column) -%}
    to_date(nullif({{ column }}, ''), 'YYYYMMDD')
{%- endmacro %}
