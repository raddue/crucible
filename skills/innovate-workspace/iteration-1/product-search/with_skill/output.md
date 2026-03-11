I'm using the innovate skill to explore potential improvements.

I've reviewed the product search implementation plan. The tasks cover full-text search, filtering, ranking, pagination, frontend integration, tests, and analytics logging. This is a well-scoped plan. But there is one addition that would make the search experience dramatically better by leveraging infrastructure you're already building.

## The Single Best Addition

**Add a `search_suggestions` materialized view that powers a typeahead/autocomplete endpoint (`GET /api/products/search/suggest?q=prefix`), built from the same `tsvector` index you're already creating in Task 2.**

The materialized view aggregates distinct lexemes from product names and category names, paired with their document frequency (how many products contain that term). The suggest endpoint queries this view using a prefix match (`lexeme LIKE 'prefix%'`) and returns the top 5-8 suggestions ordered by frequency. Refresh the materialized view on a schedule (e.g., nightly or after bulk product imports) rather than in real-time.

Implementation is a single SQL materialized view definition, one new Express route, and a small React component that calls the suggest endpoint on keystrokes (you're already adding debounced input in Task 6).

## Why This Over Alternatives

**Runner-up: Synonym expansion / query rewriting.** This would improve recall for searches like "sneakers" vs "shoes," but it requires curating a synonym dictionary, adds complexity to the query builder, and the payoff depends on how diverse your product naming is. The typeahead, by contrast, helps every single user on every single search by reducing typos and guiding them toward terms that actually exist in your catalog.

**Runner-up: Faceted search counts.** Showing "Electronics (234), Clothing (89)" alongside results is useful but is primarily a UI enhancement that doesn't change search quality. It also requires additional queries or aggregation logic. The typeahead improves the input quality, which has a multiplicative effect on the usefulness of everything else you're building.

## Impact

Typeahead fundamentally changes search from "type a query, hit enter, hope for results" to "type a few characters, see what exists, pick the right term." This eliminates zero-result searches caused by typos or wrong terminology, which is the single biggest frustration in e-commerce search. With 50k products, users cannot guess what terms will match. The search analytics table from Task 8 will show dramatically fewer failed queries once typeahead is live. Additionally, because the suggestions come from actual indexed terms, users are guided toward queries that will produce well-ranked results from your `ts_rank()` implementation.

## Cost

Approximately 2-3 days of work within the existing timeline. The materialized view is a single SQL migration. The Express route is trivial (query the view with a prefix match, return JSON). The React component reuses the debounced input pattern from Task 6. No new infrastructure beyond PostgreSQL. The main cost is the materialized view refresh strategy, but a simple cron-based `REFRESH MATERIALIZED VIEW CONCURRENTLY` (supported in PostgreSQL 15) avoids any locking concerns. This fits comfortably within the 4-week timeline and the existing stack.
