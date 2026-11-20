-- FastAPI(api-ipo-stock) 전용 읽기 전용 롤. ipostock DB에서 슈퍼유저로 한 번 실행한다.
--   docker exec -i -u postgres postgres psql -d ipostock -v ON_ERROR_STOP=1 -v app_password="$APP_DB_PASSWORD" < sql/ipostock_app.sql
-- 앱은 ipostock.v_offerings만 읽는다. 뷰가 security_invoker라 뷰가 읽는 표 7개에도 SELECT와 RLS 읽기 정책이 필요하다.

create role ipostock_app login password :'app_password';
alter role ipostock_app set default_transaction_read_only = on;

grant connect on database ipostock to ipostock_app;
grant usage on schema ipostock to ipostock_app;
grant select on
  ipostock.v_offerings,
  ipostock.offerings,
  ipostock.companies,
  ipostock.offering_financials,
  ipostock.demand_results,
  ipostock.listing_results,
  ipostock.offering_underwriters,
  ipostock.underwriters
to ipostock_app;

create policy ipostock_app_read on ipostock.offerings for select to ipostock_app using (true);
create policy ipostock_app_read on ipostock.companies for select to ipostock_app using (true);
create policy ipostock_app_read on ipostock.offering_financials for select to ipostock_app using (true);
create policy ipostock_app_read on ipostock.demand_results for select to ipostock_app using (true);
create policy ipostock_app_read on ipostock.listing_results for select to ipostock_app using (true);
create policy ipostock_app_read on ipostock.offering_underwriters for select to ipostock_app using (true);
create policy ipostock_app_read on ipostock.underwriters for select to ipostock_app using (true);
