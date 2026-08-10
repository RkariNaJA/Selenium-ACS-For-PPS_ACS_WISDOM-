# ACS — Nike CBD Data Automation(For ACS,PPS,WISDOM)

Automates the process of logging into the **Nike ACS (Apparel Cost Sheet)** portal, fetching CBD (Cost Breakdown Detail) search results, cleaning the data, and loading it into a target destination via an SSIS package.

---

## The Problem

The ACS search interface has two hard limits stacked on top of each other:

1. **The "Export CSV" button only ever exports the first 500 records** of a result set, no matter which page you're viewing. Clicking through pages and exporting each one just re-downloads the same first 500.
2. **The underlying data API caps any single search at 2000 records.** Even going straight to the API, one search returns at most 2000 rows — the rest are silently dropped. In reality there are far more than 2000 records (7,000+ across current seasons).

So we need to (a) bypass the broken Export button by calling the data API directly, and (b) break each search into smaller slices that each stay under the 2000 cap, then glue all the slices back together into one complete file.

---

## 📁 Project Structure

```
ACS/
├── FlowACS.py        # Orchestrator — runs the full pipeline in sequence
├── FetchData.py      # Selenium + API automation to fetch ALL CBD records (season-split)
├── DownloadCSV.py    # Alternative approach: downloads CSV page-by-page via UI
├── CleanFile.py      # Cleans downloaded CSV and triggers SSIS package
└── downloads/        # Auto-created; stores daily download folders (YYYY-MM-DD/)
```

---

## Bypassing the Export button (the token trick)

**\_capture_token** — grabs the login token. The website's data endpoint requires an `Authorization: Bearer` token to answer requests. Rather than copying that secret by hand, this function watches Chrome's network log, **finds the request the app itself already made to the data endpoint, and reads the token off it**. It keeps checking the log for up to 30 seconds until it finds it, then returns it. No proxy or extra tools needed.

Once we have the token, we can call the site's internal data API directly instead of fighting the Export CSV button.

---

## 📌📌 Getting past the 2000 cap (Two-Pass: Season → Dimension) 📌📌

Think of it this way: you still only want papers from three specific folders (the statuses). But those three folders together hold 7,000+ papers and the **machine only gives you 2,000 at a time.**
So you don't stop filtering by folder — you additionally say **"give me the three folders, but only for Spring 2027,"** then **"only Fall 2026,"** etc. Every grab is still restricted to your three statuses; **you're just also slicing by season so each grab is small enough to come back whole.** Right now the largest Season + Dimension slice ≈ **917 records**.

The status filter (`Q-QRMDS`, `Q-CRMDS`, `C`) is **always applied** — every request in both passes includes it. We beat the cap by _tightening_ the search (adding season, then dimension), never by loosening the status filter.

**First**, get the drawer list: fetch all seasons from the `GetAllSeasonInformation` reference endpoint and keep only **season 25 and newer** (SP25, SU25, FA25, HO25, and up) — older seasons are ignored.

Then the work happens in two passes, matching the console output:

### 🟦 Pass 1 — Fetch by season ⚠️

Go season by season. For each kept season, run the search (still filtered by the 3 statuses) and page through it 400 at a time:

- **Under 2000** → the season came back whole. Keep all its records.
- **Exactly 2000 (capped)** → the season itself is too big to trust whole. Keep the first 2000 anyway (dedup makes this safe), and mark the season for Pass 2.

While doing this, Pass 1 also **harvests every dimension value** it sees (BASKETBALL LICENSED, WOMENS, KNIT, etc.) to build the list used in Pass 2.

### 🟩 Pass 2 — Split the capped seasons by dimension ⚠️

For each season flagged as capped in Pass 1, re-run the search once **per dimension** (status + season + dimension). Each of these slices is small enough to return complete (largest ≈ 917), so together they recover the records the capped season was hiding.

- **Safety alarm:** if any season + dimension combo _still_ hits 2000, the script prints a loud `STILL CAPPED` warning (console + log file) instead of silently losing data — the signal that an even finer split (e.g. factory code) is needed.

### 🔁 Throughout both passes

- **De-duplicate by `cbdid`.** Because Pass 1 (capped seasons' first 2000) and Pass 2 (per-dimension slices) overlap, every record's unique ID is tracked so each is written only once.
- **One clean CSV** is saved at the end with just the required columns, plus a timestamped **run-log** summarizing each season's count and each dimension breakdown.

**Trade-off:** because the data is now fetched season by season (and dimension by dimension for large seasons) instead of one big grab, the script makes many more requests. A full run takes a few minutes instead of a few seconds — the price of getting _all_ the data instead of just the first 2000.

---

## ⚙️ How It Works

```
FlowACS.py
    └─▶ FetchData.py   →  Login to Nike ACS  →  Set filters (CBD Status)
                        →  Trigger search  →  Capture Bearer token
                        →  Get season list (keep season 25+)
                        →  Fetch each season; split capped seasons by dimension
                        →  De-dupe by cbdid  →  Write CBD_AllRecords.csv
    └─▶ CleanFile.py   →  Read & clean CSV  →  Save sorted Excel (archived + target)
                        →  Run SSIS package to load into database
```

### Step 1 — `FetchData.py`

- Logs into `https://acs.partner.nike-cloud.com/` using Microsoft SSO (email + password from `.env`)
- Opens "Search Criteria" and selects CBD statuses: **Q-QRMDS**, **Q-CRMDS**, **C**
- Clicks the CBD search button to trigger a real network request
- Captures the **Bearer token** from Chrome's performance logs (no proxy needed)
- Pulls the season list from `GetAllSeasonInformation` and keeps **season 25 and newer**
- For each kept season, calls `GetPagedSearchCBD` (400 records/page):
  - fetches the season whole if it's under the 2000 cap
  - splits it by **dimension** if it hits the cap
- De-duplicates records by `cbdid` and writes `downloads/YYYY-MM-DD/CBD_AllRecords.csv`

### Step 2 — `CleanFile.py`

- Reads all CSV files from today's download folder
- Keeps only the required columns (see [Columns](#-output-columns))
- Saves an archived Excel file: `CBD_SearchResults_YYYY-MM-DD_cleaned.xlsx`
- Copies a fixed-name file to the ACS target folder: `CBD_SearchResults_cleaned.xlsx`
- Executes the configured SSIS package via `DTExec.exe`

### `DownloadCSV.py` _(Alternative)_

- An earlier approach that downloads CSV page-by-page through the UI (Export CSV button)
- Limited to the first 500 records; kept only as a fallback reference

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
- The 2000-record cap is worked around by fetching season by season (and dimension by dimension for large seasons); records are de-duplicated by `cbdid`
- A full run makes many API calls and takes a few minutes — this is expected
- Watch the console for any "STILL CAPPED" warning: it means a season + dimension combo exceeded 2000 and needs a finer split
- If the SSIS path is not configured, `CleanFile.py` will skip the SSIS step without failing
- `DTExec.exe` is searched in common SQL Server 140/150 installation paths automatically
