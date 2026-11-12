-- Historique des prix standard : une ligne par période de validité d'un prix.
-- Construit à partir des exports ERP quotidiens complets : on ne garde que les jours
-- où le prix change. (À l'étape 5, un snapshot dbt prendra le relais pour l'avenir.)

with daily as (
    select
        material_id,
        plant,
        standard_price,
        currency,
        extract_date,
        lag(standard_price) over (partition by material_id, plant order by extract_date) as previous_price
    from {{ ref('stg_erp__prices') }}
),

changes as (
    select *
    from daily
    where previous_price is null or standard_price <> previous_price
)

select
    material_id                                                       as product_id,
    plant,
    standard_price,
    -- types explicites : lag() et les calculs perdent la précision du numeric d'origine
    previous_price::numeric(18, 3)                                    as previous_price,
    round(100.0 * (standard_price - previous_price) / nullif(previous_price, 0), 2)::numeric(9, 2) as change_pct,
    currency,
    extract_date                                                      as valid_from,
    lead(extract_date) over (partition by material_id, plant order by extract_date) - 1 as valid_to,
    lead(extract_date) over (partition by material_id, plant order by extract_date) is null as is_current
from changes
