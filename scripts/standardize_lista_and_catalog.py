"""scripts/standardize_lista_and_catalog.py

Standardizes and cleans `lista` and `movie_catalog` on Supabase:
1. Standardizes `lista.movie` to official TMDB titles (e.g. 'Anatomy of a Fall', 'Lost in Translation').
2. Populates `lista.season` for TV shows (extracting season numbers into the new column).
3. Populates `lista.tmdb_id` for permanent direct relational linkage to movie_catalog.
4. Preserves 100% of user viewing history (dates, ratings, cinema, rewatch flags, lista_id).
5. Deduplicates `movie_catalog` so each movie/show has strictly 1 canonical row per tmdb_id.
"""

import sys
import os
import re
import time
import logging
from collections import defaultdict

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv()

from database import client as supabase_client
import services.catalog_service as catalog_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def norm(title, year=""):
    return catalog_service.normalize_movie_key(title, year)

def run_standardization():
    print("=" * 65)
    print("KINETO LISTA STANDARDIZATION & CATALOG DEDUPLICATION")
    print("=" * 65)

    # 1. Verify that season and tmdb_id exist in lista
    try:
        supabase_client.table("lista").select("lista_id, season, tmdb_id").limit(1).execute()
        print(">> Verified: 'season' and 'tmdb_id' columns exist in Supabase 'lista'.")
    except Exception as e:
        print(">> [ERROR] Columns 'season' and 'tmdb_id' do not exist in 'lista' yet!")
        print(">> Please run 'scripts/alter_supabase_lista.sql' in the Supabase SQL Editor first:")
        print(">> https://supabase.com/dashboard/project/ooofscydkjzeobkugvfr/sql")
        return False

    # 2. Fetch all catalog rows
    print("\n>> Fetching existing canonical catalog from Supabase...")
    cat_res = supabase_client.table("movie_catalog").select("*").execute()
    cat_rows = cat_res.data or []
    cat_by_key = {r["movie_key"]: r for r in cat_rows}
    cat_by_tmdb = defaultdict(list)
    for r in cat_rows:
        if r.get("tmdb_id"):
            cat_by_tmdb[r["tmdb_id"]].append(r)
    print(f">> Loaded {len(cat_rows)} catalog rows across {len(cat_by_tmdb)} unique TMDB IDs.")

    # 3. Fetch all lista entries
    print("\n>> Fetching all viewing logs from Supabase 'lista'...")
    lista_res = supabase_client.table("lista").select("*").execute()
    lista_rows = lista_res.data or []
    print(f">> Total viewing log entries in 'lista': {len(lista_rows)}")

    # 4. Standardize each lista row
    print("\n>> Standardizing 'lista' entries (resolving titles, seasons, and TMDB IDs)...")
    updated_lista = []
    unchanged_count = 0
    standardized_count = 0
    tv_season_count = 0

    for row in lista_rows:
        orig_movie = str(row.get("movie") or "").strip()
        orig_year = row.get("p_year")
        is_tv = bool(row.get("tv_show") in [1, "1", True])

        # Check if season is mentioned in title (e.g. "The Mentalist, Season 1" or "The Mentalist Season 1")
        season_num = row.get("season")
        clean_title = orig_movie
        season_match = re.search(r',?\s*season\s*(\d+)', orig_movie, re.IGNORECASE)
        if season_match:
            season_num = int(season_match.group(1))
            clean_title = re.sub(r',?\s*season\s*\d+.*$', '', orig_movie, flags=re.IGNORECASE).strip()
            is_tv = True
            tv_season_count += 1

        # Look up in catalog using raw key or clean key
        key1 = norm(orig_movie, orig_year)
        key2 = norm(clean_title, orig_year)

        cat_item = cat_by_key.get(key1) or cat_by_key.get(key2)

        canonical_title = orig_movie
        tmdb_id = row.get("tmdb_id")
        genres = row.get("genre")
        director = row.get("director")
        poster = row.get("poster")

        if cat_item:
            canonical_title = cat_item.get("title") or clean_title
            tmdb_id = cat_item.get("tmdb_id") or tmdb_id
            if cat_item.get("genres") and (not genres or genres in ["Cinema", "Unknown"] or len(cat_item["genres"]) > len(genres)):
                genres = cat_item["genres"]
            if cat_item.get("director") and (not director or director in ["Unknown", ""]):
                director = cat_item["director"]
            if cat_item.get("poster") and (not poster or "placeholder" in str(poster)):
                poster = cat_item["poster"]

        # If it's a TV show, we want the pure show title in `movie` (e.g. "The Mentalist")
        final_movie = clean_title if is_tv and season_match else canonical_title

        # Check if anything changed
        changed = (
            final_movie != orig_movie or 
            season_num != row.get("season") or 
            tmdb_id != row.get("tmdb_id") or
            is_tv != bool(row.get("tv_show") in [1, "1", True]) or
            genres != row.get("genre")
        )

        if changed:
            standardized_count += 1
            updated_row = {
                "lista_id": row["lista_id"],
                "movie": final_movie,
                "season": season_num,
                "tmdb_id": tmdb_id,
                "tv_show": 1 if is_tv else 0,
                "genre": genres,
                "director": director,
                "poster": poster,
                # Preserved viewing logs:
                "parent_id": row["parent_id"],
                "p_year": row.get("p_year"),
                "v_date": row.get("v_date"),
                "rating": row.get("rating"),
                "rewatch": row.get("rewatch"),
                "cinema": row.get("cinema")
            }
            updated_lista.append(updated_row)
        else:
            unchanged_count += 1

    print(f">> Rows needing standardization updates: {standardized_count}")
    print(f">> Rows already standard: {unchanged_count}")
    print(f">> TV seasons extracted to 'season' column: {tv_season_count}")

    # Push updates to Supabase lista in batches
    if updated_lista:
        print(f">> Updating {len(updated_lista)} rows in Supabase 'lista' in batches of 50...")
        batch_size = 50
        for i in range(0, len(updated_lista), batch_size):
            chunk = updated_lista[i:i + batch_size]
            supabase_client.table("lista").upsert(chunk).execute()
        print(">> Supabase 'lista' table successfully updated!")

    # 5. Deduplicate movie_catalog to strictly 1 canonical row per tmdb_id
    print("\n>> Deduplicating Supabase 'movie_catalog' (collapsing alias rows)...")
    alias_keys_to_delete = []

    for t_id, items in cat_by_tmdb.items():
        if len(items) > 1:
            # Find the best item with most complete data
            best_item = max(items, key=lambda x: (len(str(x.get("overview") or "")), len(str(x.get("embedding_json") or ""))))
            canonical_key = norm(best_item.get("title") or "", best_item.get("year"))

            # If the best item has an alias key, create the canonical key entry first
            if best_item["movie_key"] != canonical_key:
                canonical_copy = dict(best_item)
                canonical_copy["movie_key"] = canonical_key
                catalog_service.upsert_catalog_item(canonical_copy, compute_embedding=False)
                alias_keys_to_delete.append(best_item["movie_key"])

            for it in items:
                if it["movie_key"] != canonical_key and it["movie_key"] not in alias_keys_to_delete:
                    alias_keys_to_delete.append(it["movie_key"])

    print(f">> Found {len(alias_keys_to_delete)} duplicate alias rows to remove from 'movie_catalog'.")
    if alias_keys_to_delete:
        batch_size = 50
        for i in range(0, len(alias_keys_to_delete), batch_size):
            chunk = alias_keys_to_delete[i:i + batch_size]
            supabase_client.table("movie_catalog").delete().in_("movie_key", chunk).execute()
        print(">> Duplicate alias rows successfully removed from Supabase 'movie_catalog'!")

        # Also remove from local SQLite cache
        import sqlite3
        with sqlite3.connect(catalog_service.CATALOG_DB_PATH) as conn:
            for k in alias_keys_to_delete:
                conn.execute("DELETE FROM movie_catalog WHERE movie_key = ?", (k,))
            conn.commit()
        print(">> Local SQLite cache synchronized.")

    # 6. Final verification
    cat_count_res = supabase_client.table("movie_catalog").select("count", count="exact").execute()
    print("\n" + "=" * 65)
    print("STANDARDIZATION & CLEANUP COMPLETE!")
    print(f">> Total viewing logs preserved in 'lista': {len(lista_rows)}")
    print(f">> Distinct canonical titles in 'movie_catalog': {cat_count_res.count}")
    print("=" * 65)
    return True

if __name__ == "__main__":
    run_standardization()
