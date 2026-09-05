"""scripts/backfill_tv_seasons.py — Backfills all existing TV show seasons into tv_season_catalog.

Usage:
  .venv/Scripts/python.exe scripts/backfill_tv_seasons.py
"""

import os
import sys
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv()

from database import client as supabase_client
import services.catalog_service as catalog_service
import services.tmdb_service as tmdb_service

def run_season_backfill():
    print("=" * 70)
    print("KINETO CANONICAL TV SEASON CATALOG BACKFILL")
    print("=" * 70)

    # 1. Initialize local cache
    catalog_service.init_local_cache()

    # 2. Check Supabase table status
    supabase_online = False
    try:
        supabase_client.table("tv_season_catalog").select("season_key").limit(1).execute()
        print(">> Supabase 'tv_season_catalog' table: ONLINE (Ready for cloud sync)")
        supabase_online = True
    except Exception as e:
        print(">> [NOTICE] Supabase 'public.tv_season_catalog' table does not exist yet.")
        print(">> Please run 'scripts/create_supabase_tv_season_catalog.sql' in the Supabase SQL Editor:")
        print(">> https://supabase.com/dashboard/project/ooofscydkjzeobkugvfr/sql")
        print(">> (Enrichment will still proceed and cache locally in SQLite, then sync once created)\n")

    # 3. Query all TV show rows from Supabase lista
    print(">> Querying TV show entries from Supabase 'lista'...")
    res = supabase_client.table("lista").select("lista_id, movie, director, p_year, tv_show, season, tmdb_id, poster").eq("tv_show", 1).execute()
    rows = res.data or []
    print(f">> Total TV show entries found in 'lista': {len(rows)}")

    # 4. Parse & resolve seasons
    # Group by (tmdb_id, season_number)
    seasons_to_process = {}
    row_updates = []

    for r in rows:
        row_id = r["lista_id"]
        raw_title = (r.get("movie") or "").strip()
        if not raw_title:
            continue

        existing_season = r.get("season")
        clean_title = re.sub(r',?\s*(?:season|series|volume|vol|part|bk|book|the final season|final season)\s*\d*.*$', '', raw_title, flags=re.IGNORECASE).strip()
        tmdb_id = r.get("tmdb_id")

        # If tmdb_id is missing, look up from movie_catalog or TMDB
        if not tmdb_id:
            cat_item = catalog_service.get_catalog_item(clean_title, r.get("p_year"))
            if cat_item and cat_item.get("tmdb_id"):
                tmdb_id = cat_item["tmdb_id"]
            else:
                search_res = tmdb_service.search_titles(clean_title, is_tv=True, limit=3)
                if search_res:
                    tmdb_id = search_res[0].get("id")

        if not tmdb_id:
            print(f"   [WARN] Could not resolve TMDB ID for TV show: '{raw_title}'")
            continue

        tmdb_id = int(tmdb_id)
        season_num = catalog_service.resolve_tv_season_number(
            raw_title, 
            tmdb_id=tmdb_id, 
            current_season=existing_season, 
            poster_url=r.get("poster")
        )
        season_key = catalog_service.normalize_season_key(tmdb_id, season_num)

        if season_key not in seasons_to_process:
            seasons_to_process[season_key] = {
                "tmdb_id": tmdb_id,
                "season_number": season_num,
                "show_title": clean_title,
                "p_year": r.get("p_year"),
                "rows": []
            }
        
        seasons_to_process[season_key]["rows"].append({
            "lista_id": row_id,
            "current_season": existing_season,
            "current_tmdb_id": r.get("tmdb_id"),
            "current_poster": r.get("poster")
        })

    print(f">> Distinct TV Seasons identified across library: {len(seasons_to_process)}")

    # 5. Fetch, enrich, and embed each distinct season
    success_count = 0
    error_count = 0
    t0 = time.time()

    print("\n>> Fetching season-specific metadata & FastEmbed embeddings...")
    for idx, (s_key, s_info) in enumerate(seasons_to_process.items(), start=1):
        tmdb_id = s_info["tmdb_id"]
        season_num = s_info["season_number"]
        show_title = s_info["show_title"]
        try:
            enriched = catalog_service.fetch_and_enrich_tv_season(tmdb_id, season_num, show_title=show_title)
            catalog_service.upsert_tv_season_catalog_item(enriched, compute_embedding=True)
            
            poster_url = enriched.get("poster") or ""
            overview_snippet = (enriched.get("overview") or "")[:40].replace("\n", " ")
            print(f"[{idx}/{len(seasons_to_process)}] {enriched.get('show_title')} - {enriched.get('season_name')} ({enriched.get('year')}) | Directing: {enriched.get('director') or 'N/A'} | Synopsis: {overview_snippet}...")
            
            # Check if any associated rows in lista need updating (season number, tmdb_id, or season poster)
            for r_entry in s_info["rows"]:
                update_fields = {}
                if r_entry["current_season"] != season_num:
                    update_fields["season"] = season_num
                if not r_entry["current_tmdb_id"]:
                    update_fields["tmdb_id"] = tmdb_id
                # If poster is missing, placeholder, or generic, update to official season poster
                cur_post = str(r_entry["current_poster"] or "")
                if poster_url and ("placeholder" in cur_post.lower() or not cur_post or cur_post.endswith("default.jpg")):
                    update_fields["poster"] = poster_url

                if update_fields:
                    supabase_client.table("lista").update(update_fields).eq("lista_id", r_entry["lista_id"]).execute()

            success_count += 1
        except Exception as e:
            print(f"[{idx}/{len(seasons_to_process)}] [ERROR] Failed to enrich {s_key} ({show_title}): {e}")
            error_count += 1

    elapsed = round(time.time() - t0, 1)
    print("\n" + "=" * 70)
    print(f"SEASON ENRICHMENT COMPLETED in {elapsed}s")
    print(f"Successfully processed: {success_count}")
    print(f"Errors: {error_count}")
    print("=" * 70)

    # 6. Push local cache to Supabase
    if supabase_online:
        print("\n>> Syncing local season catalog to Supabase...")
        sync_stats = catalog_service.sync_local_seasons_to_supabase()
        print(f">> Supabase Sync: Synced {sync_stats['synced']} rows, Errors: {sync_stats['errors']}")
    else:
        print("\n>> Local SQLite replica cache fully populated. Supabase sync will run automatically once table is created.")

if __name__ == "__main__":
    run_season_backfill()
