"""
scripts/repair_tv_season_overviews.py — Repairs missing TV season overviews in tv_season_catalog.

Enforces:
- English-only season and series overviews (en-US).
- Resolves stub TMDB IDs via canonical search (e.g. Megalo Box 301022 -> 77939).
- Resolves TV specials/movies via movie endpoint fallback (e.g. A Very Murray Christmas 364067).
- Removes stale orphan rows (e.g. Attack on Titan: Chronicle 714194_s4).
- Recomputes 384D FastEmbed semantic embeddings.
- Upserts to both local SQLite cache and Supabase public.tv_season_catalog.
- Invalidates and refreshes user Discover Galaxy cache.

Usage:
    .venv/Scripts/python.exe scripts/repair_tv_season_overviews.py
"""

import os
import sys
import sqlite3
import time

sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from database import client as supabase_client
import services.catalog_service as catalog_service
from services.cosmos_service import build_taste_cosmos_data


def run_repair():
    print("=" * 70)
    print("KINETO TV SEASON OVERVIEW REPAIR & EMBEDDING RECOMPUTATION")
    print("=" * 70)

    # 1. Initialize catalog cache
    catalog_service.init_local_cache()

    # 2. Cleanup stale orphan: 714194_s4 (Attack on Titan: Chronicle)
    print("\n>> Checking for stale orphan rows...")
    conn = sqlite3.connect("instance/movie_catalog.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tv_season_catalog WHERE season_key = '714194_s4'")
    conn.commit()
    try:
        supabase_client.table("tv_season_catalog").delete().eq("season_key", "714194_s4").execute()
        print("   [CLEANUP] Removed orphan '714194_s4' from SQLite & Supabase.")
    except Exception as e:
        print(f"   [NOTICE] Supabase cleanup for 714194_s4: {e}")

    # 3. Find all TV seasons with empty or whitespace-only overview
    cursor.execute("""
        SELECT season_key, tmdb_id, season_number, show_title, director, lead_actors, year 
        FROM tv_season_catalog 
        WHERE overview IS NULL OR TRIM(overview) = ''
    """)
    empty_seasons = cursor.fetchall()
    print(f"\n>> Found {len(empty_seasons)} TV seasons with missing overviews to enrich & re-embed.")

    success_count = 0
    fail_count = 0

    for idx, (s_key, tmdb_id, s_num, show_title, ex_dir, ex_actors, ex_year) in enumerate(empty_seasons, start=1):
        print(f"\n[{idx}/{len(empty_seasons)}] Enriching '{show_title}' (Season {s_num}, TMDB ID: {tmdb_id})...")
        try:
            enriched = catalog_service.fetch_and_enrich_tv_season(
                tmdb_id=tmdb_id,
                season_number=s_num,
                show_title=show_title,
                force_refresh=True
            )

            # Preserve existing director if valid and newly enriched was Unknown
            invalid_dirs = {"", "none", "null", "undefined", "unknown", "various", "various directors", "showrunner"}
            if ex_dir and (ex_dir.strip().lower() not in invalid_dirs):
                new_dir = (enriched.get("director") or "").strip().lower()
                if not new_dir or new_dir in invalid_dirs:
                    enriched["director"] = ex_dir.strip()

            ov = (enriched.get("overview") or "").strip()
            if ov:
                success_count += 1
                ov_snippet = (ov[:65] + "...") if len(ov) > 65 else ov
                print(f"   [SUCCESS] Overview ({len(ov)} chars): \"{ov_snippet}\"")
            else:
                fail_count += 1
                print(f"   [WARN] Overview is still empty after all fallbacks.")

            # Upsert and force recompute FastEmbed 384D embedding with the new overview
            catalog_service.upsert_tv_season_catalog_item(
                enriched, 
                compute_embedding=True, 
                force_recompute_embedding=True
            )
            print(f"   [EMBED] Recomputed 384D vector & synchronized to SQLite + Supabase.")

        except Exception as e:
            fail_count += 1
            print(f"   [ERROR] Failed enriching {s_key}: {e}")

    conn.close()

    print("\n" + "=" * 70)
    print(f">> Repair Summary: {success_count} enriched successfully, {fail_count} unresolved.")
    print("=" * 70)

    # 4. Invalidate Galaxy Cosmos Cache for active user (ID 15)
    print("\n>> Invalidating Cosmos Galaxy cache and rebuilding semantic space...")
    try:
        build_taste_cosmos_data(15, force_refresh=True)
        print(">> [SUCCESS] Discover Galaxy cache refreshed with updated TV season embeddings!")
    except Exception as ge:
        print(f">> [NOTICE] Rebuilding galaxy cache for user 15: {ge}")

    print("\n>> TV Season Catalog overview repair COMPLETE.")


if __name__ == "__main__":
    run_repair()
