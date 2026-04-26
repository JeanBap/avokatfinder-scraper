"""Denmark Advokatsamfundet — advokatsamfundet.dk (~5k). JSON API."""
import asyncio, httpx, json, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://www.advokatsamfundet.dk"

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries?on_conflict=source,source_id", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def main():
    print("[bar_dk] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # advokatsamfundet has a search API
        page = 0
        while True:
            try:
                r = await client.get(f"{BASE}/api/lawyer-search",
                    params={"page": page, "size": 100, "sort": "name"},
                    headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                    timeout=30)
                if r.status_code != 200:
                    # Try alternate
                    r = await client.get(f"{BASE}/find-advokat/api/search",
                        params={"q": "", "page": page, "pageSize": 100},
                        headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                        timeout=30)
                if r.status_code != 200:
                    print(f"[bar_dk] API failed: {r.status_code}", flush=True)
                    break
                try: data = r.json()
                except: break
                items = data if isinstance(data, list) else (data.get("lawyers") or data.get("items") or data.get("results") or [])
                if not items: break
                batch = []
                for rec in items:
                    batch.append({
                        "country": "Denmark", "country_slug": "denmark", "type": "lawyer",
                        "name": rec.get("name") or rec.get("navn") or (rec.get("firstName","")+" "+rec.get("lastName","")),
                        "firm_name": rec.get("firm") or rec.get("firma") or rec.get("company"),
                        "city": rec.get("city") or rec.get("by"),
                        "phone": rec.get("phone") or rec.get("telefon"),
                        "email": rec.get("email"),
                        "website": rec.get("website") or rec.get("homepage"),
                        "source": "advokatsamfundet_dk",
                        "source_id": str(rec.get("id") or rec.get("cvr") or ""),
                    })
                batch = [x for x in batch if x["name"].strip()]
                total += await upsert(client, batch)
                print(f"[bar_dk] p{page}: {len(batch)} => total {total}", flush=True)
                if len(items) < 100: break
                page += 1
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"[bar_dk] error p{page}: {e}", flush=True)
                break
    print(f"[bar_dk] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
