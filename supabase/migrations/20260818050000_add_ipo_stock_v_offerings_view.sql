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
        as select * from "ipo-stock".v_offerings
    $v$;
    execute 'revoke all on table ipo_stock.v_offerings from public, anon, authenticated';
    execute 'grant select on table ipo_stock.v_offerings to service_role';
  end if;
end
$$;

notify pgrst, 'reload schema';
