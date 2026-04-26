"""Master runner — executes all lawyer/notary scrapers sequentially.

Phase 1: Wikidata (quick, ~3k records)
Phase 2: notaries-of-europe.eu (pan-EU, ~15k)
Phase 3: National bar association scrapers (bulk, ~310k)
Phase 4: Email extraction for records with websites but no email (Playwright)

Usage:
    python run_all.py                  # run all phases
    python run_all.py --phase 1        # specific phase only
    python run_all.py --skip wikidata  # skip one scraper
"""
import asyncio, subprocess, sys, os, time, json
from datetime import datetime, timezone

LOG_FILE = "/var/log/lawyer-scraper.log"

SCRAPERS = [
    # (module_name, description, phase)
    ("wikidata_scraper",    "Wikidata SPARQL (law firms + notable lawyers)", 1),
    ("notaries_eu_scraper", "notaries-of-europe.eu (pan-EU notaries)",       2),
    ("bar_uk_scraper",      "UK Law Society (~150k solicitors)",              3),
    ("bar_de_scraper",      "Germany anwaltauskunft.de (~80k)",               3),
    ("bar_it_scraper",      "Italy notariato.it + CNF (~30k)",                3),
    ("bar_pt_scraper",      "Portugal oa.pt (~20k)",                          3),
    ("bar_gr_scraper",      "Greece DSA + regional bars (~15k)",              3),
    ("bar_cz_scraper",      "Czech Republic cak.cz (~12k)",                   3),
    ("bar_ie_scraper",      "Ireland Law Society (~12k)",                     3),
    ("bar_rs_scraper",      "Serbia Advokatska Komora (~8k)",                 3),
    ("bar_be_scraper",      "Belgium advocaat.be + avocats.be (~8k)",         3),
    ("bar_dk_scraper",      "Denmark Advokatsamfundet (~5k)",                 3),
    ("bar_lt_scraper",      "Lithuania advokatura.lt + notairas.lt (~2.5k)",  3),
    ("bar_lu_scraper",      "Luxembourg Barreau (~1.5k)",                     3),
    ("email_scraper",       "Email extraction via Playwright (phase 4)",      4),
]

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except: pass

def run_scraper(module_name):
    start = time.time()
    log(f"START {module_name}")
    try:
        result = subprocess.run(
            [sys.executable, f"{module_name}.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=7200  # 2h max per scraper
        )
        elapsed = round(time.time() - start, 1)
        if result.returncode == 0:
            log(f"DONE  {module_name} ({elapsed}s)")
        else:
            log(f"FAIL  {module_name} ({elapsed}s) rc={result.returncode}")
        if result.stdout: log(f"  stdout: {result.stdout[-500:]}")
        if result.stderr: log(f"  stderr: {result.stderr[-500:]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT {module_name} (>7200s)")
        return False
    except Exception as e:
        log(f"ERROR {module_name}: {e}")
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, default=0, help="Run only this phase (0=all)")
    parser.add_argument("--skip", nargs="*", default=[], help="Skip these scrapers")
    parser.add_argument("--only", nargs="*", default=[], help="Run only these scrapers")
    args = parser.parse_args()

    log("=" * 60)
    log(f"lawyer-scraper run_all.py starting — {datetime.now(timezone.utc).isoformat()}")
    log(f"phase={args.phase or 'all'}, skip={args.skip}, only={args.only}")

    results = {}
    for module, desc, phase in SCRAPERS:
        if args.phase and phase != args.phase: continue
        if args.skip and module in args.skip: continue
        if args.only and module not in args.only: continue
        log(f"--- {desc} ---")
        ok = run_scraper(module)
        results[module] = "ok" if ok else "fail"

    log("=" * 60)
    log("SUMMARY:")
    for mod, status in results.items():
        log(f"  {status.upper():4s}  {mod}")
    ok_count = sum(1 for v in results.values() if v == "ok")
    log(f"  {ok_count}/{len(results)} scrapers succeeded")

if __name__ == "__main__":
    main()
