-- Comptes clients avec leur activité de devis. Grain : un compte.

with quotes as (
    select
        account_id,
        count(*)                                              as quote_count,
        count(*) filter (where quote_status = 'Accepted')     as accepted_quote_count,
        max(created_at)                                       as last_quote_at
    from {{ ref('stg_crm__quotes') }}
    group by account_id
)

select
    accounts.account_id,
    accounts.account_name,
    accounts.country,
    accounts.segment,
    accounts.created_at,
    coalesce(quotes.quote_count, 0)            as quote_count,
    coalesce(quotes.accepted_quote_count, 0)   as accepted_quote_count,
    quotes.last_quote_at
from {{ ref('stg_crm__accounts') }} as accounts
left join quotes on quotes.account_id = accounts.account_id
