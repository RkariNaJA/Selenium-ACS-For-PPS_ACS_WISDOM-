import subprocess
import os
from datetime import datetime
from dotenv import load_dotenv

# ========================================
#               LOAD ENV
# ========================================
load_dotenv()

base_path = os.getenv("ACS-FLOW_BASE_PATH")

# ---------------- LOG PATH ----------------
desktop_path = os.getenv("DESKTOP_PATH",os.path.join(os.path.expanduser("~"), "Desktop"))

log_filename = os.getenv("ACS-FLOW_LOG_FILE", "flow_Log.txt")
log_file = os.path.join(desktop_path, log_filename)

RUN_ID = os.getenv("ACS-FLOW_RUN_ID", "ACS-FLOW_DEFAULT")

# -------- MULTILINE PARSING --------
scripts_env = os.getenv("ACS-FLOW_SCRIPTS", "")
scripts_env = scripts_env.strip().strip('"').strip("'")
scripts_env = scripts_env.replace("\n", " ").replace("\t", " ")
scripts_env = scripts_env.replace("  ", " ")

scripts_to_run = [s.strip() for s in scripts_env.split(",") if s.strip()]

if not scripts_to_run:
    raise Exception("❌ ไม่มีรายการ ACS-FLOW_SCRIPTS ในไฟล์ .env")


# ========================================
#           START EXECUTION
# ========================================
start_time = datetime.now()
success = 0
fail = 0

print(f"🚀 เริ่มรัน ACS-FLOW (Process: {RUN_ID})")
print(f"📂 Base Path: {base_path}")
print("=" * 80)

for script in scripts_to_run:
    script_path = os.path.join(base_path, script)

    if not os.path.exists(script_path):
        print(f"⚠️ ไม่พบไฟล์: {script_path}")
        fail += 1
        continue

    print(f"➡️ รันไฟล์: {script}")

    try:
        subprocess.run(["python", script_path], check=True)
        print(f"✅ เสร็จสิ้น: {script}")
        success += 1
    except subprocess.CalledProcessError as e:
        print(f"❌ Error ในไฟล์ {script}: {e}")
        fail += 1


# ========================================
#       SAVE SUMMARY LOG (NEW FORMAT)
# ========================================
end_time = datetime.now()
status_text = "SUCCESS" if fail == 0 else "FAILED"

try:
    with open(log_file, "a", encoding="utf-8") as log:
        log.write("\n=============================================\n")
        log.write(f"Process: {RUN_ID}\n")
        log.write(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"End Time:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"Status: {status_text}\n")
        log.write(f"Success Count: {success}\n")
        log.write(f"Failed Count: {fail}\n")
        log.write("=============================================\n")
    print(f"\n📄 Log saved to: {log_file}")
except Exception as e:
    print(f"⚠️ Could not save log file: {e}")

print("\n" + "=" * 80)
print(f"✅ Finished! Success: {success}, Failed: {fail}")
print("=" * 80)
