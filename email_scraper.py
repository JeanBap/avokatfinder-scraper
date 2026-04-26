"""
Phase 2 — Email extractor.
For lawyers/notaries with website but no email, scrapes their site with Playwright.
"""

import asyncio, httpx, json, os, re
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
MAX_WORKERS = int(os.environ.get("EMAIL_WORKERS", "20"))
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json"}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
JUNK_DOMAINS = {"example.com","sentry.io","squarespace.com","wix.com","google.com",
                "wordpress.com","jquery.com","cloudflare.com","schema.org"}

def extract_emails(html: str, url: str) -> list[str]:
    found = EMAIL_RE.findall(html)
    clean = []
    for e in found:
        e = e.lower().strip(".")
        domain = e.split("@")[-1]
        if domain in JUNK_DOMAINS: continue
        if any(e.endswith(x) for x in [".png",".jpg",".css",".js"]): continue
        if e not in clean:
            clean.append(e)
    return clean[:3]

async def load_queue(client: httpx.AsyncClient) -> list[dict]:
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/lawyers_notaries",
        params={"select":"id,website","email":"is.null","website":"not.is.null",
                "website_scraped_at":"is.null","limit":"50000"},
        headers=HEADERS, timeout=30)
    return r.json() if r.status_code == 200 else []

async def scrape_one(pid: int, row: dict, sem: asyncio.Semaphore,
                      client: httpx.AsyncClient, pw_ctx):
    async with sem:
        url = row["website"]
        try:
            page = await pw_ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            html = await page.content()
            await page.close()
            emails = extract_emails(html, url)
            now = datetime.now(timezone.utc).isoformat()
            patch = {"website_scraped_at": now, "email": emails[0] if emails else None}
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/lawyers_notaries",
                params={"id": f"eq.{row['id']}"},
                json=patch, headers=HEADERS, timeout=10)
            return bool(emails)
        except Exception as e:
            now = datetime.now(timezone.utc).isoformat()
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/lawyers_notaries",
                params={"id": f"eq.{row['id']}"},
                json={"website_scraped_at": now}, headers=HEADERS, timeout=10)
            return False

async def main():
    from playwright.async_api import async_playwright
    from filters import is_blocked

    async with httpx.AsyncClient(timeout=30) as client:
        queue = await load_queue(client)
        print(f"Email queue: {len(queue)} lawyers with websites, no email", flush=True)
        if not queue: return

        sem = asyncio.Semaphore(MAX_WORKERS)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = await browser.new_context()
            tasks = []
            for i, row in enumerate(queue):
                if is_blocked(row["website"])[0]: continue
                tasks.append(scrape_one(i, row, sem, client, ctx))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            found = sum(1 for r in results if r is True)
            print(f"Done — {found}/{len(tasks)} emails found", flush=True)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
