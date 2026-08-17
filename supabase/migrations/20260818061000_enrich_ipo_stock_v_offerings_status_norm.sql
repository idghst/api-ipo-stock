-- status_norm: 뷰 한글/NULL 상태를 API enum으로 정규화. SELECT only.
create schema if not exists ipo_stock;

revoke all privileges on schema ipo_stock from public, anon, authenticated;
grant usage on schema ipo_stock to service_role;

do $$
begin
  if exists (
    select 1
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'ipo-stock'
      and c.relname = 'v_offerings'
      and c.relkind = 'v'
  ) then
    execute $v$
      create or replace view ipo_stock.v_offerings
        with (security_invoker = true)
        as
        select
          src.*,
          case
            when src.status::text like '공모철회%' then 'cancelled'
            when src.status::text = '신규상장' then 'listed'
            when src.status::text in (
              'scheduled',
              'subscription_open',
              'subscription_closed',
              'listed',
              'cancelled'
            ) then src.status::text
            when src.listing_date is not null
              and src.listing_date::date
                <= (timezone('Asia/Seoul', now()))::date
              then 'listed'
            when src.subscribe_start is not null
              and src.subscribe_end is not null
              and src.subscribe_start::date
                <= (timezone('Asia/Seoul', now()))::date
              and src.subscribe_end::date
                >= (timezone('Asia/Seoul', now()))::date
              then 'subscription_open'
            when src.subscribe_end is not null
              and src.subscribe_end::date
                < (timezone('Asia/Seoul', now()))::date
              then 'subscription_closed'
            else 'scheduled'
          end as status_norm
        from "ipo-stock".v_offerings as src
    $v$;
    execute 'revoke all on table ipo_stock.v_offerings from public, anon, authenticated';
    execute 'grant select on table ipo_stock.v_offerings to service_role';
  end if;
end
$$;

notify pgrst, 'reload schema';
