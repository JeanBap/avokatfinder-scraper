"""Ireland Law Society — lawsociety.ie (~12k solicitors). HTML pagination."""
import asyncio, httpx, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://www.lawsociety.ie"

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

def parse_html(html):
    rows = []
    # Extract solicitor cards/table entries
    # lawsociety.ie search returns result blocks with name, firm, county
    blocks = re.findall(r'class="[^"]*result[^"]*"[^>]*>(.*?)</(?:div|tr|li)>', html, re.DOTALL | re.IGNORECASE)
    if not blocks:
        # Try table rows
        blocks = re.findall(r'<tr[^>]*class="[^"]*solicitor[^"]*"[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for b in blocks:
        name_m = re.search(r'class="[^"]*name[^"]*"[^>]*>(.*?)<', b, re.IGNORECASE)
        firm_m = re.search(r'class="[^"]*firm[^"]*"[^>]*>(.*?)<', b, re.IGNORECASE)
        city_m = re.search(r'class="[^"]*county|city|town[^"]*"[^>]*>(.*?)<', b, re.IGNORECASE)
        phone_m = re.search(r'[\+0-9][\d\s\-\(\)]{7,}', b)
        email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', b)
        name = re.sub(r'<[^>]+>','', name_m.group(1)).strip() if name_m else None
        if not name: continue
        rows.append({
            "country": "Ireland", "country_slug": "ireland", "type": "lawyer",
            "name": name,
            "firm_name": re.sub(r'<[^>]+>','', firm_m.group(1)).strip() if firm_m else None,
            "city": re.sub(r'<[^>]+>','', city_m.group(1)).strip() if city_m else None,
            "phone": phone_m.group() if phone_m else None,
            "email": email_m.group() if email_m else None,
            "source": "lawsociety_ie",
            "source_id": f"ie_{len(rows)}",
        })
    return rows

async def main():
    print("[bar_ie] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            page = 1
            while True:
                try:
                    r = await client.get(f"{BASE}/practising-solicitors",
                        params={"q": letter, "page": page},
                        headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                    if r.status_code != 200: break
                    rows = parse_html(r.text)
                    if not rows: break
                    total += await upsert(client, rows)
                    print(f"[bar_ie] {letter} p{page}: {len(rows)} => total {total}", flush=True)
                    if len(rows) < 20: break
                    page += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"[bar_ie] error {letter} p{page}: {e}", flush=True)
                    break
    print(f"[bar_ie] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
