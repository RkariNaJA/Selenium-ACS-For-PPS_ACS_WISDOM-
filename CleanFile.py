import pandas as pd
import glob
import os
import shutil
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# ================================
#    LOAD ENV VARIABLES
# ================================
load_dotenv()

# ACS Paths from .env
ASC_FOLDER_PATH = os.getenv("ASC_FOLDER_PATH", r"D:\Filepackage\python\PPS,ACS,WISDOM\ACS\downloads")
ASC_SSIS_PATH = os.getenv("ASC_SSIS_PATH")

KEEP_COLUMNS = [
    "CBDID",
    "Season",
    "Style Number",
    "Modified",
    "Created",
    "Colorway Code",
    "Factory Code",
    "Final FOB",
    "ExtSzFOB"
]

class SQLServerFinder:
    """Find valid DTExec.exe installation"""
    
    @staticmethod
    def find_dtexec():
        """Search for valid DTExec.exe in multiple locations"""
        
        possible_paths = [
            "D:\\Program Files\\Microsoft SQL Server\\150\\DTS\\Binn\\DTExec.exe",
            "C:\\Program Files\\Microsoft SQL Server\\150\\DTS\\Binn\\DTExec.exe",
            "D:\\Microsoft SQL Server\\150\\DTS\\Binn\\DTExec.exe",
            "C:\\Microsoft SQL Server\\150\\DTS\\Binn\\DTExec.exe",
            "D:\\Program Files\\Microsoft SQL Server\\140\\DTS\\Binn\\DTExec.exe",
            "C:\\Program Files\\Microsoft SQL Server\\140\\DTS\\Binn\\DTExec.exe",
        ]
        
        print("\n🔍 Searching for SQL Server DTExec.exe...")
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"✅ Found: {path}")
                return path
        
        print("❌ DTExec.exe not found in any location!")
        return None

def clean_csv():
    # Setup local download directories
    base_download_dir = os.path.join(os.getcwd(), "downloads")
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    download_dir = os.path.join(base_download_dir, date_stamp)

    # Find the latest CSV
    csv_files = glob.glob(os.path.join(download_dir, "*.csv"))
    if not csv_files:
        print(f"No CSV files found in: {download_dir}")
        return None

    # # csv_path = csv_files[-1]
    print(f"Found {len(csv_files)} CSV file(s) to process.")

    # Read and clean data
    all_dfs = [] # empty list to collect each file's cleaned DataFrame
    for csv_path in csv_files: # loop over every CSV path found in the folder  
        print(f"Processing: {csv_path}") 

        df = pd.read_csv(csv_path) # read this one CSV into a DataFrame

        missing = [col for col in KEEP_COLUMNS if col not in df.columns] # list the wanted columns that are NOT in this file
        if missing: # if that list isn't empty (some columns are missing)
            print(f"  Warning - columns not found in {os.path.basename(csv_path)}: {missing}") 

        existing_keep = [col for col in KEEP_COLUMNS if col in df.columns] # list the wanted columns that DO exist in this file
        df = df[existing_keep] # keep only those columns, drop the rest

    all_dfs.append(df) #Append every record into all_dfs for combinded afterward

    # Append all cleaned files into one
    combined_df = pd.concat(all_dfs, ignore_index=True)
    print(f"Combined {len(csv_files)} files into {len(combined_df)} total rows.")

    df = combined_df   # keep the same variable name for whatever comes next

    # 1. Save archived version (with date)
    original_filename = f"CBD_SearchResults_{date_stamp}_cleaned.xlsx"
    archive_path = os.path.join(download_dir, original_filename)
    combined_df.to_excel(archive_path, index=False)
    print(f"Saved archived file: {archive_path}")

    # 2. Copy to ACS Target Path (without date)
    target_filename = "CBD_SearchResults_cleaned.xlsx"
    
    try:
        # Use path from .env or default
        target_dir = ASC_FOLDER_PATH
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            print(f"Created target directory: {target_dir}")
            
        target_path = os.path.join(target_dir, target_filename)
        shutil.copy2(archive_path, target_path)
        print(f"Successfully copied to: {target_path}")
        return target_path
    except Exception as e:
        print(f"Error copying file to target path: {e}")
        return None

def run_ssis():
    print("\n" + "="*60)
    print("RUNNING SSIS PACKAGE")
    print("="*60)
    
    if not ASC_SSIS_PATH or ASC_SSIS_PATH == "SSIS Path is Missing":
        print("⚠️ SSIS Path not configured in .env yet. Skipping execution.")
        return

    try:
        dtexec_path = SQLServerFinder.find_dtexec()
        
        if not dtexec_path:
            print("⚠️ Cannot run SSIS - DTExec.exe not found. Is SQL Server installed?")
            return

        if not os.path.exists(ASC_SSIS_PATH):
            print(f"❌ SSIS package not found at: {ASC_SSIS_PATH}")
            return

        print(f"🚀 Running SSIS package: {ASC_SSIS_PATH}\n")
        
        # Run the package
        cmd = [dtexec_path, "/f", ASC_SSIS_PATH, "/Rep", "E"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        print(result.stdout)

        if result.returncode == 0:
            print("✅ SSIS Package executed successfully.")
        else:
            print("❌ SSIS execution failed.")
            if result.stderr:
                print(result.stderr)

    except Exception as e:
        print(f"⚠️ Error running SSIS: {e}")

if __name__ == "__main__":
    # Step 1: Clean and Copy
    cleaned_file = clean_csv()
    
    # Step 2: Run SSIS if cleaning was successful
    if cleaned_file:
        run_ssis()
    
    print("\n" + "="*60)
    print("✅ Process completed!")
    print("="*60)
