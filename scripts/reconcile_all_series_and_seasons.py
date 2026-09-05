"""scripts/reconcile_all_series_and_seasons.py

Cleans and standardizes all series titles, seasons, and catalog keys:
1. Cleans TV titles in `public.lista` so `movie` contains pure series titles
   (e.g., 'Love, Death & Robots' instead of 'love, death & robots, Volume 4').
2. Reconciles `movie_catalog` to keep only canonical series keys.
3. Purges erroneous/obsolete season entries (e.g., 86831_s1) from `tv_season_catalog`.
4. Fully enriches Naruto Season 4 (year 2005, official poster) in `tv_season_catalog`.
5. Synchronizes SQLite replica cache and Supabase cloud tables.
"""

import os
import sys
import re
import json
import sqlite3

sys.path.insert(0, os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv()

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from database import client as supabase_client
import services.catalog_service as catalog_service
import services.tmdb_service as tmdb_service

CATALOG_DB_PATH = catalog_service.CATALOG_DB_PATH

SERIES_TITLE_UPDATES = {
    813: {"movie": "Love, Death & Robots", "season": 4, "tmdb_id": 86831, "poster": "https://image.tmdb.org/t/p/w500/qV6LtEc8FChEzhtTzmiJdQlJFWE.jpg", "p_year": 2025},
    710: {"movie": "Attack on Titan", "season": 4, "tmdb_id": 1429, "poster": "https://image.tmdb.org/t/p/w500/sfbSjGlLHsvFQrMUSNR9RrwZgV1.jpg", "p_year": 2020},
    822: {"movie": "Naruto", "season": 4, "tmdb_id": 46260, "poster": "https://image.tmdb.org/t/p/w500/jN77xxkOJG0dWMQZPu7KHzPFQoZ.jpg", "p_year": 2005},
    823: {"movie": "Naruto Shippuden", "season": 1, "tmdb_id": 31910, "poster": "https://image.tmdb.org/t/p/w500/842myobV2MkoHZuoyxJDV9gdkvb.jpg", "p_year": 2007},
    827: {"movie": "Naruto Shippuden", "season": 2, "tmdb_id": 31910, "poster": "https://image.tmdb.org/t/p/w500/qb1AcfiKlXLKIiR3S4x8YZtr2po.jpg", "p_year": 2007},
    467: {"movie": "Sherlock", "season": 1, "tmdb_id": 19885, "poster": "https://image.tmdb.org/t/p/w500/wQczbo7IKtHjmO49pVWTc2u5pSt.jpg", "p_year": 2010},
    468: {"movie": "Sherlock", "season": 2, "tmdb_id": 19885, "poster": "https://image.tmdb.org/t/p/w500/hSf2frcLiEWAPUZ6wbOMTTNZ7b0.jpg", "p_year": 2012},
    469: {"movie": "Sherlock", "season": 3, "tmdb_id": 19885, "poster": "https://image.tmdb.org/t/p/w500/z9ljxwZUQA2349ZBZAssBXpd0i6.jpg", "p_year": 2014},
    470: {"movie": "Sherlock", "season": 4, "tmdb_id": 19885, "poster": "https://image.tmdb.org/t/p/w500/yVaWUlLmln0xqUDxVFc8JBuzHzK.jpg", "p_year": 2017},
    983: {"movie": "Peaky Blinders", "season": 1, "tmdb_id": 60574, "poster": "https://image.tmdb.org/t/p/w500/vPlsKun2WZEsqe3yZTmebxtwElW.jpg", "p_year": 2013},
    984: {"movie": "Peaky Blinders", "season": 2, "tmdb_id": 60574, "poster": "https://image.tmdb.org/t/p/w500/m4JPtC3gWUsq0GlfNK3SdgkL9XG.jpg", "p_year": 2014},
    486: {"movie": "War & Peace", "season": 1, "tmdb_id": 64099, "poster": "https://image.tmdb.org/t/p/w500/AoSe3KxhX4VhzlJaBEowIH239da.jpg", "p_year": 2016},
    551: {"movie": "Unorthodox", "season": 1, "tmdb_id": 99581, "poster": "https://image.tmdb.org/t/p/w500/5Rfz20IKgC4fIIpnhFn88UJKzW4.jpg", "p_year": 2020},
    573: {"movie": "Shōgun", "season": 1, "tmdb_id": 126308, "poster": "https://image.tmdb.org/t/p/w500/7O4iVfOMQmdCSxhOg1WnzG1AgYT.jpg", "p_year": 2024},
    680: {"movie": "Archangel", "season": 1, "tmdb_id": 30301, "poster": "https://image.tmdb.org/t/p/w500/sDKkCzb2LP2WBMhp80XAQlVWGof.jpg", "p_year": 2005},
    812: {"movie": "Adolescence", "season": 1, "tmdb_id": 249042, "poster": "https://image.tmdb.org/t/p/w500/tDHWWReefmOOjBCJZUck8cNwssk.jpg", "p_year": 2025},
}

KEYS_TO_PURGE_FROM_MOVIE_CATALOG = [
    "lovedeathrobotsvolume4_2019",
    "sherlockseries1_2010",
    "sherlockseries2_2010",
    "sherlockseries3_2010",
    "sherlockseries4_2010",
    "peakyblindersseries2_2013",
    "narutoshippudens1kazekagerescue_2007",
    "narutoshippudens2longawaitedreunion_2007",
    "adolescencelimitedseries_2025",
    "guerraepaceminiseries_2016",
    "unorthodoxlimitedseries_2020",
    "shogunminiseries_2024",
    "archangelminiseries_2005"
]

CANONICAL_SERIES_TO_ENSURE = [
    ("Love, Death & Robots", 2019, 86831),
    ("Attack on Titan", 2013, 1429),
    ("Sherlock", 2010, 19885),
    ("Naruto", 2002, 46260),
    ("Naruto Shippuden", 2007, 31910),
    ("Peaky Blinders", 2013, 60574),
    ("Adolescence", 2025, 249042),
    ("Unorthodox", 2020, 99581),
    ("War and Peace", 2016, 64099),
]

def run_reconciliation():
    print("=" * 70)
    print("RECONCILING SERIES AND TV SEASONS")
    print("=" * 70)

    # 1. Update public.lista rows
    print("\n>> 1. Updating public.lista rows to clean series titles...")
    for lista_id, fields in SERIES_TITLE_UPDATES.items():
        try:
            supabase_client.table("lista").update(fields).eq("lista_id", lista_id).execute()
            print(f"   [OK] lista_id {lista_id} -> {fields.get('movie')} (Season {fields.get('season')})")
        except Exception as e:
            print(f"   [ERR] lista_id {lista_id}: {e}")

    # 2. Ensure canonical series exist in movie_catalog
    print("\n>> 2. Ensuring canonical series rows in movie_catalog...")
    for title, yr, tid in CANONICAL_SERIES_TO_ENSURE:
        try:
            enriched = catalog_service.fetch_and_enrich_from_tmdb(title, yr, tmdb_id=tid, is_tv=True)
            catalog_service.upsert_catalog_item(enriched, compute_embedding=True)
            print(f"   [OK] movie_catalog canonical: {enriched.get('movie_key')} ({enriched.get('title')})")
        except Exception as e:
            print(f"   [ERR] {title}: {e}")

    # 3. Purge obsolete keys from movie_catalog (SQLite & Supabase)
    print("\n>> 3. Purging obsolete alias keys from movie_catalog...")
    with sqlite3.connect(CATALOG_DB_PATH) as conn:
        for k in KEYS_TO_PURGE_FROM_MOVIE_CATALOG:
            conn.execute("DELETE FROM movie_catalog WHERE movie_key = ?", (k,))
            try:
                supabase_client.table("movie_catalog").delete().eq("movie_key", k).execute()
            except Exception:
                pass
            print(f"   [PURGED] movie_catalog: {k}")
        conn.commit()

    # 4. Clean tv_season_catalog
    print("\n>> 4. Cleaning tv_season_catalog...")
    with sqlite3.connect(CATALOG_DB_PATH) as conn:
        # Delete obsolete 86831_s1
        conn.execute("DELETE FROM tv_season_catalog WHERE season_key = '86831_s1'")
        try:
            supabase_client.table("tv_season_catalog").delete().eq("season_key", "86831_s1").execute()
            print("   [PURGED] tv_season_catalog: 86831_s1")
        except Exception:
            pass
        
        # Also clean show_title names in tv_season_catalog
        for tid, s_title in [
            (1429, "Attack on Titan"),
            (86831, "Love, Death & Robots"),
            (19885, "Sherlock"),
            (60574, "Peaky Blinders"),
            (31910, "Naruto Shippuden"),
            (46260, "Naruto")
        ]:
            conn.execute("UPDATE tv_season_catalog SET show_title = ? WHERE tmdb_id = ?", (s_title, tid))
            try:
                supabase_client.table("tv_season_catalog").update({"show_title": s_title}).eq("tmdb_id", tid).execute()
            except Exception:
                pass
            print(f"   [UPDATED] tv_season_catalog titles for tmdb_id {tid} -> '{s_title}'")
        conn.commit()

    # 5. Enrich Naruto Season 4 properly (year=2005, official poster)
    print("\n>> 5. Re-enriching Naruto Season 4...")
    naruto_s4 = catalog_service.fetch_and_enrich_tv_season(46260, 4, show_title="Naruto", force_refresh=True)
    if not naruto_s4.get("year"):
        naruto_s4["year"] = 2005
    if not naruto_s4.get("poster") or "placeholder" in naruto_s4.get("poster"):
        naruto_s4["poster"] = "https://image.tmdb.org/t/p/w500/jN77xxkOJG0dWMQZPu7KHzPFQoZ.jpg"
    catalog_service.upsert_tv_season_catalog_item(naruto_s4, compute_embedding=True)
    print(f"   [OK] Naruto Season 4 enriched: Year {naruto_s4.get('year')}, Poster: {naruto_s4.get('poster')}")

    # 6. Push any local changes to Supabase tv_season_catalog
    print("\n>> 6. Syncing tv_season_catalog to Supabase...")
    sync_stats = catalog_service.sync_local_seasons_to_supabase()
    print(f"   [SYNCED] Synced: {sync_stats['synced']}, Errors: {sync_stats['errors']}")

    print("\n" + "=" * 70)
    print("RECONCILIATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_reconciliation()
