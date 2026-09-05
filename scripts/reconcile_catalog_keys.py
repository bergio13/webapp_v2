"""scripts/reconcile_catalog_keys.py — Resolves catalog key aliases and duplicates

Ensures that every movie in `public.lista` maps to strictly 1 canonical row in `public.movie_catalog`,
moving enriched metadata (tmdb_id, overview, crafts, embeddings) to the canonical key
and purging duplicate stubs/aliases (e.g. 'apocalypsenowfinalcut_1979' -> 'apocalypsenow_1979').
Also updates the local SQLite cache 'instance/movie_catalog.db'.
"""

import os
import sys
import sqlite3
from typing import Dict, Any

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
load_dotenv()

from database import client as supabase
import services.catalog_service as catalog_service
from services.catalog_service import normalize_movie_key, CATALOG_DB_PATH

def reconcile_catalog():
    print("=" * 65)
    print("RECONCILING MOVIE CATALOG KEYS AND ELIMINATING DUPLICATES")
    print("=" * 65)

    # 1. Fetch all rows from Supabase movie_catalog
    print(">> Fetching movie_catalog from Supabase...")
    all_cat = supabase.table("movie_catalog").select("*").execute().data
    print(f"Total rows in movie_catalog: {len(all_cat)}")
    cat_by_key: Dict[str, Dict[str, Any]] = {r['movie_key']: r for r in all_cat}

    # 2. Fetch all rows from Supabase lista
    print(">> Fetching lista from Supabase...")
    lista_rows = supabase.table("lista").select("lista_id, movie, p_year, tmdb_id").execute().data
    print(f"Total viewing logs in lista: {len(lista_rows)}")

    # Group lista by tmdb_id and by canonical key
    lista_canon = {}
    for r in lista_rows:
        title = r['movie']
        year = r['p_year']
        tmdb_id = r.get('tmdb_id')
        if not title:
            continue
        ckey = normalize_movie_key(title, year)
        if ckey not in lista_canon:
            lista_canon[ckey] = {
                "title": title,
                "year": year,
                "tmdb_id": tmdb_id
            }
        elif tmdb_id and not lista_canon[ckey].get("tmdb_id"):
            lista_canon[ckey]["tmdb_id"] = tmdb_id

    # 3. Find all duplicate pairs
    # Index catalog by tmdb_id
    cat_by_tmdb: Dict[int, list] = {}
    for r in all_cat:
        tid = r.get('tmdb_id')
        if tid:
            cat_by_tmdb.setdefault(tid, []).append(r)

    to_delete_from_supabase = set()
    to_upsert_to_supabase = []

    merged_count = 0

    # Step A: For each canonical item in lista
    for ckey, info in lista_canon.items():
        tmdb_id = info.get("tmdb_id")
        existing_canon = cat_by_key.get(ckey)

        # Look for enriched rows with this tmdb_id under another key
        matching_tmdb = cat_by_tmdb.get(tmdb_id, []) if tmdb_id else []
        alias_rows = [r for r in matching_tmdb if r['movie_key'] != ckey]

        if alias_rows:
            # We found alias rows for this title! (e.g. apocalypsenowfinalcut_1979 for Apocalypse Now)
            # Pick the most complete alias row (has embedding, overview, etc.)
            best_alias = max(alias_rows, key=lambda r: (
                bool(r.get('embedding_json')),
                len(r.get('overview') or ""),
                len(r.get('cinematographer') or "")
            ))

            # Build the consolidated canonical row
            canon_row = dict(best_alias)
            canon_row['movie_key'] = ckey
            canon_row['title'] = info['title']
            if info['year']:
                try:
                    canon_row['year'] = int(str(info['year'])[:4])
                except Exception:
                    pass
            canon_row['tmdb_id'] = tmdb_id

            to_upsert_to_supabase.append(canon_row)
            for a in alias_rows:
                to_delete_from_supabase.add(a['movie_key'])

            merged_count += 1
            print(f"  [MERGE] '{best_alias['movie_key']}' -> '{ckey}' (TMDB #{tmdb_id}, '{info['title']}')")

    # Step B: Also check for case-insensitive duplicate titles where one has tmdb_id and the other is null stub
    title_map = {}
    for r in all_cat:
        t_lower = r['title'].strip().lower()
        title_map.setdefault(t_lower, []).append(r)

    for t_lower, rows in title_map.items():
        if len(rows) > 1:
            with_tmdb = [r for r in rows if r.get('tmdb_id')]
            without_tmdb = [r for r in rows if not r.get('tmdb_id')]
            if with_tmdb and without_tmdb:
                # The row without tmdb_id is an un-enriched stub
                for stub in without_tmdb:
                    # Check if the stub has no embedding and no overview
                    if not stub.get('embedding_json') and not stub.get('overview'):
                        # If a row with tmdb exists for the same year
                        matching_year = [w for w in with_tmdb if w.get('year') == stub.get('year')]
                        if matching_year:
                            best_enriched = matching_year[0]
                            expected_key = normalize_movie_key(stub['title'], stub.get('year'))
                            # If the stub had the expected key, move enriched data to expected key
                            if stub['movie_key'] == expected_key and best_enriched['movie_key'] != expected_key:
                                enriched_copy = dict(best_enriched)
                                enriched_copy['movie_key'] = expected_key
                                to_upsert_to_supabase.append(enriched_copy)
                                to_delete_from_supabase.add(best_enriched['movie_key'])
                                to_delete_from_supabase.add(stub['movie_key'])
                                print(f"  [RESOLVE STUB] Moved '{best_enriched['movie_key']}' to '{expected_key}', purging stub")
                            else:
                                to_delete_from_supabase.add(stub['movie_key'])
                                print(f"  [PURGE STUB] '{stub['movie_key']}' (no tmdb, duplicate of '{best_enriched['movie_key']}')")

    print(f"\n>> Total canonical rows to upsert to Supabase: {len(to_upsert_to_supabase)}")
    print(f">> Total alias/stub rows to delete from Supabase: {len(to_delete_from_supabase)}")

    # 4. Apply upserts to Supabase
    if to_upsert_to_supabase:
        print("\n>> Upserting canonical consolidated rows to Supabase...")
        batch_size = 50
        for i in range(0, len(to_upsert_to_supabase), batch_size):
            chunk = to_upsert_to_supabase[i:i + batch_size]
            # Ensure proper payload fields
            clean_chunk = []
            for item in chunk:
                row = {
                    "movie_key": item["movie_key"],
                    "tmdb_id": item.get("tmdb_id"),
                    "imdb_id": item.get("imdb_id") or "",
                    "title": item["title"],
                    "year": item.get("year"),
                    "is_tv": item.get("is_tv", 0),
                    "genres": item.get("genres") or "",
                    "overview": item.get("overview") or "",
                    "keywords": item.get("keywords") or "",
                    "director": item.get("director") or "",
                    "cinematographer": item.get("cinematographer") or "",
                    "composer": item.get("composer") or "",
                    "screenwriter": item.get("screenwriter") or "",
                    "editor": item.get("editor") or "",
                    "lead_actors": item.get("lead_actors") or "",
                    "studios": item.get("studios") or "",
                    "poster": item.get("poster") or "",
                    "vote_average": float(item.get("vote_average") or 0.0),
                    "vote_count": int(item.get("vote_count") or 0),
                    "embedding_json": item.get("embedding_json") or ""
                }
                clean_chunk.append(row)
            supabase.table("movie_catalog").upsert(clean_chunk, on_conflict="movie_key").execute()
            print(f"   Upserted batch {i + 1}-{min(i + batch_size, len(to_upsert_to_supabase))}")

    # 5. Apply deletes to Supabase
    # Don't delete keys that are being kept as canonical
    actual_deletes = [k for k in to_delete_from_supabase if k not in {u['movie_key'] for u in to_upsert_to_supabase}]
    if actual_deletes:
        print(f"\n>> Deleting {len(actual_deletes)} alias/stub rows from Supabase...")
        batch_size = 50
        for i in range(0, len(actual_deletes), batch_size):
            chunk = actual_deletes[i:i + batch_size]
            supabase.table("movie_catalog").delete().in_("movie_key", chunk).execute()
            print(f"   Deleted batch {i + 1}-{min(i + batch_size, len(actual_deletes))}")

    # 6. Re-sync local SQLite cache
    print("\n>> Rebuilding local SQLite replica cache 'instance/movie_catalog.db'...")
    try:
        # Fetch fresh full table from Supabase
        fresh_cat = supabase.table("movie_catalog").select("*").execute().data
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.execute("DELETE FROM movie_catalog")
            for r in fresh_cat:
                emb_blob = None
                emb_json = r.get("embedding_json")
                if emb_json and emb_json.startswith("["):
                    try:
                        import json
                        import numpy as np
                        vec = np.array(json.loads(emb_json), dtype=np.float32)
                        emb_blob = catalog_service._vec_to_blob(vec)
                    except Exception:
                        pass
                conn.execute("""
                    INSERT OR REPLACE INTO movie_catalog (
                        movie_key, tmdb_id, imdb_id, title, year, is_tv, genres,
                        overview, keywords, director, cinematographer, composer,
                        screenwriter, editor, lead_actors, studios, poster,
                        vote_average, vote_count, embedding_blob, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (strftime('%s', 'now')))
                """, (
                    r.get("movie_key"),
                    r.get("tmdb_id"),
                    r.get("imdb_id", ""),
                    r.get("title", ""),
                    r.get("year"),
                    r.get("is_tv", 0),
                    r.get("genres", ""),
                    r.get("overview", ""),
                    r.get("keywords", ""),
                    r.get("director", ""),
                    r.get("cinematographer", ""),
                    r.get("composer", ""),
                    r.get("screenwriter", ""),
                    r.get("editor", ""),
                    r.get("lead_actors", ""),
                    r.get("studios", ""),
                    r.get("poster", ""),
                    float(r.get("vote_average") or 0.0),
                    int(r.get("vote_count") or 0),
                    emb_blob
                ))
            conn.commit()
        print(f">> Local SQLite cache successfully synced with {len(fresh_cat)} canonical items!")
    except Exception as e:
        print(f">> Local SQLite cache sync warning: {e}")

    # 7. Invalidate in-memory caches
    catalog_service._IN_MEMORY_CATALOG.clear()
    print("\n[OK] Movie catalog reconciliation completed successfully!")

if __name__ == "__main__":
    reconcile_catalog()
