import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"c:\Users\g.bertone\Desktop\Personal\Projects\webapp_v2")

from database import load_users_from_db, get_movies

users = load_users_from_db()
myks_id = None
for u in users:
    if u.get("username") == "Myks":
        myks_id = u.get("id")
        break

print(f"Myks User ID: {myks_id}")
movies = get_movies(myks_id)

print("\nALL MOVIES LOGGED BY MYKS:")
for m in movies:
    genres = m.get("genre") or ""
    if "horror" in genres.lower():
        print(f"  [HORROR MATCH] Title: {m.get('movie')} | Rating: {m.get('rating')} | Genres: {genres} | Year: {m.get('p_year')}")

print("\nSAMPLE OF OTHER MOVIES LOGGED BY MYKS:")
for m in movies[:10]:
    print(f"  Title: {m.get('movie')} | Rating: {m.get('rating')} | Genres: {m.get('genre')}")
