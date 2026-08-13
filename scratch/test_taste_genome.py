import sys
import os

# Add root directory to sys.path
sys.path.insert(0, r"c:\Users\g.bertone\Desktop\Personal\Projects\webapp_v2")

from recommendation_service import build_user_taste_genome

# Sample movie database records on 1-5 scale with view dates
test_movies = [
    {"movie": "Inception", "p_year": 2010, "rating": 5.0, "v_date": "2020-01-01", "director": "Christopher Nolan", "genre": "Sci-Fi, Action"},
    {"movie": "Interstellar", "p_year": 2014, "rating": 5.0, "v_date": "2024-05-10", "director": "Christopher Nolan", "genre": "Sci-Fi, Drama"},
    {"movie": "Dune: Part Two", "p_year": 2024, "rating": 5.0, "v_date": "2026-02-01", "director": "Denis Villeneuve", "genre": "Sci-Fi, Adventure"},
    {"movie": "The Dark Knight", "p_year": 2008, "rating": 5.0, "v_date": "2019-11-20", "director": "Christopher Nolan", "genre": "Action, Crime"},
    {"movie": "The Matrix", "p_year": 1999, "rating": 4.5, "v_date": "2025-08-01", "director": "Lana Wachowski, Lilly Wachowski", "genre": "Sci-Fi, Action"},
    {"movie": "Cats", "p_year": 2019, "rating": 1.0, "v_date": "2021-03-01", "director": "Tom Hooper", "genre": "Musical, Comedy"}
]

genome = build_user_taste_genome(test_movies)

print("--- GENERATED TASTE GENOME ---")
print(genome["summary"])
print("------------------------------")
