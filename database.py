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

def get_movies_paginated(parent_id, order_column='v_date', desc=True, page=1, limit=50, search=None, rating=None, media_type=None, cinema=None, rewatch=None, year=None):
    start_index = (page - 1) * limit
    end_index = start_index + limit - 1
    
    try:
        query = client.table('lista').select('*', count='exact').eq('parent_id', parent_id)
        
        if search:
            clean_search = search.strip()
            if clean_search.isdigit() and len(clean_search) == 4:
                query = query.or_(f"movie.ilike.%{clean_search}%,director.ilike.%{clean_search}%,p_year.eq.{int(clean_search)}")
            else:
                query = query.or_(f"movie.ilike.%{clean_search}%,director.ilike.%{clean_search}%")

        if year is not None and str(year).isdigit():
            query = query.eq('p_year', int(year))

        if rating is not None and str(rating).isdigit() and int(rating) in [1, 2, 3, 4, 5]:
            r_int = int(rating)
            query = query.or_(f"rating.eq.{r_int},rating.eq.{r_int * 2},rating.eq.{r_int * 2 - 1}")

        if media_type == 'movie':
            query = query.or_('tv_show.eq.0,tv_show.is.null')
        elif media_type == 'tv':
            query = query.eq('tv_show', 1)

        if cinema is not None and int(cinema) == 1:
            query = query.eq('cinema', 1)

        if rewatch is not None and int(rewatch) == 1:
            query = query.eq('rewatch', 1)
            
        data = query.order(order_column, desc=desc) \
            .range(start_index, end_index) \
            .execute()
            
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
            
        total_count = getattr(data, 'count', len(lista_dicts))
        if total_count is None:
            total_count = len(lista_dicts)
            
        return lista_dicts, total_count
    except Exception as e:
        logger.error(f"Pagination error for {parent_id}: {e}")
        return [], 0

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
            .gte('rating', 5) \
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
        
        # 1. Deduplicate within each user's library using a strong primary key (title + director + year)
        def get_primary_key(m):
            return f"{m['movie'].lower().strip()}_{m.get('director', '').lower().strip()}_{m['p_year']}"
        
        user_movies_clean = {}
        for m in user_movies:
            k = get_primary_key(m)
            if k not in user_movies_clean or m['rating'] > user_movies_clean[k]['rating']:
                user_movies_clean[k] = m

        friend_movies_clean = {}
        for m in friend_movies:
            k = get_primary_key(m)
            if k not in friend_movies_clean or m['rating'] > friend_movies_clean[k]['rating']:
                friend_movies_clean[k] = m

        # 2. Find matches
        shared_movie_pairs = []
        user_matched_keys = set()
        friend_matched_keys = set()

        # Pass 1: Match by Title + Director + Year
        for u_key, u_m in user_movies_clean.items():
            if u_key in friend_movies_clean:
                f_m = friend_movies_clean[u_key]
                user_matched_keys.add(u_key)
                friend_matched_keys.add(u_key)
                shared_movie_pairs.append((u_m, f_m))

        # Pass 2: Match by Director + Year alone (Fallback to handle language differences)
        user_dir_year_map = {}
        for u_key, m in user_movies_clean.items():
            if u_key not in user_matched_keys:
                director = m.get('director', '').lower().strip()
                year = m['p_year']
                if director and year and director != "unknown":
                    dy_key = f"{director}_{year}"
                    user_dir_year_map[dy_key] = m

        # Helper for Pass 2 verification
        import difflib
        def verify_movie_match(m1, m2):
            # 1. Poster Match (Strongest signal)
            p1 = m1.get('poster', '')
            p2 = m2.get('poster', '')
            if p1 and p2 and p1 == p2 and 'tmdb.org' in p1:
                return True
                
            # 2. Title Similarity (Handles slight variations or subtitles)
            t1 = m1['movie'].lower().strip()
            t2 = m2['movie'].lower().strip()
            if len(t1) > 3 and len(t2) > 3:
                if t1 in t2 or t2 in t1:
                    return True
            ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
            if ratio > 0.65:
                return True
                
            # 3. Genre Match (Good signal since they already share director & year)
            g1 = m1.get('genre', '').lower().strip()
            g2 = m2.get('genre', '').lower().strip()
            if g1 and g2 and g1 != "unknown" and g1 == g2:
                return True
                
            return False

        for f_key, m in friend_movies_clean.items():
            if f_key not in friend_matched_keys:
                director = m.get('director', '').lower().strip()
                year = m['p_year']
                if director and year and director != "unknown":
                    dy_key = f"{director}_{year}"
                    if dy_key in user_dir_year_map:
                        u_m = user_dir_year_map[dy_key]
                        if verify_movie_match(u_m, m):
                            shared_movie_pairs.append((u_m, m))
                            friend_matched_keys.add(f_key) # mark as matched

        total_unique_movies = len(user_movies_clean) + len(friend_movies_clean) - len(shared_movie_pairs)
        shared_count = len(shared_movie_pairs)
        
        if shared_count == 0:
            return {
                "match_percent": 0, "shared_count": 0, "shared_movies": [],
                "library_overlap": 0, "rating_similarity": 0, "harsher_critic": "None"
            }
            
        shared_movies = []
        sum_squared_diff = 0
        user_rating_sum = 0
        friend_rating_sum = 0

        for u_m, f_m in shared_movie_pairs:
            u_rating = u_m['rating']
            f_rating = f_m['rating']
            
            diff = abs(u_rating - f_rating)
            sum_squared_diff += diff ** 2
            
            user_rating_sum += u_rating
            friend_rating_sum += f_rating
            
            shared_movies.append({
                "movie": f_m['movie'], "poster": f_m['poster'], "year": f_m['p_year'],
                "u_rating": u_rating, "f_rating": f_rating, "diff": diff
            })
                
        # 2. Root Mean Square Error (RMSE) on 5-Point Sentiment Scale
        rmse = math.sqrt(sum_squared_diff / shared_count)
        rating_match_score = max(0, min(100, 100 - (rmse * 20)))
        
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

#############################################
####### WATCHLISTS ##########################
#############################################

def get_or_create_personal_watchlist(user_id):
    try:
        data = client.table('watchlists').select('*').eq('user1_id', user_id).is_('user2_id', 'null').execute()
        if data.data:
            return data.data[0]
        else:
            new_list = client.table('watchlists').insert({"user1_id": user_id}).execute()
            return new_list.data[0]
    except Exception as e:
        logger.error(f"Error getting/creating personal watchlist: {e}")
        return None

def get_or_create_shared_watchlist(user1_id, user2_id):
    try:
        # Check both ordering permutations
        data = client.table('watchlists').select('*').eq('user1_id', user1_id).eq('user2_id', user2_id).execute()
        if data.data: return data.data[0]
        data = client.table('watchlists').select('*').eq('user1_id', user2_id).eq('user2_id', user1_id).execute()
        if data.data: return data.data[0]
        
        new_list = client.table('watchlists').insert({"user1_id": min(user1_id, user2_id), "user2_id": max(user1_id, user2_id)}).execute()
        return new_list.data[0]
    except Exception as e:
        logger.error(f"Error getting/creating shared watchlist: {e}")
        return None

def get_watchlist_items(watchlist_id):
    try:
        # Fetch items and join with user to get added_by username
        data = client.table('watchlist_items').select('*, users!inner(username)').eq('watchlist_id', watchlist_id).order('created_at', desc=True).execute()
        items = []
        for row in data.data:
            item = row.copy()
            item['added_by_name'] = row['users']['username']
            items.append(item)
        return items
    except Exception as e:
        logger.error(f"Error fetching watchlist items: {e}")
        return []

def add_to_watchlist(watchlist_id, added_by, title, director, year, poster):
    try:
        client.table('watchlist_items').insert({
            "watchlist_id": watchlist_id,
            "added_by": added_by,
            "title": title,
            "director": director,
            "p_year": year,
            "poster": poster
        }).execute()
    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}")

def remove_from_watchlist(item_id):
    try:
        client.table('watchlist_items').delete().eq('id', item_id).execute()
    except Exception as e:
        logger.error(f"Error removing from watchlist: {e}")