"""Lithuania — advokatura.lt (lawyers ~2k) + notairas.lt (notaries ~500)."""
import asyncio, httpx, re, json, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries?on_conflict=source,source_id", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def scrape_advokatura(client):
    results = []
    page = 1
    while True:
        try:
            r = await client.get("https://www.advokatura.lt/advokatai",
                params={"page": page},
                headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
            if r.status_code != 200: break
            # Extract from HTML
            blocks = re.findall(r'<div[^>]*class="[^"]*advokat[^"]*"[^>]*>(.*?)</div>', r.text, re.DOTALL | re.IGNORECASE)
            if not blocks:
                blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
            if not blocks: break
            for b in blocks:
                name_m = re.search(r'<(?:strong|h\d|td)[^>]*>(.*?)</(?:strong|h\d|td)>', b, re.IGNORECASE | re.DOTALL)
                email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', b)
                phone_m = re.search(r'[\+0-9][\d\s\-\(\)]{7,}', b)
                city_m = re.search(r'(?:Vilnius|Kaunas|Klaipeda|Šiauliai|Panevėžys)', b)
                name = re.sub(r'<[^>]+>','',name_m.group(1)).strip() if name_m else None
                if not name: continue
                results.append({
                    "country": "Lithuania", "country_slug": "lithuania", "type": "lawyer",
                    "name": name,
                    "city": city_m.group() if city_m else None,
                    "email": email_m.group() if email_m else None,
                    "phone": phone_m.group() if phone_m else None,
                    "source": "advokatura_lt",
                    "source_id": f"lt_{page}_{len(results)}",
                })
            if len(blocks) < 10: break
            page += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[bar_lt] advokatura error p{page}: {e}", flush=True)
            break
    return results

async def scrape_notairas(client):
    results = []
    try:
        r = await client.get("https://www.notairas.lt/notarai",
            headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
        if r.status_code == 200:
            blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
            for b in blocks[1:]:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', b, re.DOTALL | re.IGNORECASE)
                if len(cells) < 2: continue
                name = re.sub(r'<[^>]+>','',cells[0]).strip()
                if not name: continue
                email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', b)
                results.append({
                    "country": "Lithuania", "country_slug": "lithuania", "type": "notary",
                    "name": name,
                    "city": re.sub(r'<[^>]+>','',cells[1]).strip() if len(cells)>1 else None,
                    "email": email_m.group() if email_m else None,
                    "source": "notairas_lt",
                    "source_id": f"lt_notary_{len(results)}",
                })
    except Exception as e:
        print(f"[bar_lt] notairas error: {e}", flush=True)
    return results

async def main():
    print("[bar_lt] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        recs = await scrape_advokatura(client)
        total += await upsert(client, recs)
        print(f"[bar_lt] advokatura: {len(recs)}", flush=True)
        recs2 = await scrape_notairas(client)
        total += await upsert(client, recs2)
        print(f"[bar_lt] notairas: {len(recs2)}", flush=True)
    print(f"[bar_lt] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
