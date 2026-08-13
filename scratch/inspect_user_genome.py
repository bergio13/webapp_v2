import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"c:\Users\g.bertone\Desktop\Personal\Projects\webapp_v2")

from database import load_users_from_db, get_movies
from recommendation_service import build_user_taste_genome

users = load_users_from_db()
print(f"Found {len(users)} users in Supabase.\n")

for u in users:
    user_id = u.get("id")
    username = u.get("username")
    movies = get_movies(user_id)
    print(f"==================================================")
    print(f"USER: {username} (ID: {user_id}) - Total Movies Logged: {len(movies)}")
    print(f"==================================================")
    
    genome = build_user_taste_genome(movies)
    print("TASTE GENOME SUMMARY:")
    print(genome["summary"])
    print("\nTOP DIRECTORS:")
    print(genome["top_directors"])
    print("\nANCHOR FAVORITES:")
    for fav in genome["anchor_favorites"]:
        print(f"  - {fav}")
    print("\nANTI-PREFERENCES (DISLIKES):")
    if genome["anti_preferences"]:
        for item in genome["anti_preferences"]:
            print(f"  - {item}")
    else:
        print("  - None recorded")
    print("\n")
