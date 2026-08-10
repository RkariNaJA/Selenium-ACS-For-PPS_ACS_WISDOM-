# For dbo.ACS => PPS,ACS,WISDOM

# ACS — Nike CBD Data Automation

Automates the process of logging into the **Nike ACS (Apparel Cost Sheet)** portal, fetching CBD (Cost Breakdown Detail) search results, cleaning the data, and loading it into a target destination via an SSIS package.

---

## 📁 Project Structure

```
ACS/
├── FlowACS.py        # Orchestrator — runs the full pipeline in sequence
├── FetchData.py      # Selenium + API automation to fetch all CBD records
├── DownloadCSV.py    # Alternative approach: downloads CSV page-by-page via UI
├── CleanFile.py      # Cleans downloaded CSV and triggers SSIS package
└── downloads/        # Auto-created; stores daily download folders (YYYY-MM-DD/)
```

---

## 2k Record LOGIC(Bypass the Export CSV button)

**\_capture_token** — grabs the login token. The website's data endpoint requires an Authorization: **Bearer token to answer requests**. Rather than you copying that secret by hand, this function watches Chrome's network log, finds the request the app itself already made to the data endpoint, and reads the token off it. It keeps checking the log for up to 30 seconds until it finds it, then returns it.

**fetch_all_records** — uses that token to pull everything. It calls \_capture_token to get the token, **then repeatedly asks the data endpoint for records one page at a time (400 per page)**. From the first response it learns the total count (2000) and calculates how many pages that is (5). It loops through all pages, piling up the records, then hands the full set to \_write_csv to save as one clean CSV.

The big picture: instead of fighting the broken "Export CSV" button that only ever gave you the first 500, you go straight to the data source the website uses internally — borrow its token, ask for every page, and build your own complete file of all 2000 records.

## ⚙️ How It Works

```
FlowACS.py
    └─▶ FetchData.py   →  Login to Nike ACS  →  Set filters (CBD Status)
                        →  Trigger search  →  Capture Bearer token
                        →  Fetch all pages via API  →  Write CBD_AllRecords.csv
    └─▶ CleanFile.py   →  Read & clean CSV  →  Save sorted Excel (archived + target)
                        →  Run SSIS package to load into database
```

### Step 1 — `FetchData.py`

- Logs into `https://acs.partner.nike-cloud.com/` using Microsoft SSO (email + password from `.env`)
- Opens "Search Criteria" and selects CBD statuses: **Q-QRMDS**, **Q-CRMDS**, **C**
- Clicks the CBD search button to trigger a real network request
- Captures the **Bearer token** from Chrome's performance logs (no proxy needed)
- Calls `GetPagedSearchCBD` API directly (400 records/page) until all records are collected
- Writes output to `downloads/YYYY-MM-DD/CBD_AllRecords.csv`

### Step 2 — `CleanFile.py`

- Reads all CSV files from today's download folder
- Keeps only the required columns (see [Columns](#-output-columns))
- Saves an archived Excel file: `CBD_SearchResults_YYYY-MM-DD_cleaned.xlsx`
- Copies a fixed-name file to the ACS target folder: `CBD_SearchResults_cleaned.xlsx`
- Executes the configured SSIS package via `DTExec.exe`

### `DownloadCSV.py` _(Alternative)_

- An earlier approach that downloads CSV page-by-page through the UI (Export CSV button)
- Useful as a fallback if the API token capture approach fails

### `FlowACS.py` _(Orchestrator)_

- Reads the list of scripts to run from `.env` (`ACS-FLOW_SCRIPTS`)
- Runs each script sequentially using `subprocess`
- Writes a summary log to the Desktop after completion

---

## 🔧 Environment Variables (`.env`)

| Variable             | Description                                                               |
| -------------------- | ------------------------------------------------------------------------- |
| `ACS_USER`           | Nike ACS login email                                                      |
| `ACS_PASS`           | Nike ACS login password                                                   |
| `ASC_FOLDER_PATH`    | Target folder path for the cleaned Excel output                           |
| `ASC_SSIS_PATH`      | Full path to the `.dtsx` SSIS package file                                |
| `ACS-FLOW_BASE_PATH` | Base directory where ACS scripts are located                              |
| `ACS-FLOW_SCRIPTS`   | Comma-separated list of scripts to run (e.g. `FetchData.py,CleanFile.py`) |
| `ACS-FLOW_LOG_FILE`  | Log filename saved to Desktop (default: `flow_Log.txt`)                   |
| `ACS-FLOW_RUN_ID`    | Label used in the log to identify this run                                |
| `DESKTOP_PATH`       | Desktop path for log output (defaults to `~/Desktop`)                     |

### Example `.env`

```env
ACS_USER=your.email@partner.nike.com
ACS_PASS=your_password

ASC_FOLDER_PATH=D:\Filepackage\python\PPS,ACS,WISDOM\ACS\downloads
ASC_SSIS_PATH=D:\SSIS\ACS_Load.dtsx

ACS-FLOW_BASE_PATH=D:\Filepackage\python\PPS,ACS,WISDOM\ACS
ACS-FLOW_SCRIPTS=FetchData.py, CleanFile.py
ACS-FLOW_LOG_FILE=ACS_flow_Log.txt
ACS-FLOW_RUN_ID=ACS-DAILY
DESKTOP_PATH=C:\Users\YourName\Desktop
```

---

## 📦 Output Columns

The following columns are extracted and kept in the cleaned output:

| Column          | API Field         |
| --------------- | ----------------- |
| `CBDID`         | `cbdid`           |
| `Season`        | `season`          |
| `Style Number`  | `styleNo`         |
| `Modified`      | `modifiedDate`    |
| `Created`       | `createdDate`     |
| `Colorway Code` | `colorwayCode`    |
| `Factory Code`  | `factoryCode`     |
| `Final FOB`     | `finalFOB`        |
| `ExtSzFOB`      | `extendedSizeFOB` |

---

## 📋 Requirements

- **Python 3.8+**
- **Google Chrome** (latest)
- **Microsoft SQL Server** with `DTExec.exe` (for SSIS execution)

### Python Packages

```
selenium
webdriver-manager
pandas
openpyxl
python-dotenv
```

Install with:

```bash
pip install selenium webdriver-manager pandas openpyxl python-dotenv
```

---

## 🚀 Usage

### Run full pipeline (recommended)

```bash
python FlowACS.py
```

### Run individual scripts

```bash
# Step 1: Fetch data from ACS
python FetchData.py

# Step 2: Clean and load
python CleanFile.py
```

---

## 📝 Notes

- Downloads are organized by date under `downloads/YYYY-MM-DD/`
- The Bearer token is captured automatically from Chrome's performance log — no extra proxy or network tool needed
- If the SSIS path is not configured, `CleanFile.py` will skip the SSIS step without failing
- `DTExec.exe` is searched in common SQL Server 140/150 installation paths automatically
