# Hours audit

Checks whether a location's hours agree across three sources: Google Business
Profile (GBP), the website, and the team's own hours sheet. The website
turned out not to be reliable enough to treat as ground truth on its own, so
the sheet was added as a third, independently-checked source rather than a
replacement.

Built for Aqua-Tots first; Papa's Pizza To Go was added second. Everything
except the website's HTML parsing is shared across brands unchanged -- see
"Adding a new brand" near the bottom.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`source .venv/bin/activate` only lasts for the current terminal session/tab —
run it again in any new terminal before using `python`/`pip` below. If you'd
rather not activate, prefix every command with the venv's own interpreter
instead: `.venv/bin/python audit.py --gbp gbp_export.csv`.

## Web app (for the team, no command line)

```bash
streamlit run app.py
```

Opens a page at `http://localhost:8501`: pick a **Brand** (this is what
selects which website-parsing logic runs — see "Adding a new brand" below),
optionally paste a Master Sheet URL (pre-filled with that brand's sheet if
one's registered, blank otherwise so you don't accidentally audit the wrong
brand against someone else's sheet), upload the GBP export CSV, pick a
**Source of truth**, click "Run audit". You get a table back — just **Name**
plus the match column(s) for whichever source you picked — color-coded
green (`Yes`) / red (`No`) / amber (`N/A (not enough data)`), plus a CSV
download button. Store code, Locality, State, and Website aren't shown in
the table (the name already identifies the location, and Website lives in
the hours dialog instead — see below), but all four are still included in
the CSV download for reference.

**The Master Sheet is optional.** Leave the URL blank and the app compares
GBP against the website only — same as before the sheet existed — with a
single `GBP Matches Website` (or `Website Matches GBP`) column. The moment
a URL is there, Master Sheet becomes available as a third source and a
choice in the dropdown; clearing the URL later automatically falls back the
selection to Website if it was set to Master Sheet, since that option no
longer exists.

**Source of truth is a dropdown, not fixed**: with a sheet, pick GBP,
Website, or Master Sheet; without one, pick GBP or Website. The app checks
the *other* source(s) directly against whichever one you picked — same
star-shaped comparison either way, just pointed at a different center.
Column names and the hours dialog both follow: pick "GBP" (with a sheet
present) and you get `Website Matches GBP` / `Master Sheet Matches GBP`,
with the dialog showing GBP plain and the other two colored against it.
Master Sheet is the recommended default when available since it's the one
the team maintains by hand — the website turned out not to be reliable
enough to trust on its own — but nothing stops you from checking, say,
whether the website and sheet agree with what's on GBP instead.

**Changing the dropdown alone doesn't change what's on screen** — it only
takes effect on the next "Run audit" click. The already-computed report
keeps showing the source of truth it was actually run with, so you can't
end up with a screen where the columns and the underlying numbers disagree
about which source is "truth."

**Hours live in a dialog, not the table**: comma-separated per-day times
across multiple columns were hard to scan side by side, so the table only
shows the match verdicts. Click anywhere on a row to open a popup with a
proper Day grid for that location (source of truth first, then the other
source(s)), plus the location's website link at the bottom. The chosen
source of truth is shown plain, and the other column(s) are each colored by
comparing directly against it (gray means the source of truth had no data
for that day, so there's nothing to check against). Click the row again (or
another row) to close it or switch locations.

**How the match column(s) work:** each is checked directly against
whichever source you picked as truth, not against each other — with a
sheet present, reporting them separately (rather than one combined verdict)
shows which side is actually the odd one out. The trade-off of trusting one
source: if that source itself is wrong, the other(s) can come back flagged
even though they agree with each other — that's expected, not a bug, since
everything is judged against the chosen source on purpose. A day only
counts if both sides being compared have data for it; a location with too
little overlapping data across the board comes back `N/A (not enough
data)` rather than a false `Yes`.

**The sheet join is name-based and exact-ish**: a location's GBP `Business
name` is matched to the sheet's `Location Name` after lowercasing and
stripping punctuation/whitespace differences. If the names don't line up at
all (different naming conventions between GBP and the sheet), that row will
show `(no match in sheet)` — there's no fuzzy/approximate matching, so keep
the sheet's names close to the GBP export's names for this to work.

**Sheet blank-cell policy differs from GBP's**: unlike the GBP export (where
blank is documented to mean "closed"), a blank cell in the team's sheet is
treated as *unknown* — it doesn't count toward a mismatch either way. Write
"Closed" explicitly in the sheet for days that are actually closed.

**Always write am/pm in the sheet — bare hour ranges are read as 24h,
and closing times entered without "pm" are read as if they were in the
morning.** For example `10:15-8:00` isn't read as "10:15am to 8:00pm" — it's
read literally as 24h clock values, and since 8:00 comes before 10:15, the
parser has to assume you meant an overnight span running from 10:15am all
the way through the night to 8:00am the next day. There is no way to tell,
from `10:15-8:00` alone, whether that's really what you meant or whether
"pm" just got dropped when the sheet was typed or exported — so rather than
guess (and risk a wrong match or a wrong mismatch), the tool treats any cell
shaped like this as *unknown* (blank cell in the "Sheet Hours" column,
`N/A (not enough data)` if it's the only source with data for that day).
Nothing gets silently miscompared, but it does mean that day looks
unaudited until the sheet is fixed. Prefer `10:15am - 8:00pm` or
`10:15-20:00` — either is read correctly, with or without am/pm, as long as
at least one side of the range makes the meridiem unambiguous.

**Deploying it for the team (free):**
1. Push this folder to a GitHub repo (a private repo is fine).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, and pick
   "New app" → point it at the repo, branch, and `app.py`.
3. That's it — no server to manage, no credentials needed (the sheet is read
   via its public CSV export link, not an API key), and every push to the
   branch redeploys it automatically.

The app scrapes the website on every run, but each page's raw HTML is
cached to disk (`./cache`) by URL so re-runs are fast and don't hammer the
site. **That cache has no expiry** — if a location's site is edited after
its page was cached, the app will keep serving the old copy indefinitely
until someone clears it. If a result looks wrong or out of date, check
"Force refresh (ignore cached pages)" under Advanced settings and re-run;
that ignores the cache and refetches every page live (slower — a full
refetch, not just the first run). On a hosted deployment, restarting the
app also clears the cache, since it isn't committed to the repo.

**Verbose logging**: every run prints each stage (fetching the sheet,
scraping — one line per page with its fetch status, comparing — the
verdict counts per column) to stdout with timestamps. Locally that's your
terminal; on Streamlit Community Cloud, open the app, click the hamburger
menu → **Manage app** to see the same log stream while the audit runs.
Useful for telling whether a run is still working or stuck, and for
spotting which specific page a slow or failed fetch came from.

## Command-line usage

The CLI tools below (`audit.py`, `scrape_website_hours.py`,
`compare_hours.py`) only ever compare GBP against the website — they predate
the sheet and don't take a sheet argument. For the three-way GBP/website/sheet
comparison, use the web app above. These stick around for quick scripted
runs and for the wide per-day report the app doesn't produce.

### Quick version — one command, simple output

```bash
python audit.py --gbp gbp_export.csv
```

Scrapes and compares in one shot and writes `simple_report.csv`: one row per
location with `Business name`, `GBP Hours`, `Website Hours`, and `Do they
Match` (`Yes` / `No` / `N/A (...)` for locations with nothing to compare —
no website, no GBP hours, etc). Same flags as below apply (`--tolerance`,
`--workers`, `--cache`, `--blank-gbp-is-closed`), plus `--brand` (see
"Adding a new brand" below; defaults to `aqua_tots`).

### Full version — two steps, full detail

For the wide per-day report (per-day match/diff columns, `What to fix`
strings, fetch status) or when you want to tweak comparison rules without
re-scraping, use the two scripts directly. Scraping and comparing are separate scripts on purpose: scraping
186 pages is slow and occasionally flaky, while the comparison rules (blank
handling, tolerance, filters) get tweaked and re-run far more often. Keeping
them apart means a comparison-logic change never costs a re-fetch.

**1. Scrape the sites** (reads URLs out of the GBP export, writes `website_hours.csv`):

```bash
python scrape_website_hours.py --gbp gbp_export.csv
```

Useful flags:
- `--brand aqua_tots|papas_pizza` — which site's markup to parse (default
  `aqua_tots`). See "Adding a new brand" below.
- `--limit 5` — smoke test against the first 5 pages only.
- `--workers 8` — parallel fetch workers (default 8).
- `--cache ./cache` — disk cache directory for raw HTML, keyed by URL hash. A
  re-run reads from cache and costs zero requests; use `--no-cache-read` to
  force a refetch (e.g. after the site itself changes).
- `--out website_hours.csv` — output path.

**2. Compare against the GBP export:**

```bash
python compare_hours.py --gbp gbp_export.csv --site website_hours.csv
```

Useful flags:
- `--tolerance 15` — minutes of slack allowed per boundary (e.g. a 9:00 vs
  9:10 open time won't be flagged).
- `--only-mismatch` — filter the output down to non-`MATCH` rows, for a
  client-facing version of the report.
- `--blank-gbp-is-closed yes|no` — see "Blank-cell policy" below.
- `--out hours_comparison.csv` — output path.

Both scripts print a summary to stdout; the full detail goes to the CSV.

## Verdicts

| verdict | meaning |
|---|---|
| `MATCH` | all seven days agree between GBP and the site |
| `MISMATCH` | at least one day differs |
| `GBP_NO_HOURS` | the GBP export has no hours published for this location at all (all seven cells blank) |
| `SITE_NO_HOURS` | the location page has no "Hours of Operation" block, or the fetch failed |
| `NO_WEBSITE` | no URL in the GBP export for this location |
| `NOT_SCRAPED` | the location has a URL, but it's missing from `website_hours.csv` (re-run the scraper, or check `--limit`) |

`hours_comparison.csv` is sorted worst-first: `MISMATCH`, then
`SITE_NO_HOURS`, `GBP_NO_HOURS`, `NOT_SCRAPED`, `NO_WEBSITE`, `MATCH` last.

## Blank-cell policy

In the GBP export, a closed day is an **empty cell** — the word "Closed"
never appears. By default (`--blank-gbp-is-closed yes`), a blank day cell is
read as "closed that day". The one exception: if **all seven** day cells for
a location are blank, that's treated as "no hours published at all"
(`GBP_NO_HOURS`) rather than reported as seven day mismatches.

Pass `--blank-gbp-is-closed no` to instead treat every blank cell as unknown
(excluded from the day-by-day comparison rather than compared as "Closed").

`Special hours` (holiday overrides) is out of scope for this audit — it's
carried into the report as a reference column (`Special hours (GBP)`) and
never compared.

## A note on non-US templates

7 locations sit on different domains/templates than the main US site:
`thailand.aqua-tots.com` (5 locations) and `www.aqua-tots.com.tr` (2
locations). The scraper's hours-extraction logic was built and verified
against the standard `www.aqua-tots.com` template. These 7 rows may come
back as `SITE_NO_HOURS`, or with hours that look off, simply because the page
structure differs — eyeball them by hand after the first run rather than
trusting the verdict blindly.

## Adding a new brand

Only the website's HTML parsing is brand-specific. GBP parsing, the sheet
join, the comparison logic, the caching/fetching/retry machinery, and the
whole app UI are shared as-is — a new brand is one new file plus one line.

1. **Look at the site first.** Fetch a real location page with plain
   `requests` (no browser) and check the hours are actually in that raw
   HTML — some sites render hours client-side with JavaScript, which this
   project can't handle (see the ground-truth check that was done for
   Aqua-Tots and Papa's Pizza, both server-rendered). Note the real
   selector/heading the hours live under, the day-name order, the time
   format (12h vs 24h, am/pm placement), how a closed day is written, and
   whether any location has split hours (e.g. a lunch/dinner gap).

2. **Write `scrapers/<brand>.py`** with one function:

   ```python
   def parse_page(html, requested_url):
       """Returns (hours_by_day, page_title, page_phone, raw_block, notes)."""
   ```

   `hours_by_day` is `{day: canonical}` using `hours_lib.parse_day_hours()`
   on each day's raw text — reuse it rather than writing new time parsing;
   it already handles 12h/24h, split hours, "Closed", ranges with no am/pm,
   and the ambiguous-time safety check (see "Always write am/pm" above).
   `notes` should include `"no hours block found"` when the expected
   markup isn't present, so that row surfaces for manual review. Look at
   `scrapers/aqua_tots.py` (ancestor-climbing around a heading, no stable
   CSS hook) and `scrapers/papas_pizza.py` (a clean, directly-selectable
   grid) as two different real shapes to model from.

3. **Register it** in `scrapers/__init__.py`: add one entry to `BRANDS` with
   a display label, the new `parse_page`, and a `default_sheet_url` (blank
   string if there isn't one yet).

4. **Write tests** in `tests/test_scrapers_<brand>.py` against real HTML
   fixtures captured from the live site (not hypothetical markup) — at
   least one normal location, one with a closed day, and one missing the
   hours block entirely. `tests/test_scrapers_papas_pizza.py` is a template.

That's it — the brand shows up in the app's **Brand** dropdown and in
`--brand` on the CLI tools automatically, with no other file needing to
change.

## Tests

```bash
pytest
```

Runs entirely offline against fixed HTML/text fixtures — no network calls.
