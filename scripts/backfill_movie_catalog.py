"""scripts/backfill_movie_catalog.py — Backfills all existing movies into movie_catalog (Supabase + local SQLite)

Usage:
  .venv/Scripts/python.exe scripts/backfill_movie_catalog.py
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv()

from database import client as supabase_client
import services.catalog_service as catalog_service

def run_backfill(user_id: int = None, limit: int = None):
    print("=" * 65)
    print("KINETO CANONICAL MOVIE CATALOG BACKFILL (SUPABASE + LOCAL CACHE)")
    print("=" * 65)

    # 1. Check Supabase table status
    supabase_online = False
    try:
        supabase_client.table("movie_catalog").select("count", count="exact").limit(1).execute()
        print(">> Supabase 'movie_catalog' table: ONLINE (Ready for cloud sync)")
        supabase_online = True
    except Exception as e:
        print(">> [NOTICE] Supabase 'public.movie_catalog' table does not exist yet.")
        print(">> Please run 'scripts/create_supabase_movie_catalog.sql' in the Supabase SQL Editor:")
        print(">> https://supabase.com/dashboard/project/ooofscydkjzeobkugvfr/sql")
        print(">> (Enrichment will still proceed and cache locally, then sync to Supabase once created)\n")

    # 2. Fetch unique titles from Supabase lista
    print(">> Querying unique movies from Supabase 'lista'...")
    query = supabase_client.table("lista").select("movie, p_year, tv_show, director, genre")
    if user_id:
        query = query.eq("parent_id", user_id)
    res = query.execute()
    rows = res.data or []
    print(f"Total entries found in 'lista': {len(rows)}")

    # Deduplicate by normalized key
    unique_items = {}
    for r in rows:
        title = (r.get("movie") or "").strip()
        if not title:
            continue
        year = r.get("p_year")
        key = catalog_service.normalize_movie_key(title, year)
        if key not in unique_items:
            unique_items[key] = {
                "title": title,
                "year": year,
                "is_tv": bool(r.get("tv_show") in [1, "1", True]),
                "director": r.get("director", ""),
                "genre": r.get("genre", "")
            }

    items_to_process = list(unique_items.values())
    if limit:
        items_to_process = items_to_process[:limit]

    total = len(items_to_process)
    print(f">> Total unique titles to ensure in catalog: {total}")

    # Check already enriched in catalog
    existing_catalog = catalog_service.batch_get_catalog([catalog_service.normalize_movie_key(it["title"], it["year"]) for it in items_to_process])
    to_fetch = []
    already_complete = 0

    for it in items_to_process:
        k = catalog_service.normalize_movie_key(it["title"], it["year"])
        existing = existing_catalog.get(k)
        if existing and existing.get("overview") and existing.get("cinematographer"):
            already_complete += 1
        else:
            to_fetch.append(it)

    print(f">> Already complete in catalog: {already_complete}")
    print(f">> Items needing TMDB enrichment & embedding: {len(to_fetch)}")

    if to_fetch:
        # Process in parallel with ThreadPoolExecutor
        print(f"\n>> Starting parallel enrichment (workers=5)...")
        t0 = time.time()
        success_count = 0
        error_count = 0

        def _process_item(it):
            title = it["title"]
            year = it["year"]
            is_tv = it["is_tv"]
            try:
                enriched = catalog_service.fetch_and_enrich_from_tmdb(title, year, is_tv=is_tv)
                if not enriched.get("director") and it.get("director"):
                    enriched["director"] = it["director"]
                if not enriched.get("genres") and it.get("genre"):
                    enriched["genres"] = it["genre"]

                # Upsert into local cache and Supabase (if online)
                catalog_service.upsert_catalog_item(enriched, compute_embedding=True)
                return True, title, enriched.get("genres", ""), enriched.get("tmdb_id")
            except Exception as e:
                return False, title, str(e), None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_process_item, it): it for it in to_fetch}
            for i, future in enumerate(as_completed(futures), 1):
                success, title, info, tmdb_id = future.result()
                if success:
                    success_count += 1
                    if i % 25 == 0 or i == len(to_fetch) or i <= 5:
                        print(f"[{i}/{len(to_fetch)}] Enriched: '{title}' -> TMDB #{tmdb_id} | Genres: {info[:35]}")
                else:
                    error_count += 1
                    print(f"[{i}/{len(to_fetch)}] Warning on '{title}': {info}")

        duration = round(time.time() - t0, 1)
        print(f"\n>> TMDB enrichment pass finished in {duration}s. (Success: {success_count}, Errors: {error_count})")

    # If Supabase is online, ensure full sync
    if supabase_online:
        print("\n>> Syncing all catalog entries to Supabase 'public.movie_catalog'...")
        sync_stats = catalog_service.sync_local_to_supabase(batch_size=50)
        print(f">> Supabase Sync Complete: Synced {sync_stats['synced']} / {sync_stats['total_read']} rows.")

    print("\n" + "=" * 65)
    print("BACKFILL PROCESS COMPLETE!")
    print(f"Total unique movies indexed in catalog: {total}")
    print("=" * 65)

if __name__ == "__main__":
    user_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    run_backfill(user_id=user_arg)
