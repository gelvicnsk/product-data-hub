-- Chiffre d'affaires et marge des devis acceptés, par famille de produits.
-- Coût = prix standard ERP connu le jour du devis. Les lignes sur un produit inconnu
-- de l'ERP sont gardées dans une famille « Non rapproché » pour que les totaux
-- restent égaux à ceux du CRM (voir le test assert_margin_matches_reference).

select
    coalesce(products.family, 'Non rapproché')        as family,
    count(distinct lines.quote_id)                    as accepted_quote_count,
    count(*)                                          as line_count,
    sum(lines.line_amount)::numeric(18, 2)            as revenue,
    sum(lines.line_cost)::numeric(18, 2)              as cost,
    sum(lines.line_margin)::numeric(18, 2)            as margin,
    round(100.0 * sum(lines.line_margin) / nullif(sum(lines.line_amount), 0), 2)::numeric(7, 2) as margin_pct
from {{ ref('fct_quote_lines') }} as lines
left join {{ ref('dim_product') }} as products on products.product_id = lines.material_id
where lines.quote_status = 'Accepted'
group by 1
