-- Deux façons indépendantes de connaître le prix actuel doivent concorder :
--   - la version courante du snapshot (dbt_valid_to is null) ;
--   - la période courante de fct_price_history, reconstruite depuis les exports quotidiens.
-- Un écart signale un snapshot en retard (pas rejoué) ou une erreur de logique.

with snapshot_current as (
    select material_id, plant, standard_price
    from {{ ref('snap_material_price') }}
    where dbt_valid_to is null
),

history_current as (
    select product_id as material_id, plant, standard_price
    from {{ ref('fct_price_history') }}
    where is_current
)

(select 'absent du snapshot' as ecart, * from history_current
 except
 select 'absent du snapshot', * from snapshot_current)
union all
(select 'absent de l''historique', * from snapshot_current
 except
 select 'absent de l''historique', * from history_current)
