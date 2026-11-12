-- Comptes clients : dernière version connue de chaque compte. Grain : account_id.

with versions as (
    select
        *,
        row_number() over (partition by id order by last_modified_date::timestamptz desc) as version_rank
    from {{ source('crm', 'crm_accounts') }}
)

select
    id                                  as account_id,
    name                                as account_name,
    billing_country                     as country,
    industry                            as segment,
    created_date::timestamptz           as created_at,
    last_modified_date::timestamptz     as last_modified_at
from versions
where version_rank = 1
