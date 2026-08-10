from FetchData import NikeACSAutomator, ACS_EMAIL, ACS_PASSWORD, CBD_STATUSES, BASE_URL
import json, time

# Seasons to test — put the ones you care about here
SEASONS_TO_TEST = ["SU27", "FA26", "SP27", "HO26"]

def check_counts():
    bot = NikeACSAutomator(ACS_EMAIL, ACS_PASSWORD)
    try:
        bot.login()
        bot.set_filters()
        bot.set_CBD()          # fires a search so the token becomes capturable
        token = bot._capture_token()

        fetch_script = """
            const [url, body, token] = arguments;
            const done = arguments[arguments.length - 1];
            fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json", "Authorization": token },
                credentials: "include",
                body: body
            })
            .then(r => r.json())
            .then(data => done({ ok: true, count: data.count }))
            .catch(err => done({ ok: false, error: err.toString() }));
        """
        bot.driver.set_script_timeout(60)

        # Broad search (all seasons) for reference
        def count_for(seasons):
            payload = {
                "seasons": seasons, "styleNumbers": [], "factoryCodes": [], "dimensions": [],
                "developerEmails": [], "cbdStatuses": CBD_STATUSES,
                "colorwayCodes": None, "createdDateRange": [], "dataStages": [],
                "mmUploads": [], "mscCodes": [], "poColorwayCodes": None,
                "reviewStatuses": None, "sampleRounds": None, "subCategories": None,
            }
            url = f"{BASE_URL}?page=1&size=400"
            res = bot.driver.execute_async_script(fetch_script, url, json.dumps(payload), token)
            return res.get("count") if res.get("ok") else f"ERROR: {res.get('error')}"

        broad = count_for([])
        print(f"\nBROAD (all seasons): {broad}")

        total = 0
        for s in SEASONS_TO_TEST:
            c = count_for([s])
            print(f"  {s}: {c}")
            if isinstance(c, int):
                total += c
            time.sleep(0.3)

        print(f"\nSum of tested seasons: {total}")
        print(f"Broad search returned: {broad}")
        if isinstance(broad, int) and total > broad:
            print(">>> CONFIRMED: more records exist than the broad search returns (2000 cap).")
    finally:
        bot.driver.quit()

if __name__ == "__main__":
    check_counts()