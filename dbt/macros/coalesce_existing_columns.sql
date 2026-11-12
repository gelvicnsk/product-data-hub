{#
  Évolution de schéma côté source : renvoie coalesce() des colonnes candidates
  qui existent vraiment dans la table raw.

  Exemple : l'export SAP a renommé MAKTX en MAKTX_LONG pendant une journée.
  Le chargeur a ajouté la colonne maktx_long ; ce modèle continue de fonctionner,
  que la colonne existe déjà ou pas.
    {{ coalesce_existing_columns(source('erp', 'erp_mara'), ['maktx', 'maktx_long']) }}
#}
{% macro coalesce_existing_columns(relation, candidates) -%}
    {%- if execute -%}
        {%- set existing = adapter.get_columns_in_relation(relation) | map(attribute='name') | map('lower') | list -%}
    {%- else -%}
        {%- set existing = candidates -%}
    {%- endif -%}
    {%- set present = [] -%}
    {%- for c in candidates if c | lower in existing -%}
        {%- do present.append(adapter.quote(c)) -%}
    {%- endfor -%}
    {%- if present | length == 0 -%}
        {{ exceptions.raise_compiler_error("Aucune des colonnes " ~ candidates ~ " n'existe dans " ~ relation) }}
    {%- elif present | length == 1 -%}
        {{ present[0] }}
    {%- else -%}
        coalesce({{ present | join(', ') }})
    {%- endif -%}
{%- endmacro %}
