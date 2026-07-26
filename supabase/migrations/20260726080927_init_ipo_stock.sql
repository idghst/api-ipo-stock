create schema if not exists ipo_stock;
grant usage on schema ipo_stock to anon, authenticated, service_role;
alter default privileges in schema ipo_stock
  grant all on tables to service_role;
alter default privileges in schema ipo_stock
  grant all on sequences to service_role;
alter default privileges in schema ipo_stock
  grant execute on routines to service_role;
