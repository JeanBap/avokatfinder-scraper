"""Luxembourg Barreau — barreau.lu (~1.5k). HTML scrape."""
import asyncio, httpx, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://www.barreau.lu"

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries?on_conflict=source,source_id", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def main():
    print("[bar_lu] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            page = 1
            while True:
                try:
                    r = await client.get(f"{BASE}/avocats",
                        params={"nom": letter, "page": page},
                        headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                    if r.status_code != 200: break
                    # Extract lawyer entries
                    entries = re.findall(r'class="[^"]*(?:avocat|lawyer|member)[^"]*"[^>]*>(.*?)</(?:div|li|article)>', r.text, re.DOTALL | re.IGNORECASE)
                    if not entries:
                        entries = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
                    if not entries: break
                    batch = []
                    for e in entries:
                        name_m = re.search(r'<(?:h\d|strong|a|td)[^>]*>(.*?)</(?:h\d|strong|a|td)>', e, re.DOTALL | re.IGNORECASE)
                        firm_m = re.search(r'(?:cabinet|etude|firm)[^>]*>(.*?)<', e, re.IGNORECASE | re.DOTALL)
                        email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', e)
                        phone_m = re.search(r'[\+0-9][\d\s\-\(\)]{7,}', e)
                        name = re.sub(r'<[^>]+>','',name_m.group(1)).strip() if name_m else None
                        if not name or len(name) < 3: continue
                        batch.append({
                            "country": "Luxembourg", "country_slug": "luxembourg", "type": "lawyer",
                            "name": name,
                            "firm_name": re.sub(r'<[^>]+>','',firm_m.group(1)).strip() if firm_m else None,
                            "city": "Luxembourg",
                            "email": email_m.group() if email_m else None,
                            "phone": phone_m.group() if phone_m else None,
                            "source": "barreau_lu",
                            "source_id": f"lu_{letter}_{page}_{len(batch)}",
                        })
                    total += await upsert(client, batch)
                    print(f"[bar_lu] {letter} p{page}: {len(batch)} => total {total}", flush=True)
                    if len(entries) < 10: break
                    page += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"[bar_lu] error {letter} p{page}: {e}", flush=True)
                    break
    print(f"[bar_lu] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
