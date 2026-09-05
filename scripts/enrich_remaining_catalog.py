"""scripts/enrich_remaining_catalog.py — Enriches remaining stub titles in movie_catalog with TMDB data & embeddings

Finds all items in `movie_catalog` where `tmdb_id IS NULL` or `overview = ''`,
fetches rich TMDB metadata (synopsis, keywords, credits, lead cast, poster, vote stats),
computes 384D FastEmbed embeddings, and syncs to both Supabase and local SQLite cache.

Usage:
  .venv/Scripts/python.exe scripts/enrich_remaining_catalog.py
"""

import os
import sys
import time
import json
import sqlite3
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()

from database import client as supabase_client
import services.catalog_service as catalog_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def run_enrichment_pass(max_workers: int = 5):
    print("=" * 65)
    print("ENRICHING REMAINING STUB TITLES IN MOVIE CATALOG")
    print("=" * 65)

    # 1. Connect to local cache to find stubs
    conn = sqlite3.connect("instance/movie_catalog.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    stubs = cursor.execute("""
        SELECT movie_key, title, year, is_tv, director, cinematographer, composer, screenwriter, genres
        FROM movie_catalog
        WHERE tmdb_id IS NULL OR overview = '' OR overview IS NULL
    """).fetchall()

    stubs = [dict(r) for r in stubs]
    print(f">> Total stub titles to enrich: {len(stubs)}")

    if not stubs:
        print(">> No stub titles found! Catalog is already 100% enriched.")
        return

    # 2. Process in parallel
    t0 = time.time()
    success_items = []
    error_items = []

    def _enrich_single(item):
        key = item["movie_key"]
        title = item["title"]
        year = item["year"]
        is_tv = bool(item["is_tv"])

        try:
            enriched = catalog_service.fetch_and_enrich_from_tmdb(title, year, is_tv=is_tv)
            if not enriched.get("tmdb_id"):
                import re
                clean_t = re.sub(r',?\s*(series|season|volume|miniseries|limited series)\s*\d*.*$', '', title, flags=re.IGNORECASE).strip()
                clean_t = re.sub(r'\(.*?\)', '', clean_t).strip()
                is_tv_guess = is_tv or any(w in title.lower() for w in ['series', 'season', 'miniseries', 'volume', 'shippuden'])
                clean_year = year if year and int(year) > 1920 else None
                enriched = catalog_service.fetch_and_enrich_from_tmdb(clean_t, clean_year, is_tv=is_tv_guess)
                if not enriched.get("tmdb_id") and clean_year:
                    enriched = catalog_service.fetch_and_enrich_from_tmdb(clean_t, None, is_tv=is_tv_guess)

            if not enriched.get("tmdb_id"):
                return False, title, None, "No TMDB match found"

            # Retain the existing movie_key so lookups by original logged key succeed
            enriched["movie_key"] = key
            
            # Preserve existing curated craft credits if TMDB is sparse
            for craft_col in ["director", "cinematographer", "composer", "screenwriter"]:
                if not enriched.get(craft_col) and item.get(craft_col):
                    enriched[craft_col] = item[craft_col]
            if not enriched.get("genres") and item.get("genres"):
                enriched["genres"] = item.get("genres")

            # Upsert into local SQLite & Supabase
            catalog_service.upsert_catalog_item(enriched, compute_embedding=True)
            return True, title, enriched.get("tmdb_id"), enriched.get("genres", "")
        except Exception as e:
            return False, title, None, str(e)

    print(f">> Starting enrichment with {max_workers} worker threads...\n")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_enrich_single, it): it for it in stubs}
        for i, fut in enumerate(as_completed(futures), 1):
            ok, title, tmdb_id, info = fut.result()
            safe_title = str(title).encode('ascii', 'replace').decode('ascii')
            safe_info = str(info).encode('ascii', 'replace').decode('ascii')
            if ok:
                success_items.append((title, tmdb_id))
                if i % 10 == 0 or i == len(stubs) or i <= 5:
                    print(f"[{i}/{len(stubs)}] [OK] '{safe_title}' -> TMDB #{tmdb_id} ({safe_info[:30]})")
            else:
                error_items.append((title, info))
                print(f"[{i}/{len(stubs)}] [WARN] '{safe_title}': {safe_info}")

    duration = round(time.time() - t0, 1)
    print("\n" + "-" * 65)
    print(f">> Finished in {duration}s!")
    print(f">> Successfully enriched: {len(success_items)}")
    print(f">> Errors / Unmatched:     {len(error_items)}")
    if error_items:
        print(">> Errors list:")
        for t, err in error_items[:10]:
            print(f"   - {str(t).encode('ascii', 'replace').decode('ascii')}: {str(err).encode('ascii', 'replace').decode('ascii')}")

    # 3. Final sync verification
    conn2 = sqlite3.connect("instance/movie_catalog.db")
    remaining_stubs = conn2.execute("SELECT COUNT(*) FROM movie_catalog WHERE tmdb_id IS NULL OR overview = '' OR overview IS NULL").fetchone()[0]
    total_catalog = conn2.execute("SELECT COUNT(*) FROM movie_catalog").fetchone()[0]
    print(f">> Current catalog status: {total_catalog - remaining_stubs}/{total_catalog} fully enriched ({remaining_stubs} remaining stubs).")
    print("=" * 65)

if __name__ == "__main__":
    run_enrichment_pass(max_workers=5)
