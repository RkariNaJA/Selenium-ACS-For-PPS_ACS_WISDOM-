# Download CSV from Export CSV button For 500 Record
from selenium.webdriver.chrome import remote_connection
import time
import glob
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()


ACS_EMAIL = os.getenv("ACS_USER")
ACS_PASSWORD = os.getenv("ACS_PASS")

class NikeACSAutomator:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.downloaded_count = 0
        self.expected_count = 0
        
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
            "download.directory_upgrade": True  # Fixed key name
        }
        options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def login(self):
        print("Navigating to Nike ACS...")
        self.driver.get("https://acs.partner.nike-cloud.com/")
        
        print("Entering email...")
        email_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='text' or contains(@name, 'loginfmt')]")))
        email_input.send_keys(self.email)

        next_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' or contains(text(), 'Next')]")))
        next_btn.click()
        
        print("Entering password...")
        password_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='password' or contains(@name, 'passwd')]")))
        password_input.send_keys(self.password)
        
        verify_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' or @value='Sign in' or @value='ตรวจสอบ' or @value='Verify']")))
        verify_btn.click()
        
        try:
            remind_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'เตือนฉันในภายหลัง') or contains(text(), 'Remind me later') or @id='KmsiCheckboxField']"))
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
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cbd_element)
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
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", rec_select)
            time.sleep(0.3)
            
            select = Select(rec_select)
            select.select_by_visible_text("500")
            print("Selected: 500 records")
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Could not select 500 records: {e}")

    def wait_for_download(self, timeout=60):
        """Wait until .tmp file is gone and .csv file exists"""
        print("Waiting for download to complete...")
        end_time = time.time() + timeout
        while time.time() < end_time:
            tmp_files = glob.glob(os.path.join(self.download_dir, "*.tmp"))
            csv_files = glob.glob(os.path.join(self.download_dir, "*.csv"))
            if not tmp_files and csv_files:
                print(f"Download complete: {csv_files[-1]}")
                return csv_files[-1]
            time.sleep(0.5)
        raise TimeoutError("Download did not complete within timeout.")

    def Export500Record(self):
        page_num = 1                       # ← initialize

        while True:                        # ← the loop that was missing
            print(f"Downloading page {page_num}...")
            time.sleep(0.5)

            # Click the Export CSV button
            csv_btn = self.wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//button[@type='button' and contains(@class, 'eds-button--icon') "
                "and .//span[text()='Export CSV']]"
            )))
            csv_btn.click()
            print("Clicked export button...")

            self.wait_for_download()

            # Read the page indicator, e.g. "1 / 4"
            try:
                indicator = self.driver.find_element(
                    By.XPATH, "//span[@class='page-indicator']"
                ).text
                print(f"Page indicator: {indicator.strip()}")
            except Exception:
                pass

            # Find the Next Page button (target by title so we don't grab First/Prev)
            nxt_btn = self.driver.find_element(
                By.XPATH,
                "//button[@title='Next Page' "
                "and contains(@class, 'page-btn')]"
            )

            # Last page → Next is disabled → stop
            if not nxt_btn.is_enabled() or nxt_btn.get_attribute("disabled") is not None:
                print("Reached the final page. Done.")
                break                      # ← now legally inside the while loop

            nxt_btn.click()
            print("Clicked next page...")
            page_num += 1

            # Let the new page render before the next export
            self.wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//button[@type='button' and .//span[text()='Export CSV']]"
            )))



    def run(self):
        try:
            self.login()
            self.set_filters()
            self.set_CBD()
            self.set_records()
            self.Export500Record()
            
        except Exception as e:
            print(f"Error occurred: {e}")
            
        finally:
            # input("Press Enter to close the browser...")
            print("Closing browser...")
            self.driver.quit()

if __name__ == "__main__":
    email = ACS_EMAIL
    password = ACS_PASSWORD
    
    automator = NikeACSAutomator(email, password)
    automator.run()