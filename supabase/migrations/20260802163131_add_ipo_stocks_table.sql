create table if not exists ipo_stock.ipo_stocks (
  id uuid primary key default gen_random_uuid(),
  company_name text not null check (char_length(company_name) between 1 and 200),
  ticker text unique check (
    ticker is null
    or (char_length(ticker) between 1 and 32 and ticker = upper(ticker))
  ),
  market text check (market is null or char_length(market) between 1 and 50),
  offer_price integer check (offer_price is null or offer_price > 0),
  subscription_start date,
  subscription_end date,
  listing_date date,
  status text not null default 'scheduled' check (
    status in (
      'scheduled',
      'subscription_open',
      'subscription_closed',
      'listed',
      'cancelled'
    )
  ),
  memo text check (memo is null or char_length(memo) <= 4000),
  check (
    subscription_end is null
    or subscription_start is null
    or subscription_end >= subscription_start
  )
);

create index if not exists ipo_stocks_status_listing_date_idx
  on ipo_stock.ipo_stocks (status, listing_date);

alter table ipo_stock.ipo_stocks enable row level security;

revoke all privileges on schema ipo_stock from public, anon, authenticated;
revoke all privileges on table ipo_stock.ipo_stocks from public, anon, authenticated;
grant usage on schema ipo_stock to service_role;
grant select, insert, update, delete on table ipo_stock.ipo_stocks to service_role;
