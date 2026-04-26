"""Czech Bar Association — cak.cz (~12k). JSON/XML API."""
import asyncio, httpx, json, re, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://vyhledavac.cak.cz"

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries?on_conflict=source,source_id", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def main():
    print("[bar_cz] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            page = 1
            while True:
                try:
                    # cak.cz has a search form — try AJAX/JSON endpoint
                    r = await client.get(f"{BASE}/Units/Detail",
                        params={"q": letter, "page": page, "type": "A"},  # A=advokat
                        headers={"Accept":"application/json","X-Requested-With":"XMLHttpRequest","User-Agent":"AvokatFinder/1.0"},
                        timeout=30)
                    if r.status_code != 200:
                        r = await client.post(f"{BASE}/search",
                            data={"name": letter, "page": page},
                            headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                    if r.status_code != 200: break
                    try: data = r.json()
                    except:
                        # HTML fallback
                        rows_html = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
                        batch = []
                        for row in rows_html[1:]:  # skip header
                            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                            if len(cells) < 2: continue
                            name = re.sub(r'<[^>]+>','',cells[0]).strip()
                            if not name: continue
                            batch.append({
                                "country": "Czech Republic", "country_slug": "czech-republic", "type": "lawyer",
                                "name": name,
                                "city": re.sub(r'<[^>]+>','',cells[1]).strip() if len(cells)>1 else None,
                                "source": "cak_cz",
                                "source_id": f"cz_{letter}_{page}_{len(batch)}",
                            })
                        if batch:
                            total += await upsert(client, batch)
                            print(f"[bar_cz] {letter} p{page}: {len(batch)} => total {total}", flush=True)
                        if len(batch) < 20: break
                        page += 1
                        await asyncio.sleep(0.5)
                        continue
                    items = data if isinstance(data, list) else (data.get("items") or data.get("results") or [])
                    if not items: break
                    batch = []
                    for rec in items:
                        batch.append({
                            "country": "Czech Republic", "country_slug": "czech-republic", "type": "lawyer",
                            "name": rec.get("name") or rec.get("jmeno") or rec.get("prijmeni","")+" "+rec.get("jmeno",""),
                            "city": rec.get("mesto") or rec.get("city"),
                            "phone": rec.get("telefon") or rec.get("phone"),
                            "email": rec.get("email"),
                            "website": rec.get("web") or rec.get("website"),
                            "source": "cak_cz",
                            "source_id": str(rec.get("id") or rec.get("ev_cislo") or ""),
                        })
                    batch = [x for x in batch if x["name"].strip()]
                    total += await upsert(client, batch)
                    print(f"[bar_cz] {letter} p{page}: {len(batch)} => total {total}", flush=True)
                    if len(items) < 20: break
                    page += 1
                    await asyncio.sleep(0.4)
                except Exception as e:
                    print(f"[bar_cz] error {letter} p{page}: {e}", flush=True)
                    break
    print(f"[bar_cz] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
