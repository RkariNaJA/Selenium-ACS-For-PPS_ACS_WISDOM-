import time
import glob
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

    def fetch_all_records(self):
        """
        Pull all records directly from the GetPagedSearchCBD endpoint,
        reusing the browser's logged-in session. Writes one clean CSV.
        """
        print("Fetching all records from the API...")

        # Search-filter body — mirrors what the UI sends.
        payload = {
            "seasons": [], "styleNumbers": [], "factoryCodes": [], "dimensions": [],
            "developerEmails": [], "cbdStatuses": CBD_STATUSES,
            "colorwayCodes": None, "createdDateRange": [], "dataStages": [],
            "mmUploads": [], "mscCodes": [], "poColorwayCodes": None,
            "reviewStatuses": None, "sampleRounds": None, "subCategories": None,
        }

        base_url = ("https://acs-service.partner.nike-cloud.com"
                    "/api/CBDSearch/GetPagedSearchCBD")
        size = 400

        # Runs a single page fetch inside the page context (uses session cookies).
        fetch_script = """
            const [url, body] = arguments;
            const done = arguments[arguments.length - 1];   // Selenium async callback
            fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: body
            })
            .then(r => r.json())
            .then(data => done({ ok: true, data }))
            .catch(err => done({ ok: false, error: err.toString() }));
        """

        self.driver.set_script_timeout(60)

        all_records = []
        page = 1
        total_pages = None

        while True:
            url = f"{base_url}?page={page}&size={size}"
            result = self.driver.execute_async_script(
                fetch_script, url, json.dumps(payload)
            )

            if not result.get("ok"):
                raise RuntimeError(
                    f"Fetch failed on page {page}: {result.get('error')}"
                )

            data = result["data"]
            records = data.get("cbdSearchResults") or []
            all_records.extend(records)

            # Work out how many pages there are, from the first response.
            if total_pages is None:
                count = data.get("count", 0)
                total_pages = (count + size - 1) // size   # ceil division
                print(f"Total records: {count}  ->  {total_pages} page(s)")

            print(f"  Page {page}/{total_pages}: got {len(records)} records "
                  f"(running total {len(all_records)})")

            if total_pages == 0 or page >= total_pages:
                break
            page += 1
            time.sleep(0.3)   # gentle pacing

        print(f"Fetched {len(all_records)} records total.")
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
            self.set_CBD()
            self.set_records()          # optional; fetch ignores the UI page size
            self.fetch_all_records()    # replaces Export500Record + CSV combining
        except Exception as e:
            print(f"Error occurred: {e}")
        finally:
            print("Closing browser...")
            self.driver.quit()


if __name__ == "__main__":
    automator = NikeACSAutomator(ACS_EMAIL, ACS_PASSWORD)
    automator.run()