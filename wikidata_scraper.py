"""Wikidata SPARQL — law firms, notary offices, notable lawyers in Europe."""
import asyncio, httpx, json, os, uuid
from datetime import datetime, timezone
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
SLUG_MAP = {v: k.lower().replace(" ","-").replace("(","").replace(")","") for k,v in COUNTRY_ISO.items()}
SLUG_MAP["GB"] = "united-kingdom"
SLUG_MAP["BA"] = "bosnia"
SLUG_MAP["BY"] = "belarus"

QUERIES = {
    "law_firms": """
SELECT DISTINCT ?item ?itemLabel ?website ?email ?phone ?countryLabel ?country WHERE {
  { ?item wdt:P31 wd:Q613142 } UNION { ?item wdt:P31 wd:Q2571614 } UNION
  { ?item wdt:P31 wd:Q252686 }
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:Q46 .
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P968 ?email }
  OPTIONAL { ?item wdt:P1329 ?phone }
  OPTIONAL { ?country wdt:P297 ?iso }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it,es,pt,nl" }
} LIMIT 10000
""",
    "lawyers": """
SELECT DISTINCT ?item ?itemLabel ?website ?email ?countryLabel ?country WHERE {
  ?item wdt:P106 wd:Q40348 .
  ?item wdt:P17 ?country .
  ?country wdt:P30 wd:Q46 .
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P968 ?email }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,de,it,es" }
} LIMIT 10000
""",
}

def country_to_slug(label):
    for k, v in COUNTRY_ISO.items():
        if label.lower() in k.lower(): return v, k
    return None, label

async def run_query(client, name, sparql):
    print(f"[wikidata] running {name}...", flush=True)
    r = await client.get("https://query.wikidata.org/sparql",
        params={"query": sparql, "format": "json"},
        headers={"Accept":"application/sparql-results+json","User-Agent":"AvokatFinder/1.0"},
        timeout=90)
    if r.status_code != 200:
        print(f"[wikidata] {name} failed: {r.status_code}"); return []
    rows = r.json()["results"]["bindings"]
    print(f"[wikidata] {name}: {len(rows)} results", flush=True)
    return rows

async def upsert(client, rows):
    if not rows: return 0
    r = await client.post(f"{SUPABASE_URL}/rest/v1/lawyers_notaries", json=rows,
        headers={**HEADERS,"Prefer":"resolution=ignore-duplicates,return=minimal"}, timeout=30)
    return len(rows) if r.status_code < 300 else 0

def g(row, key): return row.get(key,{}).get("value")

async def main():
    async with httpx.AsyncClient() as client:
        total = 0
        for qname, sparql in QUERIES.items():
            rows = await run_query(client, qname, sparql)
            batch = []
            for row in rows:
                country_label = g(row,"countryLabel") or ""
                iso, cname = country_to_slug(country_label)
                slug = SLUG_MAP.get(iso, country_label.lower().replace(" ","-"))
                website = g(row,"website")
                if website and not website.startswith("http"): website = "https://"+website
                email = g(row,"email")
                if email and "@" not in email: email = None
                entry = {
                    "country": cname or country_label,
                    "country_slug": slug,
                    "type": "law_firm" if qname=="law_firms" else "lawyer",
                    "name": g(row,"itemLabel"),
                    "website": website,
                    "email": email,
                    "phone": g(row,"phone"),
                    "source": "wikidata",
                    "source_id": f"wd_{( g(row,'item') or '' ).split('/')[-1]}",
                }
                if entry["name"]: batch.append(entry)
                if len(batch) >= 200:
                    total += await upsert(client, batch); batch=[]
            total += await upsert(client, batch)
        print(f"[wikidata] done — {total} upserted", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
