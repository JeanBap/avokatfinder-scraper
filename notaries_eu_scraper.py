"""notaries-of-europe.eu — pan-European notary directory (~15k records). HTML pagination."""
import asyncio, httpx, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://www.notaries-of-europe.eu"

COUNTRIES = [
    ("Albania","AL","albania"),("Austria","AT","austria"),("Belgium","BE","belgium"),
    ("Bulgaria","BG","bulgaria"),("Croatia","HR","croatia"),("Cyprus","CY","cyprus"),
    ("Czech Republic","CZ","czech-republic"),("Estonia","EE","estonia"),
    ("France","FR","france"),("Germany","DE","germany"),("Greece","GR","greece"),
    ("Hungary","HU","hungary"),("Italy","IT","italy"),("Latvia","LV","latvia"),
    ("Lithuania","LT","lithuania"),("Luxembourg","LU","luxembourg"),("Malta","MT","malta"),
    ("Netherlands","NL","netherlands"),("Poland","PL","poland"),("Portugal","PT","portugal"),
    ("Romania","RO","romania"),("Slovakia","SK","slovakia"),("Slovenia","SI","slovenia"),
    ("Spain","ES","spain"),
]

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

def extract_notaries(html, country, slug):
    """Parse HTML table rows from notaries-of-europe.eu listing."""
    rows = []
    # Pattern: table rows with name, city, contact info
    # Try to extract from table/list structures
    entries = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for entry in entries:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', entry, re.DOTALL | re.IGNORECASE)
        if len(cells) < 2: continue
        name = re.sub(r'<[^>]+>', '', cells[0]).strip()
        if not name or name.lower() in ('name','notary','full name'): continue
        city = re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else None
        phone_m = re.search(r'[\+0-9][\d\s\-\(\)]{7,}', entry)
        email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', entry)
        web_m = re.search(r'https?://[^\s"<>]+', entry)
        rows.append({
            "country": country, "country_slug": slug, "type": "notary",
            "name": name, "city": city,
            "phone": phone_m.group() if phone_m else None,
            "email": email_m.group() if email_m else None,
            "website": web_m.group() if web_m else None,
            "source": "notaries_europe",
            "source_id": f"ne_{slug}_{len(rows)}",
        })
    return rows

async def scrape_country(client, country, iso, slug):
    results = []
    page = 1
    while True:
        try:
            # Try search endpoint
            r = await client.get(f"{BASE}/en/about-notaries/find-a-notary",
                params={"country": iso, "page": page},
                headers={"User-Agent":"AvokatFinder/1.0"},
                timeout=30)
            if r.status_code != 200: break
            rows = extract_notaries(r.text, country, slug)
            if not rows: break
            results.extend(rows)
            if len(rows) < 10: break
            page += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[notaries_eu] error {country} p{page}: {e}", flush=True)
            break
    return results

async def main():
    print("[notaries_eu] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for country, iso, slug in COUNTRIES:
            recs = await scrape_country(client, country, iso, slug)
            if recs:
                total += await upsert(client, recs)
                print(f"[notaries_eu] {country}: {len(recs)} => total {total}", flush=True)
            else:
                print(f"[notaries_eu] {country}: 0 results", flush=True)
            await asyncio.sleep(1)
    print(f"[notaries_eu] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
