"""
Phase 1 — Overpass API scraper.
Queries OpenStreetMap for all lawyers, notaries, law firms per European country.
Writes results to Supabase lawyers_notaries table.
"""

import asyncio, httpx, json, os, re, time, uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
OVERPASS = "https://overpass-api.de/api/interpreter"

AMENITY_MAP = {
    "lawyers": "lawyer",
    "notary": "notary",
    "law_firm": "law_firm",
}

def clean(s):
    if not s: return None
    s = s.strip()
    return s if s else None

def parse_tags(tags: dict, country: dict) -> dict:
    """Extract structured fields from OSM tags."""
    name = clean(tags.get("name") or tags.get("name:en"))
    website = clean(tags.get("website") or tags.get("contact:website") or tags.get("url"))
    if website and not website.startswith("http"):
        website = "https://" + website
    phone = clean(tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile"))
    email = clean(tags.get("email") or tags.get("contact:email"))
    if email and "@" not in email:
        email = None
    addr_parts = [
        tags.get("addr:housenumber",""),
        tags.get("addr:street",""),
        tags.get("addr:city",""),
        tags.get("addr:postcode",""),
    ]
    address = clean(" ".join(p for p in addr_parts if p)) or clean(tags.get("addr:full"))
    city = clean(tags.get("addr:city"))
    amenity = AMENITY_MAP.get(tags.get("amenity",""), "lawyer")
    langs = []
    for k,v in tags.items():
        if k.startswith("language:") and v in ("yes","native"):
            langs.append(k.replace("language:",""))
    return {
        "country": country["name"],
        "country_slug": country["slug"],
        "city": city,
        "type": amenity,
        "name": name,
        "address": address,
        "website": website,
        "email": email,
        "phone": phone,
        "languages": langs or None,
        "source": "osm",
    }

async def fetch_overpass(client: httpx.AsyncClient, country_osm: str) -> list[dict]:
    query = f"""
[out:json][timeout:180];
area["name"="{country_osm}"]["boundary"="administrative"]["admin_level"~"^[2-4]$"]->.a;
(
  node["amenity"="lawyers"](area.a);
  way["amenity"="lawyers"](area.a);
  node["amenity"="notary"](area.a);
  way["amenity"="notary"](area.a);
  node["amenity"="law_firm"](area.a);
  way["amenity"="law_firm"](area.a);
  node["office"="lawyer"](area.a);
  way["office"="lawyer"](area.a);
  node["office"="notary"](area.a);
  way["office"="notary"](area.a);
  node["office"="notary_public"](area.a);
  way["office"="notary_public"](area.a);
);
out body;
"""
    for attempt in range(3):
        try:
            r = await client.post(OVERPASS, data={"data": query}, timeout=200)
            if r.status_code == 200:
                data = r.json()
                return data.get("elements", [])
            elif r.status_code == 429:
                await asyncio.sleep(30 * (attempt + 1))
            else:
                print(f"  Overpass {r.status_code} for {country_osm}")
                return []
        except Exception as e:
            print(f"  Overpass error for {country_osm}: {e}")
            await asyncio.sleep(10)
    return []

async def upsert_batch(client: httpx.AsyncClient, rows: list[dict]):
    if not rows: return 0
    try:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/lawyers_notaries",
            json=rows,
            headers={**HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
            timeout=30,
        )
        return len(rows) if r.status_code < 300 else 0
    except Exception as e:
        print(f"  upsert error: {e}")
        return 0

async def log_run(client, source, country_slug, status, found, inserted, errors, notes=""):
    try:
        now = datetime.now(timezone.utc).isoformat()
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/lawyer_scraper_runs",
            params={"source": f"eq.{source}", "country_slug": f"eq.{country_slug}", "status": "eq.running"},
            json={"status": status, "finished_at": now, "found": found, "inserted": inserted, "errors": errors, "notes": notes},
            headers=HEADERS, timeout=10
        )
    except: pass

async def process_country(client: httpx.AsyncClient, country: dict):
    print(f"[{country['slug']}] fetching OSM...", flush=True)

    # Start run log
    await client.post(f"{SUPABASE_URL}/rest/v1/lawyer_scraper_runs",
        json={"source": "osm", "country_slug": country["slug"], "status": "running"},
        headers=HEADERS, timeout=10)

    elements = await fetch_overpass(client, country["osm"])
    print(f"[{country['slug']}] {len(elements)} elements", flush=True)

    rows = []
    for el in elements:
        tags = el.get("tags", {})
        if not tags: continue
        parsed = parse_tags(tags, country)
        if not parsed.get("name") and not parsed.get("website"): continue
        # Add OSM id + coords
        parsed["osm_id"] = str(el["id"])
        parsed["source_id"] = f"osm_{el['id']}"
        if el["type"] == "node":
            parsed["lat"] = el.get("lat")
            parsed["lng"] = el.get("lon")
        rows.append(parsed)

    inserted = 0
    # Batch upsert in chunks of 200
    for i in range(0, len(rows), 200):
        inserted += await upsert_batch(client, rows[i:i+200])

    await log_run(client, "osm", country["slug"], "done", len(elements), inserted, 0)
    print(f"[{country['slug']}] done — {len(rows)} rows, {inserted} inserted", flush=True)
    return len(rows), inserted

async def main():
    from countries import COUNTRIES
    print(f"Starting OSM scraper for {len(COUNTRIES)} countries", flush=True)
    async with httpx.AsyncClient(timeout=210) as client:
        total_found = total_inserted = 0
        for country in COUNTRIES:
            found, inserted = await process_country(client, country)
            total_found += found
            total_inserted += inserted
            # Overpass rate limit: ~1 req/2s
            await asyncio.sleep(3)
        print(f"\nDONE — total found: {total_found}, inserted: {total_inserted}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
