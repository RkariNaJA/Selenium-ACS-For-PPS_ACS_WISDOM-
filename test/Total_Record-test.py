"""
Sub-split test: for a season that caps at 2000 (e.g. SP27), try dividing it
by a second field and see whether each piece lands under 2000.

Run:  py check_subsplit.py
"""
from FetchData import (
    NikeACSAutomator, ACS_EMAIL, ACS_PASSWORD, CBD_STATUSES, BASE_URL
)
import json
import time

# The season we know caps at 2000 and want to break down further.
CAPPED_SEASON = "SP27"

# Second fields to try splitting on. We'll discover the actual values from the
# data itself, then test each value combined with the season.
FIELDS_TO_TRY = ["factoryCode", "dimension"]   # record field names in the JSON

# Map a record field name -> the payload key that filters on it.
PAYLOAD_KEY = {
    "factoryCode": "factoryCodes",
    "dimension":   "dimensions",
}


FETCH_SCRIPT = """
    const [url, body, token] = arguments;
    const done = arguments[arguments.length - 1];
    fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": token },
        credentials: "include",
        body: body
    })
    .then(r => r.json())
    .then(data => done({ ok: true, data }))
    .catch(err => done({ ok: false, error: err.toString() }));
"""


def build_payload(seasons, extra=None):
    """Base payload; `extra` merges in the second-field filter."""
    payload = {
        "seasons": seasons, "styleNumbers": [], "factoryCodes": [], "dimensions": [],
        "developerEmails": [], "cbdStatuses": CBD_STATUSES,
        "colorwayCodes": None, "createdDateRange": [], "dataStages": [],
        "mmUploads": [], "mscCodes": [], "poColorwayCodes": None,
        "reviewStatuses": None, "sampleRounds": None, "subCategories": None,
    }
    if extra:
        payload.update(extra)
    return payload


def run():
    bot = NikeACSAutomator(ACS_EMAIL, ACS_PASSWORD)
    try:
        bot.login()
        bot.set_filters()
        bot.set_CBD()                 # fires a search so the token is capturable
        token = bot._capture_token()
        bot.driver.set_script_timeout(60)

        def query(seasons, extra=None):
            """Return (count, records) for a given filter."""
            payload = build_payload(seasons, extra)
            url = f"{BASE_URL}?page=1&size=400"
            res = bot.driver.execute_async_script(
                FETCH_SCRIPT, url, json.dumps(payload), token
            )
            if not res.get("ok"):
                return None, []
            data = res["data"]
            return data.get("count", 0), (data.get("cbdSearchResults") or [])

        # 1) Confirm the season caps, and grab a page of its records so we can
        #    discover which factory codes / dimensions appear in it.
        count, records = query([CAPPED_SEASON])
        print(f"\n{CAPPED_SEASON} total count: {count}")
        if count and count >= 2000:
            print(f"  -> capped at 2000, needs sub-splitting\n")

        # 2) For each candidate field, find the distinct values present in the
        #    sample, then test season + that value.
        for field in FIELDS_TO_TRY:
            pkey = PAYLOAD_KEY[field]
            values = sorted({r.get(field) for r in records if r.get(field)})
            print(f"=== Splitting {CAPPED_SEASON} by {field} "
                  f"({len(values)} value(s) seen in sample) ===")

            all_under = True
            for v in values:
                c, _ = query([CAPPED_SEASON], {pkey: [v]})
                flag = ""
                if c is not None and c >= 2000:
                    flag = "  <-- STILL CAPPED"
                    all_under = False
                print(f"  {field}={v}: {c}{flag}")
                time.sleep(0.3)

            if all_under:
                print(f"  >>> {field} splits {CAPPED_SEASON} cleanly "
                      f"(every piece under 2000).\n")
            else:
                print(f"  >>> {field} is NOT enough on its own — some pieces "
                      f"still cap.\n")

    finally:
        bot.driver.quit()


if __name__ == "__main__":
    run()