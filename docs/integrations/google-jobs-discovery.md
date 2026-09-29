# Google Jobs discovery

The API serves crawlable HTML job pages with Schema.org `JobPosting` JSON-LD,
plus a sitemap and `robots.txt`. This is an organic discovery path: it does not
push jobs to Google or guarantee Google Search inclusion or placement.

## Public routes

- `GET /jobs/{public_id}/{slug}` serves a canonical HTML detail page. Old slugs
  redirect to the current slug; hidden, closed, and expired postings return 404.
- `GET /sitemap.xml` lists active job pages, or returns an index of sitemap
  shards when more than 40,000 jobs are visible.
- `GET /sitemap/jobs/{page}.xml` serves one bounded sitemap shard.
- `GET /robots.txt` advertises the sitemap and disallows crawler access to the
  versioned API prefix.

Only postings that are published, not expired, and attached to an open
requisition appear in pages and the sitemap. Structured data is emitted only
when the posting has a description, a physical location, and an employer name;
the implementation does not guess that a job is remote or invent missing
location values.

## Configuration

Set `PUBLIC_SITE_BASE_URL` to the HTTPS origin that serves these routes in
production (for example, `https://careers.example.com`). It must be an origin,
without a path, query string, or fragment. Route that public hostname to the
FastAPI application. Set `PUBLIC_JOB_COUNTRY_CODE` to the applicable uppercase
ISO 3166-1 alpha-2 country code; it defaults to `KE` for the initial deployment.

After deployment, verify the site in Google Search Console and submit
`https://careers.example.com/sitemap.xml`. Keep job detail pages publicly
crawlable. The expiry worker and visibility checks remove expired/closed jobs
from public results, pages, and the sitemap.

Google's [JobPosting structured data guidance](https://developers.google.com/search/docs/appearance/structured-data/job-posting)
defines eligibility and required fields. The Google Indexing API is not used by
this integration.
