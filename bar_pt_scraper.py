"""Portugal Ordem dos Advogados — oa.pt (~20k). JSON search API."""
import asyncio, httpx, json, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

BASE = "https://www.oa.pt"

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

async def main():
    print("[bar_pt] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            page = 0
            while True:
                try:
                    # oa.pt uses a REST API for member search
                    r = await client.post(f"{BASE}/api/advogados/search",
                        json={"nome": letter, "pagina": page, "porPagina": 50},
                        headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                        timeout=30)
                    if r.status_code == 404:
                        # Try alternate endpoint
                        r = await client.get(f"{BASE}/order/member-list",
                            params={"name": letter, "page": page},
                            headers={"Accept":"application/json","User-Agent":"AvokatFinder/1.0"},
                            timeout=30)
                    if r.status_code != 200: break
                    try: data = r.json()
                    except: break
                    items = data if isinstance(data, list) else (data.get("advogados") or data.get("members") or data.get("results") or [])
                    if not items: break
                    batch = []
                    for rec in items:
                        batch.append({
                            "country": "Portugal", "country_slug": "portugal", "type": "lawyer",
                            "name": rec.get("nome") or rec.get("name"),
                            "firm_name": rec.get("escritorio") or rec.get("firm"),
                            "address": rec.get("morada") or rec.get("address"),
                            "city": rec.get("concelho") or rec.get("city"),
                            "phone": rec.get("telefone") or rec.get("phone"),
                            "email": rec.get("email"),
                            "website": rec.get("website"),
                            "source": "oa_pt",
                            "source_id": str(rec.get("id") or rec.get("numero") or ""),
                        })
                    batch = [x for x in batch if x["name"]]
                    total += await upsert(client, batch)
                    print(f"[bar_pt] {letter} p{page}: {len(batch)} => total {total}", flush=True)
                    if len(items) < 50: break
                    page += 1
                    await asyncio.sleep(0.4)
                except Exception as e:
                    print(f"[bar_pt] error {letter} p{page}: {e}", flush=True)
                    break
    print(f"[bar_pt] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
