-- Test de référence : le chiffre d'affaires total du mart doit être égal à celui
-- recalculé directement depuis le CRM (staging), sans aucune jointure produit.
-- Il échoue si une jointure perd ou duplique des lignes. Bloquant (error).

with mart as (
    select coalesce(sum(revenue), 0) as revenue, coalesce(sum(line_count), 0) as line_count
    from {{ ref('mart_margin_by_family') }}
),

reference as (
    select coalesce(sum(lines.quantity * lines.unit_price), 0) as revenue, count(*) as line_count
    from {{ ref('stg_crm__quote_lines') }} as lines
    join {{ ref('stg_crm__quotes') }} as quotes on quotes.quote_id = lines.quote_id
    where quotes.quote_status = 'Accepted'
)

select mart.revenue as mart_revenue, reference.revenue as reference_revenue,
       mart.line_count as mart_lines, reference.line_count as reference_lines
from mart cross join reference
where abs(mart.revenue - reference.revenue) > 0.01
   or mart.line_count <> reference.line_count
