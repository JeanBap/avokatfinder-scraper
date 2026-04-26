"""Wikidata SPARQL — law firms, notary offices, notable lawyers in Europe."""
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json"}

COUNTRY_ISO = {
    "Albania":"AL","Austria":"AT","Belarus":"BY","Belgium":"BE","Bosnia and Herzegovina":"BA",
    "Bulgaria":"BG","Croatia":"HR","Cyprus":"CY","Czech Republic":"CZ","Denmark":"DK",
    "Estonia":"EE","Finland":"FI","France":"FR","Germany":"DE","Greece":"GR","Hungary":"HU",
    "Iceland":"IS","Ireland":"IE","Italy":"IT","Kosovo":"XK","Latvia":"LV",
    "Liechtenstein":"LI","Lithuania":"LT","Luxembourg":"LU","Malta":"MT","Moldova":"MD",
    "Montenegro":"ME","Netherlands":"NL","North Macedonia":"MK","Norway":"NO","Poland":"PL",
    "Portugal":"PT","Romania":"RO","Serbia":"RS","Slovakia":"SK","Slovenia":"SI",
    "Spain":"ES","Sweden":"SE","Switzerland":"CH","Ukraine":"UA","United Kingdom":"GB",
}
SLUG_MAP = {v: k.lower().replace(" ","-") for k,v in COUNTRY_ISO.items()}
SLUG_MAP.update({"GB":"united-kingdom","BA":"bosnia","BY":"belarus"})

SPARQL_LAW_FIRMS = """
SELECT DISTINCT ?item ?itemLabel ?website ?email ?phone ?countryLabel ?country WHERE {
  { ?item wdt:P31 wd:Q613142 } UNION { ?item wdt:P31 wd:Q2571614 } UNION
  { ?item wdt:P31 wd:Q252686 }
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:Q46 .
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P968 ?email }
  OPTIONAL { ?item wdt:P1329 ?phone }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it,es,pt,nl" }
} LIMIT 10000
"""

SPARQL_LAWYERS = """
SELECT DISTINCT ?item ?itemLabel ?website ?email ?countryLabel ?country WHERE {
  ?item wdt:P106 wd:Q40348 .
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:Q46 .
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P968 ?email }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it,es" }
} LIMIT 10000
"""

def country_to_slug(label):
    for k, v in COUNTRY_ISO.items():
        if label.lower() in k.lower():
            return v, k
    return None, label

def g(row, key):
    return row.get(key, {}).get("value")

async def run_query(client, name, sparql):
    print(f"[wikidata] running {name}...", flush=True)
    try:
        r = await client.get("https://query.wikidata.org/sparql",
            params={"query": sparql, "format": "json"},
            headers={"Accept": "application/sparql-results+json", "User-Agent": "AvokatFinder/1.0"},
            timeout=90)
        if r.status_code != 200:
            print(f"[wikidata] {name} failed: {r.status_code}", flush=True)
            return []
        rows = r.json()["results"]["bindings"]
        print(f"[wikidata] {name}: {len(rows)} results", flush=True)
        # Debug first row
        if rows:
            first = rows[0]
            print(f"[wikidata] sample keys: {list(first.keys())}", flush=True)
            print(f"[wikidata] sample name: {g(first, 'itemLabel')}", flush=True)
        return rows
    except Exception as e:
        print(f"[wikidata] {name} error: {e}", flush=True)
        return []

async def upsert(client, rows):
    if not rows:
        return 0
    try:
        r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
            headers={**HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
            timeout=30)
        if r.status_code >= 300:
            print(f"[wikidata] upsert failed {r.status_code}: {r.text[:200]}", flush=True)
            return 0
        return len(rows)
    except Exception as e:
        print(f"[wikidata] upsert error: {e}", flush=True)
        return 0

async def main():
    async with httpx.AsyncClient() as client:
        total = 0
        for qname, sparql in [("law_firms", SPARQL_LAW_FIRMS), ("lawyers", SPARQL_LAWYERS)]:
            rows = await run_query(client, qname, sparql)
            batch = []
            skipped = 0
            for row in rows:
                country_label = g(row, "countryLabel") or ""
                iso, cname = country_to_slug(country_label)
                slug = SLUG_MAP.get(iso, country_label.lower().replace(" ", "-"))
                website = g(row, "website")
                if website and not website.startswith("http"):
                    website = "https://" + website
                email = g(row, "email")
                if email and "@" not in email:
                    email = None
                entry = {
                    "country": cname or country_label,
                    "country_slug": slug,
                    "type": "law_firm" if qname == "law_firms" else "lawyer",
                    "name": g(row, "itemLabel"),
                    "website": website,
                    "email": email,
                    "phone": g(row, "phone"),
                    "source": "wikidata",
                    "source_id": "wd_" + (g(row, "item") or "").split("/")[-1],
                }
                if entry["name"]:
                    batch.append(entry)
                else:
                    skipped += 1
                if len(batch) >= 200:
                    n = await upsert(client, batch)
                    total += n
                    print(f"[wikidata] batch upserted {n}", flush=True)
                    batch = []
            if batch:
                n = await upsert(client, batch)
                total += n
                print(f"[wikidata] final batch upserted {n}", flush=True)
            print(f"[wikidata] {qname}: skipped {skipped} nameless rows", flush=True)
        print(f"[wikidata] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
