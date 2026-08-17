create or replace function ipo_stock.schema_list_tables()
returns jsonb
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select coalesce(
    jsonb_agg(table_json order by table_name),
    '[]'::jsonb
  )
  from (
    select
      c.relname as table_name,
      jsonb_build_object(
        'name', c.relname,
        'columns', coalesce((
          select jsonb_agg(
            jsonb_build_object(
              'name', a.attname,
              'type', pg_catalog.format_type(a.atttypid, a.atttypmod),
              'nullable', not a.attnotnull,
              'primary_key', con.oid is not null
            )
            order by a.attnum
          )
          from pg_catalog.pg_attribute a
          left join pg_catalog.pg_constraint con
            on con.conrelid = c.oid
           and con.contype = 'p'
           and a.attnum = any (con.conkey)
          where a.attrelid = c.oid
            and a.attnum > 0
            and not a.attisdropped
        ), '[]'::jsonb)
      ) as table_json
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'ipo_stock'
      and c.relkind = 'r'
      and not c.relispartition
  ) tables;
$$;

create or replace function ipo_stock.schema_add_column(
  p_table text,
  p_column text,
  p_type text,
  p_nullable boolean default true
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  allowed_types text[] := array[
    'text',
    'integer',
    'bigint',
    'boolean',
    'date',
    'timestamptz',
    'numeric',
    'uuid',
    'jsonb'
  ];
  ident_re text := '^[a-z][a-z0-9_]{0,62}$';
begin
  if p_table is null or p_table !~ ident_re then
    raise exception 'invalid table name' using errcode = '22023';
  end if;
  if p_column is null or p_column !~ ident_re then
    raise exception 'invalid column name' using errcode = '22023';
  end if;
  if p_type is null or not (p_type = any (allowed_types)) then
    raise exception 'invalid column type' using errcode = '22023';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'ipo_stock'
      and c.relname = p_table
      and c.relkind = 'r'
  ) then
    raise exception 'table not found' using errcode = '42P01';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_attribute a
    join pg_catalog.pg_class c on c.oid = a.attrelid
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'ipo_stock'
      and c.relname = p_table
      and a.attname = p_column
      and a.attnum > 0
      and not a.attisdropped
  ) then
    raise exception 'column already exists' using errcode = '42701';
  end if;

  execute format(
    'alter table ipo_stock.%I add column %I %s%s',
    p_table,
    p_column,
    p_type,
    case when p_nullable then '' else ' not null' end
  );
  perform pg_catalog.pg_notify('pgrst', 'reload schema');

  return jsonb_build_object(
    'name', p_column,
    'type', p_type,
    'nullable', p_nullable,
    'primary_key', false
  );
end;
$$;

create or replace function ipo_stock.schema_drop_column(
  p_table text,
  p_column text
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  ident_re text := '^[a-z][a-z0-9_]{0,62}$';
begin
  if p_table is null or p_table !~ ident_re then
    raise exception 'invalid table name' using errcode = '22023';
  end if;
  if p_column is null or p_column !~ ident_re then
    raise exception 'invalid column name' using errcode = '22023';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'ipo_stock'
      and c.relname = p_table
      and c.relkind = 'r'
  ) then
    raise exception 'table not found' using errcode = '42P01';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_attribute a
    join pg_catalog.pg_class c on c.oid = a.attrelid
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'ipo_stock'
      and c.relname = p_table
      and a.attname = p_column
      and a.attnum > 0
      and not a.attisdropped
  ) then
    raise exception 'column not found' using errcode = '42703';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_constraint con
    join pg_catalog.pg_class c on c.oid = con.conrelid
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    join pg_catalog.pg_attribute a
      on a.attrelid = c.oid
     and a.attnum = any (con.conkey)
    where n.nspname = 'ipo_stock'
      and c.relname = p_table
      and a.attname = p_column
      and con.contype = 'p'
  ) then
    raise exception 'cannot drop primary key column' using errcode = '22023';
  end if;

  execute format(
    'alter table ipo_stock.%I drop column %I',
    p_table,
    p_column
  );
  perform pg_catalog.pg_notify('pgrst', 'reload schema');

  return jsonb_build_object('name', p_column);
end;
$$;

revoke all on function ipo_stock.schema_list_tables() from public, anon, authenticated;
revoke all on function ipo_stock.schema_add_column(text, text, text, boolean) from public, anon, authenticated;
revoke all on function ipo_stock.schema_drop_column(text, text) from public, anon, authenticated;
grant execute on function ipo_stock.schema_list_tables() to service_role;
grant execute on function ipo_stock.schema_add_column(text, text, text, boolean) to service_role;
grant execute on function ipo_stock.schema_drop_column(text, text) to service_role;
