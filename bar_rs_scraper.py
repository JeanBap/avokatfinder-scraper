"""Serbia Advokatska Komora — advokatska-komora.rs (~8k). HTML scrape."""
import asyncio, httpx, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://www.advokatska-komora.rs"

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries?on_conflict=source,source_id", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def main():
    print("[bar_rs] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        page = 1
        while True:
            try:
                r = await client.get(f"{BASE}/imenik-advokata",
                    params={"page": page, "per_page": 50},
                    headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                if r.status_code != 200:
                    r = await client.get(f"{BASE}/advokati",
                        params={"strana": page},
                        headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                if r.status_code != 200: break
                # Try JSON
                try:
                    data = r.json()
                    items = data if isinstance(data, list) else (data.get("advokati") or data.get("results") or [])
                    batch = []
                    for rec in items:
                        batch.append({
                            "country": "Serbia", "country_slug": "serbia", "type": "lawyer",
                            "name": rec.get("ime_prezime") or rec.get("name"),
                            "city": rec.get("grad") or rec.get("city"),
                            "phone": rec.get("telefon") or rec.get("phone"),
                            "email": rec.get("email"),
                            "source": "komora_rs",
                            "source_id": str(rec.get("id") or rec.get("broj_odvjetnicke_iskaznice") or ""),
                        })
                    batch = [x for x in batch if x["name"]]
                except:
                    # HTML fallback
                    rows_html = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
                    batch = []
                    for row in rows_html[1:]:
                        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                        if len(cells) < 2: continue
                        name = re.sub(r'<[^>]+>','',cells[0]).strip()
                        if not name: continue
                        email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', row)
                        phone_m = re.search(r'[\+0-9][\d\s\-\(\)]{7,}', row)
                        batch.append({
                            "country": "Serbia", "country_slug": "serbia", "type": "lawyer",
                            "name": name,
                            "city": re.sub(r'<[^>]+>','',cells[1]).strip() if len(cells)>1 else None,
                            "email": email_m.group() if email_m else None,
                            "phone": phone_m.group() if phone_m else None,
                            "source": "komora_rs",
                            "source_id": f"rs_{page}_{len(batch)}",
                        })
                if not batch: break
                total += await upsert(client, batch)
                print(f"[bar_rs] p{page}: {len(batch)} => total {total}", flush=True)
                if len(batch) < 20: break
                page += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[bar_rs] error p{page}: {e}", flush=True)
                break
    print(f"[bar_rs] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
