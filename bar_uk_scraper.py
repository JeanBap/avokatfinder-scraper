"""UK Law Society solicitor search — solicitors.lawsociety.org.uk (~150k records)."""
import asyncio, httpx, json, os, re
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://solicitors.lawsociety.org.uk"

async def search_page(client, page):
    r = await client.get(f"{BASE}/SearchResults",
        params={"Type": "Individual", "Page": page, "PageSize": 20},
        headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0 (research scraper)"},
        timeout=30)
    if r.status_code != 200: return []
    try: return r.json().get("Results") or r.json().get("results") or []
    except: return []

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

def parse_record(rec):
    return {
        "country": "United Kingdom", "country_slug": "united-kingdom",
        "type": "lawyer",
        "name": rec.get("FullName") or rec.get("Name") or rec.get("name"),
        "firm_name": rec.get("OrganisationName") or rec.get("Organisation"),
        "address": rec.get("Address") or rec.get("address"),
        "website": rec.get("Website") or rec.get("website"),
        "email": rec.get("Email") or rec.get("email"),
        "phone": rec.get("Phone") or rec.get("phone") or rec.get("Telephone"),
        "city": rec.get("Town") or rec.get("City") or rec.get("city"),
        "source": "lawsociety_uk",
        "source_id": str(rec.get("Id") or rec.get("id") or rec.get("SRAId") or ""),
    }

async def main():
    print("[bar_uk] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # The Law Society uses a paginated search API
        # Try fetching with a broad name search A-Z
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            page = 1
            while True:
                try:
                    r = await client.get(f"{BASE}/SearchResults",
                        params={"Type":"Individual","LastName":letter,"Page":page,"PageSize":100},
                        headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                        timeout=30)
                    if r.status_code != 200:
                        print(f"[bar_uk] {letter} p{page} => {r.status_code}", flush=True)
                        break
                    try: data = r.json()
                    except: break
                    results = data.get("Results") or data.get("results") or data.get("Solicitors") or []
                    if not results: break
                    batch = [parse_record(x) for x in results if x.get("FullName") or x.get("Name") or x.get("name")]
                    total += await upsert(client, batch)
                    print(f"[bar_uk] {letter} p{page}: {len(batch)} => total {total}", flush=True)
                    # Check if more pages
                    total_count = data.get("TotalResults") or data.get("Total") or 0
                    if page * 100 >= int(total_count): break
                    page += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"[bar_uk] error {letter} p{page}: {e}", flush=True)
                    break
    print(f"[bar_uk] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
