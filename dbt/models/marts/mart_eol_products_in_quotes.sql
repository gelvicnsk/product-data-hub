-- Lignes de devis portant sur un produit déjà en fin de vie (ou retiré) le jour du devis.
-- Information métier : à traiter par l'équipe commerciale, pas une panne du pipeline.

select
    lines.quote_line_id,
    lines.quote_number,
    lines.quote_status,
    lines.quote_date,
    accounts.account_name,
    lines.material_id                as product_id,
    products.product_name,
    lines.lifecycle_state_at_quote,
    products.lifecycle_state         as current_lifecycle_state,
    lines.quantity,
    lines.line_amount
from {{ ref('fct_quote_lines') }} as lines
join {{ ref('dim_product') }} as products on products.product_id = lines.material_id
left join {{ ref('dim_account') }} as accounts on accounts.account_id = lines.account_id
where lines.is_eol_at_quote
