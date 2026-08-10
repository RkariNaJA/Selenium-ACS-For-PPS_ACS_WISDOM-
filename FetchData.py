import time
import os
import json
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv


load_dotenv()

ACS_EMAIL = os.getenv("ACS_USER")
ACS_PASSWORD = os.getenv("ACS_PASS")

# CSV column header  ->  JSON field name returned by GetPagedSearchCBD
FIELD_MAP = {
    "CBDID":         "cbdid",
    "Season":        "season",
    "Style Number":  "styleNo",
    "Modified":      "modifiedDate",
    "Created":       "createdDate",
    "Colorway Code": "colorwayCode",
    "Factory Code":  "factoryCode",
    "Final FOB":     "finalFOB",
    "ExtSzFOB":      "extendedSizeFOB",
}

# CBD statuses to search for — must match what set_filters() selects in the UI.
CBD_STATUSES = ["Q-QRMDS", "Q-CRMDS", "C"]

# Endpoints (same host).
BASE_URL = ("https://acs-service.partner.nike-cloud.com"
            "/api/CBDSearch/GetPagedSearchCBD")
SEASON_URL = ("https://acs-service.partner.nike-cloud.com"
              "/api/ResourceCollection/GetAllSeasonInformation")

ENDPOINT_MATCH = "GetPagedSearchCBD"   # used to find the token-bearing request

# The server silently caps any single search at this many records.
CAP = 2000
# Records per page when paging a search.
PAGE_SIZE = 400
# Keep only seasons whose trailing 2-digit year is >= this (e.g. 25 -> 2025+).
MIN_SEASON_YEAR = 25


class NikeACSAutomator:
    def __init__(self, email, password):
        """Set up the Chrome driver, download folder, and performance logging."""
        self.email = email
        self.password = password

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")

        base_download_dir = os.path.join(os.getcwd(), "downloads")
        date_stamp = datetime.now().strftime("%Y-%m-%d")
        self.download_dir = os.path.join(base_download_dir, date_stamp)
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        print(f"Download folder: {self.download_dir}")

        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        }
        options.add_experimental_option("prefs", prefs)

        # Enable Chrome performance logging so we can read request headers (for the token).
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        options.add_experimental_option("perfLoggingPrefs", {"enableNetwork": True})

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
        self.wait = WebDriverWait(self.driver, 20)

        # Collects lines for the run log written at the end of fetch_all_records.
        self._log_lines = []

    def _log(self, msg=""):
        """Print to console AND store for the run log file."""
        print(msg)
        self._log_lines.append(str(msg))

    # ------------------------------------------------------------------ #
    # Login + UI setup (unchanged from before)
    # ------------------------------------------------------------------ #
    def login(self):
        """Log into ACS via Microsoft SSO using the email/password from .env."""
        print("Navigating to Nike ACS...")
        self.driver.get("https://acs.partner.nike-cloud.com/")

        print("Entering email...")
        email_input = self.wait.until(EC.element_to_be_clickable((
            By.XPATH, "//input[@type='text' or contains(@name, 'loginfmt')]"
        )))
        email_input.send_keys(self.email)

        next_btn = self.wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[@type='submit' or contains(text(), 'Next')]"
        )))
        next_btn.click()

        print("Entering password...")
        password_input = self.wait.until(EC.element_to_be_clickable((
            By.XPATH, "//input[@type='password' or contains(@name, 'passwd')]"
        )))
        password_input.send_keys(self.password)

        verify_btn = self.wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//button[@type='submit' or @value='Sign in' "
            "or @value='ตรวจสอบ' or @value='Verify']"
        )))
        verify_btn.click()

        try:
            remind_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//*[contains(text(), 'เตือนฉันในภายหลัง') "
                    "or contains(text(), 'Remind me later') "
                    "or @id='KmsiCheckboxField']"
                ))
            )
            remind_btn.click()
            print("Clicked 'Remind me later'")
        except Exception:
            print("No 'Remind me later' prompt appeared.")

        print("Login completed.")
        time.sleep(5)

    def set_filters(self):
        """Open the search panel and select the CBD Status filters in the UI."""
        print("Setting filters...")
        print("Opening search criteria...")
        search_btn = self.driver.find_element(
            By.XPATH, "//eds-icon-button[@label='Search Criteria']//button"
        )
        self.driver.execute_script("arguments[0].click();", search_btn)
        time.sleep(1)

        try:
            cbd_element = self.driver.find_element(
                By.XPATH, "//eds-select[@label='CBD Status']"
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", cbd_element
            )
            time.sleep(0.3)

            self.driver.execute_script("""
                var el = document.querySelector("eds-select[label='CBD Status'] .eds-select__control");
                el.dispatchEvent(new MouseEvent("mousedown", {bubbles: true}));
            """)
            print("Clicked CBD Status dropdown")
            time.sleep(1)

            for option_index in [1, 2, 3]:
                try:
                    option = self.wait.until(EC.element_to_be_clickable((
                        By.XPATH, f"//div[contains(@id, 'option-{option_index}')]"
                    )))
                    self.driver.execute_script("arguments[0].click();", option)
                    print(f"Selected option-{option_index}")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Could not select option-{option_index}: {e}")

            self.driver.find_element(By.TAG_NAME, 'body').click()
            time.sleep(0.5)

        except Exception as e:
            print(f"Failed to select CBD statuses: {e}")

    def set_CBD(self):
        """Click the CBD search button to run a real search (fires the API call
        whose Authorization header we later capture)."""
        print("Click CBD Button...")
        self.driver.execute_script("""
            var el = document.querySelector("button.split-btn-main");
            el.click();
        """)
        print("Clicked CBD button")
        time.sleep(20)

    def set_records(self):
        """Set the UI rows-per-page dropdown to 500 (cosmetic; the API fetch
        below ignores the UI page size)."""
        print("Click Show More Record")
        try:
            from selenium.webdriver.support.ui import Select

            rec_select = self.wait.until(EC.element_to_be_clickable((
                By.XPATH, "//select[contains(@class, 'rows-per-page-select')]"
            )))
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", rec_select
            )
            time.sleep(0.3)

            select = Select(rec_select)
            select.select_by_visible_text("500")
            print("Selected: 500 records")
            time.sleep(0.5)

        except Exception as e:
            print(f"Could not select 500 records: {e}")

    # ------------------------------------------------------------------ #
    # Token capture (unchanged)
    # ------------------------------------------------------------------ #
    def _capture_token(self, timeout=30):
        """
        Read Chrome's performance logs to find the app's own GetPagedSearchCBD
        request and pull its Authorization header, so we can reuse the token.
        """
        print("Capturing auth token from network logs...")
        match_ids = set()
        extra_headers = {}
        end = time.time() + timeout

        while time.time() < end:
            logs = self.driver.get_log("performance")
            for entry in logs:
                try:
                    msg = json.loads(entry["message"])["message"]
                except Exception:
                    continue

                method = msg.get("method")
                params = msg.get("params", {})
                rid = params.get("requestId")

                if method == "Network.requestWillBeSent":
                    url = params.get("request", {}).get("url", "")
                    if ENDPOINT_MATCH in url:
                        match_ids.add(rid)
                        headers = params.get("request", {}).get("headers", {})
                        auth = headers.get("Authorization") or headers.get("authorization")
                        if auth:
                            print("Token captured.")
                            return auth

                elif method == "Network.requestWillBeSentExtraInfo":
                    headers = params.get("headers", {})
                    if headers:
                        extra_headers[rid] = headers

                for mid in list(match_ids):
                    h = extra_headers.get(mid)
                    if h:
                        auth = h.get("Authorization") or h.get("authorization")
                        if auth:
                            print("Token captured.")
                            return auth

            time.sleep(1)

        raise RuntimeError(
            "Could not capture Authorization token from network logs within timeout. "
            "Make sure the search actually ran (set_CBD) before this step."
        )

    # ------------------------------------------------------------------ #
    # Low-level HTTP helpers (in-browser fetch, reuses session + token)
    # ------------------------------------------------------------------ #
    _POST_SCRIPT = """
        const [url, body, token] = arguments;
        const done = arguments[arguments.length - 1];
        fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": token },
            credentials: "include",
            body: body
        })
        .then(r => r.json().then(data => ({ status: r.status, data })))
        .then(res => done({ ok: res.status === 200, status: res.status, data: res.data }))
        .catch(err => done({ ok: false, error: err.toString() }));
    """

    _GET_SCRIPT = """
        const [url, token] = arguments;
        const done = arguments[arguments.length - 1];
        fetch(url, {
            method: "GET",
            headers: { "Authorization": token },
            credentials: "include"
        })
        .then(r => r.json().then(data => ({ status: r.status, data })))
        .then(res => done({ ok: res.status === 200, status: res.status, data: res.data }))
        .catch(err => done({ ok: false, error: err.toString() }));
    """

    def _build_payload(self, seasons, dimensions):
        """Build the search-filter JSON body for a given seasons/dimensions combo."""
        return {
            "seasons": seasons, "styleNumbers": [], "factoryCodes": [],
            "dimensions": dimensions, "developerEmails": [],
            "cbdStatuses": CBD_STATUSES,
            "colorwayCodes": None, "createdDateRange": [], "dataStages": [],
            "mmUploads": [], "mscCodes": [], "poColorwayCodes": None,
            "reviewStatuses": None, "sampleRounds": None, "subCategories": None,
        }

    def _fetch_page(self, token, seasons, dimensions, page, size):
        """Fetch a single page for a filter combination; return the JSON dict."""
        url = f"{BASE_URL}?page={page}&size={size}"
        payload = self._build_payload(seasons, dimensions)
        res = self.driver.execute_async_script(
            self._POST_SCRIPT, url, json.dumps(payload), token
        )
        if not res.get("ok"):
            raise RuntimeError(
                f"Fetch failed (seasons={seasons}, dims={dimensions}, page={page}): "
                f"status={res.get('status')} error={res.get('error')}"
            )
        return res["data"]

    def _fetch_filter(self, token, seasons, dimensions=None):
        """
        Fetch every available page for one filter combination.
        Returns (count, records). If count >= CAP, records is truncated to the
        first CAP rows (the server won't return more for this single search).
        """
        dimensions = dimensions or []
        page = 1
        total_pages = None
        count = 0
        records = []

        while True:
            data = self._fetch_page(token, seasons, dimensions, page, PAGE_SIZE)
            count = data.get("count", 0)
            records.extend(data.get("cbdSearchResults") or [])

            if total_pages is None:
                total_pages = (count + PAGE_SIZE - 1) // PAGE_SIZE   # ceil

            if total_pages == 0 or page >= total_pages:
                break
            page += 1
            time.sleep(0.3)   # gentle pacing

        return count, records

    def _get_seasons(self, token):
        """Fetch the full season list, keep only season year >= MIN_SEASON_YEAR."""
        print("Fetching season list...")
        res = self.driver.execute_async_script(self._GET_SCRIPT, SEASON_URL, token)
        if not res.get("ok"):
            raise RuntimeError(
                f"Failed to fetch seasons: status={res.get('status')} "
                f"error={res.get('error')}"
            )
        raw = res["data"] or []
        seasons = []
        for item in raw:
            s = item.get("season") if isinstance(item, dict) else item
            if not s:
                continue
            try:
                year = int(str(s)[-2:])        # trailing 2 digits, e.g. "SP27" -> 27
            except ValueError:
                continue
            if year >= MIN_SEASON_YEAR:
                seasons.append(s)
        seasons = sorted(set(seasons))
        print(f"Kept {len(seasons)} season(s) (year >= {MIN_SEASON_YEAR}): {seasons}")
        return seasons

    @staticmethod
    def _add(records, all_records, seen):
        """Add records not already seen (dedupe by cbdid). Return count added."""
        n = 0
        for r in records:
            key = r.get("cbdid")
            if key not in seen:
                seen.add(key)
                all_records.append(r)
                n += 1
        return n

    # ------------------------------------------------------------------ #
    # Main fetch: two-pass season / dimension split
    # ------------------------------------------------------------------ #
    def fetch_all_records(self):
        """
        Main routine: capture the token, get the season list, then pull every
        record using a two-pass season/dimension split to beat the 2000 cap.
        Pass 1 fetches each season (keeping capped ones' partial data and
        harvesting dimension values); Pass 2 re-fetches each capped season
        dimension by dimension. Everything is deduped by cbdid, written to CSV,
        and summarized in a log file.
        """
        token = self._capture_token()
        self.driver.set_script_timeout(60)

        run_start = datetime.now()
        seasons = self._get_seasons(token)

        all_records = []
        seen = set()          # cbdids already collected
        master_dims = set()   # every dimension value we encounter
        capped_seasons = []   # seasons that hit the 2000 cap (need splitting)

        # Per-season summary for the log.
        # season -> {"count": int, "capped": bool, "added": int, "dims": [(dim, count, added, capped)]}
        summary = {}

        # ---- Pass 1: fetch each season; keep what we get; note capped ones ----
        self._log("\n=== Pass 1: fetch by season ===")
        for s in seasons:
            count, recs = self._fetch_filter(token, [s])

            # Harvest dimensions from whatever we got (even capped samples).
            for r in recs:
                d = r.get("dimension")
                if d:
                    master_dims.add(d)

            # Keep the records regardless — dedupe handles overlap with Pass 2.
            added = self._add(recs, all_records, seen)
            capped = count >= CAP
            summary[s] = {"count": count, "capped": capped, "added": added, "dims": []}

            if capped:
                capped_seasons.append(s)
                self._log(f"  {s}: count={count} -> CAPPED (will split), +{added} new")
            else:
                self._log(f"  {s}: count={count} -> fetched whole, +{added} new")

        # ---- Pass 2: split each capped season by dimension ----
        if capped_seasons:
            dims = sorted(master_dims)
            self._log(f"\n=== Pass 2: split {len(capped_seasons)} capped season(s) "
                      f"by {len(dims)} dimension(s) ===")
            for s in capped_seasons:
                self._log(f"\n  Season {s}:")
                for d in dims:
                    count, recs = self._fetch_filter(token, [s], [d])
                    added = self._add(recs, all_records, seen)
                    dim_capped = count >= CAP
                    summary[s]["dims"].append((d, count, added, dim_capped))
                    flag = "  <-- STILL CAPPED, needs finer split!" if dim_capped else ""
                    self._log(f"    {s} / {d}: count={count}, +{added} new{flag}")
                    time.sleep(0.3)

        self._log(f"\nCollected {len(all_records)} unique records total.")
        self._write_csv(all_records)

        # ---- Write the summary log file ----
        self._write_log(summary, len(all_records), run_start)

    def _write_log(self, summary, total_unique, run_start):
        """Write a human-readable run summary to a log file in the download folder."""
        run_end = datetime.now()
        lines = []
        lines.append("=" * 60)
        lines.append("ACS FETCH RUN SUMMARY")
        lines.append(f"Started:  {run_start:%Y-%m-%d %H:%M:%S}")
        lines.append(f"Finished: {run_end:%Y-%m-%d %H:%M:%S}")
        lines.append(f"Duration: {run_end - run_start}")
        lines.append(f"CBD statuses: {', '.join(CBD_STATUSES)}")
        lines.append(f"Seasons kept: year >= {MIN_SEASON_YEAR}")
        lines.append("=" * 60)
        lines.append("")

        # Per-season breakdown.
        grand_reported = 0   # sum of season 'count' as reported by the server
        for s in sorted(summary):
            info = summary[s]
            status = "CAPPED" if info["capped"] else "OK"
            grand_reported += info["count"]
            lines.append(f"Season {s}: reported={info['count']} "
                         f"new={info['added']} [{status}]")
            # If it was split, list each dimension.
            if info["dims"]:
                for d, c, added, dim_capped in info["dims"]:
                    mark = "  !! STILL CAPPED" if dim_capped else ""
                    lines.append(f"    - {d}: reported={c} new={added}{mark}")
            lines.append("")

        lines.append("=" * 60)
        lines.append(f"TOTAL unique records written: {total_unique}")
        lines.append(f"(Sum of season 'reported' counts, "
                     f"incl. capped-at-{CAP}: {grand_reported})")

        # Flag any dimension that still capped.
        still_capped = [
            (s, d) for s in summary for (d, c, a, dc) in summary[s]["dims"] if dc
        ]
        if still_capped:
            lines.append("")
            lines.append("WARNING - these season/dimension combos STILL hit the cap "
                         "and may be missing records:")
            for s, d in still_capped:
                lines.append(f"    - {s} / {d}")
            lines.append("Consider adding a finer split (e.g. factory code) for these.")
        lines.append("=" * 60)

        stamp = run_start.strftime("%Y-%m-%d_%H%M%S")
        log_path = os.path.join(self.download_dir, f"fetch_log_{stamp}.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Wrote run log to {log_path}")

    def _write_csv(self, records):
        """Map JSON fields to the desired columns and write one CSV."""
        rows = []
        for rec in records:
            row = {}
            for col, json_field in FIELD_MAP.items():
                val = rec.get(json_field)
                row[col] = "" if val is None else val
            rows.append(row)

        df = pd.DataFrame(rows, columns=list(FIELD_MAP.keys()))
        out_path = os.path.join(self.download_dir, "CBD_AllRecords.csv")
        df.to_csv(out_path, index=False)
        print(f"Wrote {len(df)} rows to {out_path}")

    def run(self):
        """Orchestrate the whole flow (login -> filters -> search -> fetch) and
        always close the browser at the end, even on error."""
        try:
            self.login()
            self.set_filters()
            self.set_CBD()          # triggers the real search -> token capturable
            self.set_records()
            self.fetch_all_records()
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            print("Closing browser...")
            self.driver.quit()


if __name__ == "__main__":
    automator = NikeACSAutomator(ACS_EMAIL, ACS_PASSWORD)
    automator.run()