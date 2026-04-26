"""Greece DSA (dsa.gr) — Athens Bar Association + regional bars (~15k). HTML scrape."""
import asyncio, httpx, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

# Greek bar associations (Athens main + regional)
BARS = [
    ("https://www.dsa.gr", "athens"),
    ("https://www.dsth.gr", "thessaloniki"),
    ("https://www.dsp.gr", "piraeus"),
]

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def scrape_bar(client, base_url, city_hint):
    results = []
    page = 1
    while True:
        try:
            # Try JSON API first
            r = await client.get(f"{base_url}/api/members",
                params={"page": page, "per_page": 50},
                headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                timeout=30)
            if r.status_code == 200:
                try:
                    data = r.json()
                    items = data if isinstance(data, list) else (data.get("members") or data.get("results") or [])
                    if not items: break
                    for rec in items:
                        results.append({
                            "country": "Greece", "country_slug": "greece", "type": "lawyer",
                            "name": rec.get("name") or rec.get("fullname") or rec.get("onoma"),
                            "city": rec.get("city") or rec.get("poli") or city_hint,
                            "phone": rec.get("phone") or rec.get("tilefono"),
                            "email": rec.get("email"),
                            "website": rec.get("website"),
                            "source": f"dsa_gr_{city_hint}",
                            "source_id": str(rec.get("id") or rec.get("am") or ""),
                        })
                    if len(items) < 50: break
                    page += 1
                    await asyncio.sleep(0.4)
                    continue
                except: pass
            # Fallback: HTML
            r2 = await client.get(f"{base_url}/meloi/list",
                params={"page": page},
                headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
            if r2.status_code != 200: break
            # Parse names from HTML
            names = re.findall(r'<(?:td|div)[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</(?:td|div)>', r2.text, re.IGNORECASE | re.DOTALL)
            if not names: break
            for n in names:
                name = re.sub(r'<[^>]+>', '', n).strip()
                if name:
                    results.append({
                        "country": "Greece", "country_slug": "greece", "type": "lawyer",
                        "name": name, "city": city_hint,
                        "source": f"dsa_gr_{city_hint}",
                        "source_id": f"gr_{city_hint}_{len(results)}",
                    })
            if len(names) < 20: break
            page += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[bar_gr] error {base_url} p{page}: {e}", flush=True)
            break
    return results

async def main():
    print("[bar_gr] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for base_url, city in BARS:
            recs = await scrape_bar(client, base_url, city)
            if recs:
                total += await upsert(client, recs)
            print(f"[bar_gr] {city}: {len(recs)} => total {total}", flush=True)
    print(f"[bar_gr] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
