"""Master runner: OSM → email extraction → report."""
import subprocess, sys

print("=== Phase 1: OSM scraper ===")
subprocess.run([sys.executable, "osm_scraper.py"], check=True)

print("\n=== Phase 2: Email extraction ===")
subprocess.run([sys.executable, "email_scraper.py"], check=True)

print("\nAll phases complete.")
