-- Devis : dernière version connue (statut courant). Grain : quote_id.

with versions as (
    select
        *,
        row_number() over (partition by id order by last_modified_date::timestamptz desc) as version_rank,
        count(*) over (partition by id)                                                 as version_count
    from {{ source('crm', 'crm_quotes') }}
)

select
    id                                  as quote_id,
    name                                as quote_number,
    account_id,
    status                              as quote_status,
    expiration_date::date               as expires_on,
    currency_iso_code                   as currency,
    created_date::timestamptz           as created_at,
    last_modified_date::timestamptz     as last_modified_at,
    version_count
from versions
where version_rank = 1
