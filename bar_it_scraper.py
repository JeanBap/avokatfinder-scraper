"""Italy — notariato.it notaries (~6k) + consiglionazionaleforense.it lawyers."""
import asyncio, httpx, re, json, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

# Italian provinces for iteration
PROVINCES = [
    "AG","AL","AN","AO","AR","AP","AT","AV","BA","BT","BL","BN","BG","BI","BO","BZ","BS",
    "BR","CA","CL","CB","CI","CE","CT","CZ","CH","CO","CS","CR","KR","CN","EN","FM","FE",
    "FI","FG","FC","FR","GE","GO","GR","IM","IS","SP","LT","LE","LC","LI","LO","LU","MC",
    "MN","MS","MT","ME","MI","MO","MB","NA","NO","NU","OG","OT","OR","PD","PA","PR","PV",
    "PG","PU","PE","PC","PI","PT","PN","PZ","PO","RG","RA","RC","RE","RI","RN","RM","RO",
    "SA","SS","SV","SI","SR","SO","TA","TE","TR","TO","TP","TN","TV","TS","UD","VA","VE",
    "VB","VC","VR","VV","VI","VT",
]

async def scrape_notariato(client):
    results = []
    for prov in PROVINCES:
        page = 1
        while True:
            try:
                r = await client.get("https://www.notariato.it/it/cerca-un-notaio",
                    params={"provincia": prov, "page": page},
                    headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                if r.status_code != 200: break
                # Extract notary cards
                cards = re.findall(r'class="[^"]*notai[^"]*"[^>]*>(.*?)</(?:div|article)>', r.text, re.DOTALL | re.IGNORECASE)
                if not cards:
                    # Try table rows
                    cards = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
                if not cards: break
                for c in cards:
                    name_m = re.search(r'<(?:h\d|strong|td)[^>]*>(.*?)</(?:h\d|strong|td)>', c, re.DOTALL | re.IGNORECASE)
                    addr_m = re.search(r'(?:via|piazza|corso|viale)\s+[^<,]{5,50}', c, re.IGNORECASE)
                    phone_m = re.search(r'[\+0-9][\d\s\-\(\)\/]{7,}', c)
                    email_m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', c)
                    name = re.sub(r'<[^>]+>','',name_m.group(1)).strip() if name_m else None
                    if not name or len(name) < 3: continue
                    results.append({
                        "country": "Italy", "country_slug": "italy", "type": "notary",
                        "name": name,
                        "city": prov,
                        "address": addr_m.group() if addr_m else None,
                        "phone": phone_m.group() if phone_m else None,
                        "email": email_m.group() if email_m else None,
                        "source": "notariato_it",
                        "source_id": f"it_notary_{prov}_{len(results)}",
                    })
                if len(cards) < 10: break
                page += 1
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"[bar_it] notariato {prov} p{page}: {e}", flush=True)
                break
    return results

async def scrape_cnf(client):
    """Consiglio Nazionale Forense — lawyer registry."""
    results = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        page = 1
        while True:
            try:
                r = await client.get("https://www.consiglionazionaleforense.it/albo-avvocati",
                    params={"cognome": letter, "page": page},
                    headers={"User-Agent":"AvokatFinder/1.0"}, timeout=30)
                if r.status_code != 200: break
                rows = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE)
                if not rows: break
                for row in rows[1:]:
                    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
                    if len(cells) < 2: continue
                    name = re.sub(r'<[^>]+>','',cells[0]).strip()
                    if not name: continue
                    results.append({
                        "country": "Italy", "country_slug": "italy", "type": "lawyer",
                        "name": name,
                        "city": re.sub(r'<[^>]+>','',cells[1]).strip() if len(cells)>1 else None,
                        "source": "cnf_it",
                        "source_id": f"it_lawyer_{letter}_{page}_{len(results)}",
                    })
                if len(rows) < 15: break
                page += 1
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"[bar_it] cnf {letter} p{page}: {e}", flush=True)
                break
    return results

async def main():
    print("[bar_it] starting...", flush=True)
    total = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        n_recs = await scrape_notariato(client)
        total += await upsert(client, n_recs)
        print(f"[bar_it] notariato: {len(n_recs)}", flush=True)
        l_recs = await scrape_cnf(client)
        total += await upsert(client, l_recs)
        print(f"[bar_it] cnf: {len(l_recs)}", flush=True)
    print(f"[bar_it] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
