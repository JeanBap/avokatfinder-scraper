"""Belgium — advocaat.be (Dutch) + avocats.be (French) (~8k). HTML scrape."""
import asyncio, httpx, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

SOURCES = [
    ("https://www.advocaat.be", "advocaat_be"),
    ("https://www.avocats.be", "avocats_be"),
]

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries?on_conflict=source,source_id", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def scrape_source(client, base_url, source_key):
    results = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        page = 1
        while True:
            try:
                r = await client.get(f"{base_url}/find-a-lawyer",
                    params={"name": letter, "page": page},
                    headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                if r.status_code != 200:
                    r = await client.get(f"{base_url}/zoek-een-advocaat",
                        params={"naam": letter, "pagina": page},
                        headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                if r.status_code != 200: break
                # Extract cards
                blocks = re.findall(r'class="[^"]*(?:lawyer|advocaat|avocat)[^"]*"[^>]*>(.*?)</(?:div|article|li)>', r.text, re.DOTALL | re.IGNORECASE)
                if not blocks:
                    blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
                if not blocks: break
                for b in blocks:
                    name_m = re.search(r'<(?:h\d|strong|span)[^>]*>(.*?)</(?:h\d|strong|span)>', b, re.IGNORECASE | re.DOTALL)
                    city_m = re.search(r'(?:city|stad|ville|gemeente)[^>]*>(.*?)<', b, re.IGNORECASE | re.DOTALL)
                    email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', b)
                    phone_m = re.search(r'[\+0-9][\d\s\-\(\)]{7,}', b)
                    name = re.sub(r'<[^>]+>','',name_m.group(1)).strip() if name_m else None
                    if not name: continue
                    results.append({
                        "country": "Belgium", "country_slug": "belgium", "type": "lawyer",
                        "name": name,
                        "city": re.sub(r'<[^>]+>','',city_m.group(1)).strip() if city_m else None,
                        "email": email_m.group() if email_m else None,
                        "phone": phone_m.group() if phone_m else None,
                        "source": source_key,
                        "source_id": f"{source_key}_{letter}_{page}_{len(results)}",
                    })
                if len(blocks) < 10: break
                page += 1
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"[bar_be] error {source_key} {letter} p{page}: {e}", flush=True)
                break
    return results

async def main():
    print("[bar_be] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for base_url, source_key in SOURCES:
            recs = await scrape_source(client, base_url, source_key)
            if recs:
                total += await upsert(client, recs)
            print(f"[bar_be] {source_key}: {len(recs)} => total {total}", flush=True)
    print(f"[bar_be] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
