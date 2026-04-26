"""Germany anwaltauskunft.de — DAV lawyer directory (~80k records). Uses JSON search API."""
import asyncio, httpx, json, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://anwaltauskunft.de"

# German postal code prefixes 0-9 (covering all 5-digit PLZ)
PLZ_PREFIXES = [str(i) for i in range(10)]  # 0x-9x thousands

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def scrape_city(client, city, plz_prefix):
    """Scrape anwaltauskunft search for a given PLZ prefix."""
    results = []
    page = 1
    while True:
        try:
            r = await client.get(f"{BASE}/anwaltssuche",
                params={"ort": plz_prefix, "seite": page},
                headers={"Accept":"text/html","User-Agent":"AvokatFinder/1.0"},
                timeout=20)
            if r.status_code != 200: break
            # Parse JSON embedded in page or use API endpoint
            # Try the API endpoint
            r2 = await client.get(f"{BASE}/api/suche",
                params={"ort": plz_prefix, "page": page, "per_page": 20},
                headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                timeout=20)
            if r2.status_code != 200: break
            try: data = r2.json()
            except: break
            items = data.get("results") or data.get("lawyers") or data.get("anwaelte") or []
            if not items: break
            results.extend(items)
            if len(items) < 20: break
            page += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"[bar_de] error plz {plz_prefix} p{page}: {e}", flush=True)
            break
    return results

def parse_record(rec):
    return {
        "country": "Germany", "country_slug": "germany",
        "type": "lawyer",
        "name": rec.get("name") or rec.get("vorname","") + " " + rec.get("nachname",""),
        "firm_name": rec.get("kanzlei") or rec.get("firm"),
        "address": rec.get("adresse") or rec.get("address") or rec.get("strasse","") + " " + rec.get("ort",""),
        "website": rec.get("website") or rec.get("url"),
        "email": rec.get("email"),
        "phone": rec.get("telefon") or rec.get("phone"),
        "city": rec.get("stadt") or rec.get("ort") or rec.get("city"),
        "source": "anwaltauskunft_de",
        "source_id": str(rec.get("id") or rec.get("anwalt_id") or ""),
        "specialties": rec.get("rechtsgebiete") or rec.get("specialties"),
    }

async def main():
    print("[bar_de] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for prefix in PLZ_PREFIXES:
            recs = await scrape_city(client, "", prefix)
            if not recs:
                # fallback: parse HTML
                print(f"[bar_de] plz {prefix}: JSON endpoint failed, skipping HTML parse", flush=True)
                continue
            batch = [parse_record(x) for x in recs]
            total += await upsert(client, batch)
            print(f"[bar_de] plz {prefix}: {len(batch)} => total {total}", flush=True)
    print(f"[bar_de] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
