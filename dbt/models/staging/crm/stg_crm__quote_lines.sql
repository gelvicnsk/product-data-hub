-- Lignes de devis : dernière version connue. Grain : quote_line_id.
-- ProductCode = identifiant article sans les zéros SAP ; il peut ne pas exister dans l'ERP.

with versions as (
    select
        *,
        row_number() over (partition by id order by last_modified_date::timestamptz desc) as version_rank
    from {{ source('crm', 'crm_quote_lines') }}
)

select
    id                                          as quote_line_id,
    quote_id,
    product_code,
    nullif(product_code, '')::bigint            as material_id,
    quantity::integer                           as quantity,
    list_price::numeric(18, 2)                  as list_price,
    discount::numeric(5, 2)                     as discount_pct,
    unit_price::numeric(18, 2)                  as unit_price,
    quantity::integer * unit_price::numeric(18, 2) as line_amount,
    created_date::timestamptz                   as created_at
from versions
where version_rank = 1
