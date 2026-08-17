revoke all on function "ipo-stock".backfill_batch(json) from public, anon, authenticated;
grant execute on function "ipo-stock".backfill_batch(json) to service_role;
notify pgrst, 'reload schema';
