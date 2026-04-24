import os
import math
import logging
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASEURL")
SUPABASE_KEY = os.environ.get("SUPABASEKEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase configuration: set SUPABASEURL and SUPABASEKEY.")

client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

#############################################
######## USERS ##############################
#############################################

def _fetch_users_by(column: str = None, value=None):
    """Helper to fetch users dynamically and avoid repeated query logic."""
    try:
        query = client.table('users').select('*')
        if column and value:
            query = query.eq(column, value)
        response = query.execute()
        
        return [
            {
                "id": row.get('id'),
                "username": row.get('username'),
                "email": row.get('email'),
                "password": row.get('password') # Only used when specifically needed
            }
            for row in response.data
        ]
    except Exception as e:
        logger.error(f"Error fetching users by {column}: {e}")
        return []

def load_users_from_db():
    return _fetch_users_by()

def load_users_from_username(name):
    return _fetch_users_by("username", name)

def load_users_from_email(email):
    return _fetch_users_by("email", email)

def get_user_by_id(user_id):
    return _fetch_users_by("id", user_id)

def get_user_name(name):
    # Returns subset of data for safety
    users = _fetch_users_by("username", name)
    return [{"id": u["id"], "username": u["username"]} for u in users]

def get_user_id(name):
    users = _fetch_users_by("username", name)
    return [{"id": u["id"]} for u in users]

def get_user_by_email(email):
    try:
        data = client.table('users').select('*').eq("email", email).single().execute()
        return data.data
    except Exception as e:
        logger.error(f"Error fetching single user by email: {e}")
        return None

def insert_user(username, email, password):
    try:
        client.table('users').insert([{"username": username, "email": email, "password": password}]).execute()
    except Exception as e:
        logger.error(f"Failed to insert user {username}: {e}")
        raise

def update_user_password(user_id, password):
    try:
        client.table('users').update({"password": password}).eq('id', user_id).execute()
    except Exception as e:
        logger.error(f"Failed to update password for user {user_id}: {e}")

#############################################
######## MOVIES #############################
#############################################

def insert_movies(title, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema):
    try:
        payload = {
            "movie": title, "director": director, "genre": genre, 
            "p_year": p_year, "v_date": v_date, "rating": rating, 
            "rewatch": rewatch, "tv_show": tv_show, "poster": poster, 
            "parent_id": parent_id, "cinema": cinema
        }
        client.table('lista').insert(payload).execute()
    except Exception as e:
        logger.error(f"Error inserting movie {title}: {e}")

def get_movies(parent_id):
    try:
        data = client.table('lista').select('*').eq("parent_id", parent_id).execute()
        lista_dicts = []
        for row in data.data:
            movie_dict = {
                "id": row['lista_id'],
                "movie": row['movie'],
                "director": row['director'],
                "genre": row['genre'],
                "p_year": row['p_year'],
                "v_date": datetime.strptime(row['v_date'], "%Y-%m-%d").date() if isinstance(row['v_date'], str) else row['v_date'],
                "rating": row['rating'],
                "rewatch": row['rewatch'],
                "tv_show": row['tv_show'],
                "poster": row['poster'],
                "cinema": row['cinema']
            }
            lista_dicts.append(movie_dict)
        return lista_dicts
    except Exception as e:
        logger.error(f"Error fetching movies for {parent_id}: {e}")
        return []

def get_monthly_movies(parent_id, month):
    try:
        current_year = datetime.now().year
        start_date = datetime(year=current_year, month=month, day=1)
        if month == 12:
            end_date = datetime(year=current_year + 1, month=1, day=1)
        else:
            end_date = datetime(year=current_year, month=month + 1, day=1)

        response = client.table('lista') \
            .select('*') \
            .eq('parent_id', parent_id) \
            .gte('v_date', start_date.strftime('%Y-%m-%d')) \
            .lt('v_date', end_date.strftime('%Y-%m-%d')) \
            .execute()
        
        return [
            {
                "id": row['lista_id'], "movie": row['movie'], "director": row['director'],
                "genre": row['genre'], "p_year": row['p_year'], "v_date": row['v_date'],
                "rating": row['rating'], "rewatch": row['rewatch'], "tv_show": row['tv_show'],
                "poster": row['poster'], "cinema": row['cinema']
            }
            for row in response.data
        ]
    except Exception as e:
        logger.error(f"Error fetching monthly movies: {e}")
        return []

def remove_movie_by_id(movie_id):
    try:
        client.table('lista').delete().eq('lista_id', movie_id).execute()
    except Exception as e:
        logger.error(f"Error removing movie {movie_id}: {e}")

def update_movie(lista_id, movie, director, p_year, rating, poster):
    try:
        client.table('lista').update({
            "movie": movie, "director": director, 
            "p_year": p_year, "rating": rating, "poster": poster
        }).eq('lista_id', lista_id).execute()
    except Exception as e:
        logger.error(f"Error updating movie {lista_id}: {e}")

# --- DRY Fetching for Ordered Lists ---
def _get_movies_ordered_by(parent_id, order_column):
    try:
        data = client.table('lista').select('*').eq('parent_id', parent_id).order(order_column).execute()
        return [
            {
                "id": row['lista_id'], "movie": row['movie'], "director": row['director'],
                "genre": row['genre'], "p_year": row['p_year'], "v_date": row['v_date'],
                "rating": row['rating'], "rewatch": row['rewatch'], "tv_show": row['tv_show'],
                "poster": row['poster']
            }
            for row in data.data
        ]
    except Exception as e:
        logger.error(f"Error fetching ordered movies by {order_column}: {e}")
        return []

def _get_distinct_attribute(parent_id, column):
    try:
        data = client.table('lista').select(column).eq('parent_id', parent_id).order(column).execute()
        return [{"name": attr} for attr in {row[column] for row in data.data if row.get(column)}]
    except Exception as e:
        logger.error(f"Error fetching distinct {column}: {e}")
        return []

def get_movies_groupby_director(parent_id): return _get_movies_ordered_by(parent_id, 'director')
def get_directors(parent_id): return _get_distinct_attribute(parent_id, 'director')
def get_movies_groupby_genre(parent_id): return _get_movies_ordered_by(parent_id, 'genre')
def get_genres(parent_id): return _get_distinct_attribute(parent_id, 'genre')
def get_movies_groupby_year(parent_id): return _get_movies_ordered_by(parent_id, 'p_year')
def get_years(parent_id): return _get_distinct_attribute(parent_id, 'p_year')
def get_movies_groupby_rating(parent_id): return _get_movies_ordered_by(parent_id, 'rating')
def get_ratings(parent_id): return _get_distinct_attribute(parent_id, 'rating')

def get_highest_rating():
    try:
        now = datetime.now()
        start_date = datetime(year=now.year - 1, month=12, day=1) if now.month == 1 else datetime(year=now.year, month=now.month - 1, day=1)
        end_date = datetime(year=now.year + 1, month=1, day=1) if now.month == 12 else datetime(year=now.year, month=now.month + 1, day=1)

        data = client.table('lista') \
            .select('movie', 'director', 'p_year', 'poster') \
            .gte('rating', 9) \
            .gte('v_date', start_date.strftime('%Y-%m-%d')) \
            .lt('v_date', end_date.strftime('%Y-%m-%d')) \
            .execute()
            
        distinct_movies = { (row['movie'], row['director'], row['p_year'], row['poster']) for row in data.data }
        return [{"movie": m[0], "director": m[1], "p_year": m[2], "poster": m[3]} for m in distinct_movies]
    except Exception as e:
        logger.error(f"Error fetching highest rating: {e}")
        return []

#############################################
######## FRIENDS ############################
#############################################

def insert_friends(user_id, f_username, parent_id):
    try:
        client.table('friends').insert({"user_id": user_id, "f_username": f_username, "parent_id": parent_id}).execute()
    except Exception as e:
        logger.error(f"Error inserting friend: {e}")

def get_friends(parent_id):
    try:
        data = client.table('friends').select('*').eq("parent_id", parent_id).execute()
        return [
            {
                "id": row['friend_id'],
                "user_id": row['user_id'],
                "f_username": row['f_username']
            }
            for row in data.data
        ]
    except Exception as e:
        logger.error(f"Error fetching friends: {e}")
        return []

def get_friend_activity(parent_id, limit=20):
    try:
        friends = get_friends(parent_id)
        if not friends:
            return []
        
        friend_ids = [f['user_id'] for f in friends]
        friend_map = {f['user_id']: f['f_username'] for f in friends}
        
        data = client.table('lista') \
            .select('*') \
            .in_('parent_id', friend_ids) \
            .order('v_date', desc=True) \
            .limit(limit) \
            .execute()
            
        lista_dicts = []
        for row in data.data:
            try:
                v_date_obj = datetime.strptime(row['v_date'], "%Y-%m-%d").date()
            except:
                v_date_obj = row['v_date']
                
            lista_dicts.append({
                "id": row['lista_id'], "movie": row['movie'], "director": row['director'],
                "genre": row['genre'], "p_year": row['p_year'], "v_date": v_date_obj,
                "rating": row['rating'], "rewatch": row['rewatch'], "tv_show": row['tv_show'],
                "poster": row['poster'], "cinema": row['cinema'],
                "f_username": friend_map.get(row['parent_id'], "Unknown"),
                "f_user_id": row['parent_id']
            })
        return lista_dicts
    except Exception as e:
        logger.error(f"Error fetching friend activity: {e}")
        return []

def remove_friend(parent_id, friend_id):
    try:
        client.table('friends').delete().eq('parent_id', parent_id).eq('user_id', friend_id).execute()
    except Exception as e:
        logger.error(f"Error removing friend {friend_id}: {e}")

def get_taste_match(user_id, friend_id):
    try:
        user_movies = get_movies(user_id)
        friend_movies = get_movies(friend_id)
        
        # 1. Create fast lookups and determine unique libraries
        user_dict = {f"{m['movie'].lower()}_{m['p_year']}": m['rating'] for m in user_movies}
        friend_dict = {f"{m['movie'].lower()}_{m['p_year']}": m['rating'] for m in friend_movies}
        
        shared_keys = set(user_dict.keys()).intersection(set(friend_dict.keys()))
        total_unique_movies = len(set(user_dict.keys()).union(set(friend_dict.keys())))
        shared_count = len(shared_keys)
        
        if shared_count == 0:
            return {
                "match_percent": 0, "shared_count": 0, "shared_movies": [],
                "library_overlap": 0, "rating_similarity": 0, "harsher_critic": "None"
            }
            
        shared_movies = []
        sum_squared_diff = 0
        user_rating_sum = 0
        friend_rating_sum = 0

        for m in friend_movies:
            key = f"{m['movie'].lower()}_{m['p_year']}"
            if key in shared_keys:
                u_rating = user_dict[key]
                f_rating = m['rating']
                
                diff = abs(u_rating - f_rating)
                sum_squared_diff += diff ** 2
                
                user_rating_sum += u_rating
                friend_rating_sum += f_rating
                
                shared_movies.append({
                    "movie": m['movie'], "poster": m['poster'], "year": m['p_year'],
                    "u_rating": u_rating, "f_rating": f_rating, "diff": diff
                })
                
        # 2. Root Mean Square Error (RMSE)
        rmse = math.sqrt(sum_squared_diff / shared_count)
        rating_match_score = max(0, min(100, 100 - (rmse * 10)))
        
        # 3. Jaccard Index (Library Overlap)
        overlap_percent = (shared_count / total_unique_movies) * 100 if total_unique_movies > 0 else 0
        
        # 4. Confidence Scaling
        confidence_multiplier = min(1.0, shared_count / 5.0) 
        final_match_percent = rating_match_score * confidence_multiplier

        # Sort shared movies by biggest agreements first, then by highest user rating
        shared_movies.sort(key=lambda x: (x['diff'], -x['u_rating']))
        
        if user_rating_sum < friend_rating_sum:
            harsher_critic = "You"
        elif friend_rating_sum < user_rating_sum:
            harsher_critic = "Friend"
        else:
            harsher_critic = "Equal"
        
        return {
            "match_percent": int(final_match_percent),
            "shared_count": shared_count,
            "shared_movies": shared_movies,
            "library_overlap": int(overlap_percent),
            "rating_similarity": int(rating_match_score),
            "harsher_critic": harsher_critic
        }
    except Exception as e:
        logger.error(f"Error calculating taste match: {e}")
        return {
            "match_percent": 0, "shared_count": 0, "shared_movies": [],
            "library_overlap": 0, "rating_similarity": 0, "harsher_critic": "Error"
        }

#############################################
####### TOKENS ##############################
#############################################

def insert_token(user_id, token, date):
    try:
        client.table('tokens').insert([{'token': token, 'user_id': user_id, 'created_at': date}]).execute()
    except Exception as e:
        logger.error(f"Error inserting token: {e}")

def get_token(token):
    try:
        data = client.table('tokens').select('*').eq("token", token).single().execute()
        return data.data
    except Exception as e:
        logger.error(f"Error fetching token: {e}")
        return None

def delete_token(token):
    try:
        client.table('tokens').delete().eq('token', token).execute()
    except Exception as e:
        logger.error(f"Error deleting token: {e}")