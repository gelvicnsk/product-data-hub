-- Lignes de devis enrichies. Grain : une ligne de devis.
--
-- Deux informations sont reconstituées « à la date du devis » à partir des exports
-- quotidiens, et non avec l'état d'aujourd'hui :
--   - l'état PLM du produit ce jour-là (était-il déjà en fin de vie ?) ;
--   - le prix standard ERP connu ce jour-là (dernier export disponible, même si un
--     export a manqué), utilisé comme coût pour calculer la marge.

with lines as (
    select * from {{ ref('stg_crm__quote_lines') }}
),

quotes as (
    select * from {{ ref('stg_crm__quotes') }}
),

products as (
    select product_id from {{ ref('dim_product') }}
),

base as (
    select
        lines.quote_line_id,
        lines.quote_id,
        quotes.quote_number,
        quotes.account_id,
        quotes.quote_status,
        quotes.created_at                                    as quote_created_at,
        (quotes.created_at at time zone 'UTC')::date         as quote_date,
        lines.product_code,
        lines.material_id,
        lines.quantity,
        lines.list_price,
        lines.discount_pct,
        lines.unit_price,
        lines.line_amount,
        products.product_id is not null                      as has_known_product
    from lines
    join quotes on quotes.quote_id = lines.quote_id
    left join products on products.product_id = lines.material_id
),

cost_candidates as (
    -- prix connu le jour du devis : dernier export ERP à cette date ou avant
    -- (une journée sans export ERP reprend donc le prix de la veille)
    select
        base.quote_line_id,
        prices.standard_price,
        row_number() over (partition by base.quote_line_id order by prices.extract_date desc) as recency
    from base
    join {{ ref('stg_erp__prices') }} as prices
        on prices.material_id = base.material_id
        and prices.extract_date <= base.quote_date
),

cost as (
    select quote_line_id, standard_price from cost_candidates where recency = 1
)

select
    base.*,
    plm.lifecycle_state                                          as lifecycle_state_at_quote,
    coalesce(plm.lifecycle_state in ('END_OF_LIFE', 'RETIRED'), false) as is_eol_at_quote,
    cost.standard_price                                          as unit_cost_at_quote,
    (base.quantity * cost.standard_price)::numeric(18, 2)        as line_cost,
    (base.line_amount - base.quantity * cost.standard_price)::numeric(18, 2) as line_margin
from base
left join {{ ref('stg_plm__lifecycle') }} as plm
    on plm.material_id = base.material_id
    and plm.extract_date = base.quote_date
left join cost on cost.quote_line_id = base.quote_line_id
