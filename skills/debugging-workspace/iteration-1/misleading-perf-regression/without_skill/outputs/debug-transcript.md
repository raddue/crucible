# Debug Transcript: API Response Time Regression After v2.3 Deploy

## User's Problem
API response times jumped from ~50ms to ~500ms after deploying v2.3 yesterday. Team assumes it's the new recommendation engine code.

## Investigation

Let me look at the evidence carefully before jumping to conclusions.

**Key observation #1**: The new `/api/recommendations` endpoint itself responds in ~30ms. If the new recommendation code were the problem, that endpoint would be slow too.

**Key observation #2**: The slowdown affects ALL endpoints, not just the new one. This strongly suggests a systemic issue, not a problem with any specific application code.

**Key observation #3**: The top offending slow query is from `/api/users/recent`, which hasn't been changed in months:

```sql
SELECT u.*, p.* FROM users u
JOIN purchases p ON u.id = p.user_id
WHERE u.created_at > '2024-01-01'
ORDER BY u.created_at DESC
LIMIT 50;
```

**Key observation #4**: The EXPLAIN output shows a sequential scan on the users table:

```
Seq Scan on users u  (cost=0.00..1850432.00 rows=25000000 width=892)
  Filter: (created_at > '2024-01-01')
  Rows Removed by Filter: 25000000
```

This is scanning all 50M rows sequentially instead of using an index on `created_at`. Note also the `width=892` -- the row width is significant.

**Key observation #5**: The v2.3 migration added a JSONB column with a default value to the 50M-row users table:

```sql
ALTER TABLE users ADD COLUMN preferences JSONB DEFAULT '{}';
```

## Root Cause

The migration `ALTER TABLE users ADD COLUMN preferences JSONB DEFAULT '{}'` is almost certainly the cause. In PostgreSQL, adding a column with a non-null default to a large table (prior to PostgreSQL 11, and sometimes in later versions depending on the default expression and data type) triggers a **full table rewrite**. Even in PostgreSQL 11+, a JSONB column with a default can cause a table rewrite depending on the exact version and circumstances.

A full table rewrite on a 50M-row table has several effects:

1. **Table bloat**: The rewrite creates a new copy of all rows, and the old pages may not be immediately reclaimed, causing massive table bloat. The query planner sees the inflated table size and may decide a sequential scan is cheaper than an index scan.

2. **Index invalidation/bloat**: Existing indexes (including presumably one on `created_at`) may need to be rebuilt after such a rewrite, or they may become bloated and less efficient. The planner may stop choosing them.

3. **Statistics staleness**: The table statistics used by the query planner are now stale after the rewrite. PostgreSQL's autovacuum/autoanalyze may not have caught up yet, leading the planner to make bad decisions (like choosing Seq Scan over Index Scan).

The EXPLAIN output confirms this -- it's doing a Seq Scan on a table with 50M rows where there should be an index scan on `created_at`.

**Your DBA's suggestion to "rewrite the recommendation queries" is misdirected.** The slow query has nothing to do with the recommendation feature. It's a pre-existing query on the users table that became slow because the migration changed the table's physical characteristics.

## Fix

### Immediate fix:

1. **Run ANALYZE on the users table** to update planner statistics:
   ```sql
   ANALYZE users;
   ```

2. **Check if the index on `created_at` exists and is healthy**:
   ```sql
   SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'users';
   ```

3. **If the index exists but isn't being used, rebuild it**:
   ```sql
   REINDEX INDEX CONCURRENTLY idx_users_created_at;
   ```

4. **If no index exists on `created_at`, create one**:
   ```sql
   CREATE INDEX CONCURRENTLY idx_users_created_at ON users (created_at DESC);
   ```

5. **Run VACUUM to reclaim bloated space**:
   ```sql
   VACUUM (VERBOSE) users;
   ```
   For severe bloat, consider `VACUUM FULL` (but be aware this locks the table).

### Verification:

After the fix, re-run the EXPLAIN on the slow query and confirm it now shows an Index Scan instead of a Seq Scan:

```sql
EXPLAIN ANALYZE
SELECT u.*, p.* FROM users u
JOIN purchases p ON u.id = p.user_id
WHERE u.created_at > '2024-01-01'
ORDER BY u.created_at DESC
LIMIT 50;
```

### Prevention:

- For future migrations on large tables, test on a staging environment with production-sized data first.
- Monitor `pg_stat_user_tables` for sequential scan counts after deployments.
- Consider running `ANALYZE` as a post-migration step in your deployment pipeline.
- For very large tables, consider using `ALTER TABLE ... ADD COLUMN` without a default, then backfilling in batches.

## Summary

The correlation with v2.3 was real but the causation was misattributed. The new recommendation code is fine (it responds in 30ms). The actual cause was the database migration that altered the 50M-row users table, which invalidated or degraded the index on `created_at` and/or bloated the table, causing the query planner to fall back to sequential scans on all queries touching the users table.
