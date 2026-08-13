import sys
import os
import math

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"c:\Users\g.bertone\Desktop\Personal\Projects\webapp_v2")

from database import load_users_from_db, get_movies

users = load_users_from_db()
myks_id = [u.get("id") for u in users if u.get("username") == "Myks"][0]
movies = get_movies(myks_id)

genre_ratings = {}
for m in movies:
    raw_r = m.get("rating")
    if raw_r is None:
        continue
    try:
        r_val = float(raw_r)
        if r_val > 5.0:
            r_val = r_val / 2.0
    except (TypeError, ValueError):
        continue

    genres_raw = m.get("genre") or ""
    for g in [x.strip() for x in genres_raw.split(",") if x.strip()]:
        genre_ratings.setdefault(g, []).append(r_val)

print("--- UNWEIGHTED RAW GENRE AVERAGE (CURRENT BUG) ---")
unweighted = []
for g, ratings in genre_ratings.items():
    avg = sum(ratings) / len(ratings)
    unweighted.append((g, avg, len(ratings)))

for g in sorted(unweighted, key=lambda x: (x[1], x[2]), reverse=True)[:8]:
    print(f"  {g[0]}: Avg {g[1]:.2f} ★ | Count: {g[2]}")

print("\n--- FREQUENCY-WEIGHTED GENRE SCORE (FIX) ---")
# Score = avg_rating * log2(1 + count) OR Bayesian weighting
weighted = []
for g, ratings in genre_ratings.items():
    count = len(ratings)
    avg = sum(ratings) / count
    # Weighted score favors genres watched multiple times with high ratings
    # Require count >= 2 for top affinity, or apply log multiplier
    score = avg * math.log2(1 + count)
    weighted.append((g, avg, count, score))

for g in sorted(weighted, key=lambda x: x[3], reverse=True)[:8]:
    print(f"  {g[0]}: Avg {g[1]:.2f} ★ | Count: {g[2]} | Score: {g[3]:.2f}")
