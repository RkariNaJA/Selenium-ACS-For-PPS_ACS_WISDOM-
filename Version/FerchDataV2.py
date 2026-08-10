# Fetch Data from API For 2000 Record
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

# The data endpoint (path fragment used to match the captured request).
ENDPOINT_MATCH = "GetPagedSearchCBD"
BASE_URL = ("https://acs-service.partner.nike-cloud.com"
            "/api/CBDSearch/GetPagedSearchCBD")


class NikeACSAutomator:
    def __init__(self, email, password):
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

    def login(self):
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
        print("Click CBD Button...")
        self.driver.execute_script("""
            var el = document.querySelector("button.split-btn-main");
            el.click();
        """)
        print("Clicked CBD button")
        time.sleep(20)

    def set_records(self):
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

    # For Capturing Bearer Token from ACS website
    def _capture_token(self, timeout=30):
        """
        Read Chrome's performance logs to find the app's own GetPagedSearchCBD
        request and pull its Authorization header, so we can reuse the  token.
        No proxy or extra packages needed — just the built-in performance log.
        """
        print("Capturing auth token from network logs...")

        match_ids = set()          # requestIds of requests whose URL is our endpoint
        extra_headers = {}         # requestId -> headers, collected from ExtraInfo events
        end = time.time() + timeout  # stop polling once this deadline passes

        # Keep reading the log until we find the token or run out of time.
        while time.time() < end:
            # get_log returns all performance events since the last call (then clears them).
            logs = self.driver.get_log("performance")

            for entry in logs:
                # Each entry is a JSON string; unwrap it to the actual CDP message.
                try:
                    msg = json.loads(entry["message"])["message"]
                except Exception:
                    continue  # skip anything that isn't valid JSON

                method = msg.get("method")          # which network event this is
                params = msg.get("params", {})      # the event's data
                rid = params.get("requestId")       # unique id linking related events

                # Event fired when the browser is about to send a request.
                if method == "Network.requestWillBeSent":
                    url = params.get("request", {}).get("url", "")
                    # Only care about requests going to our data endpoint.
                    if ENDPOINT_MATCH in url:
                        match_ids.add(rid)  # remember this request's id
                        headers = params.get("request", {}).get("headers", {})
                        # Grab the bearer token if it's already on this event.
                        auth = headers.get("Authorization") or headers.get("authorization")
                        if auth:
                            print("Token captured.")
                            return auth

                # Sometimes Chrome reports the real headers in a separate ExtraInfo event.
                elif method == "Network.requestWillBeSentExtraInfo":
                    headers = params.get("headers", {})
                    if headers:
                        extra_headers[rid] = headers  # stash by id to match up later

                # Reconcile: if one of our matched requests got its token via ExtraInfo,
                # pair them up by requestId and return the token.
                for mid in list(match_ids):
                    h = extra_headers.get(mid)
                    if h:
                        auth = h.get("Authorization") or h.get("authorization")
                        if auth:
                            print("Token captured.")
                            return auth

            time.sleep(1)  # wait a beat, then read the log again

        # We never saw an authorized request within the time limit.
        raise RuntimeError(
            "Could not capture Authorization token from network logs within timeout. "
            "Make sure the search actually ran (set_CBD) before this step."
        )

    # Use the token to ask the data endpoint for all records one page at a time
    def fetch_all_records(self):
        """
        Pull all records directly from GetPagedSearchCBD, reusing the captured
        bearer token. Writes one clean CSV.
        """
        # First get the auth token from the app's own request (see _capture_token).
        token = self._capture_token()

        print("Fetching all records from the API...")

        # The search-filter body sent with each request — mirrors what the UI sends.
        # cbdStatuses must match the filters chosen in set_filters().
        payload = {
            "seasons": [], "styleNumbers": [], "factoryCodes": [], "dimensions": [],
            "developerEmails": [], "cbdStatuses": CBD_STATUSES,
            "colorwayCodes": None, "createdDateRange": [], "dataStages": [],
            "mmUploads": [], "mscCodes": [], "poColorwayCodes": None,
            "reviewStatuses": None, "sampleRounds": None, "subCategories": None,
        }
        size = 400  # records requested per page

        # JavaScript that runs one POST inside the page (so it shares the login session).
        # It sends cookies (credentials) AND the bearer token, then hands the JSON
        # response back to Python via Selenium's async callback (done).
        fetch_script = """
            const [url, body, token] = arguments;
            const done = arguments[arguments.length - 1];   // Selenium async callback
            fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": token
                },
                credentials: "include",
                body: body
            })
            .then(r => r.json().then(data => ({ status: r.status, data })))
            .then(res => done({ ok: res.status === 200, status: res.status, data: res.data }))
            .catch(err => done({ ok: false, error: err.toString() }));
        """

        self.driver.set_script_timeout(60)  # allow up to 60s per fetch

        all_records = []     # accumulates records across all pages
        page = 1             # current page number
        total_pages = None   # figured out from the first response

        # Loop through every page until we've collected them all.
        while True:
            url = f"{BASE_URL}?page={page}&size={size}"
            # Run the fetch in the browser and get the parsed result back.
            result = self.driver.execute_async_script(
                fetch_script, url, json.dumps(payload), token
            )

            # If the request didn't return 200, stop and report the status/error.
            if not result.get("ok"):
                raise RuntimeError(
                    f"Fetch failed on page {page}: "
                    f"status={result.get('status')} error={result.get('error')}"
                )

            data = result["data"]
            records = data.get("cbdSearchResults") or []  # this page's records
            all_records.extend(records)                   # add them to the pile

            # On the first page, work out how many pages there are in total.
            if total_pages is None:
                count = data.get("count", 0)                 # total record count
                total_pages = (count + size - 1) // size     # round up: ceil(count/size)
                print(f"Total records: {count}  ->  {total_pages} page(s)")

            print(f"  Page {page}/{total_pages}: got {len(records)} records "
                  f"(running total {len(all_records)})")

            # Stop if there are no records, or we've reached the last page.
            if total_pages == 0 or page >= total_pages:
                break
            page += 1
            time.sleep(0.3)   # small pause between pages to be gentle on the server

        print(f"Fetched {len(all_records)} records total.")
        # Hand all collected records to the CSV writer.
        self._write_csv(all_records)

    def _write_csv(self, records):
        """Map JSON fields to the desired columns and write one CSV."""
        rows = []
        for rec in records:
            row = {}
            for col, json_field in FIELD_MAP.items():
                val = rec.get(json_field)
                row[col] = "" if val is None else val   # null -> blank cell
            rows.append(row)

        df = pd.DataFrame(rows, columns=list(FIELD_MAP.keys()))

        out_path = os.path.join(self.download_dir, "CBD_AllRecords.csv")
        df.to_csv(out_path, index=False)
        print(f"Wrote {len(df)} rows to {out_path}")

    def run(self):
        try:
            self.login()
            self.set_filters()
            self.set_CBD()          # triggers the real search -> token becomes capturable
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