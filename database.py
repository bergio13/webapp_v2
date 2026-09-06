import os
import re
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

def search_users_by_query(query_str: str, limit=10):
    try:
        clean_q = (query_str or "").strip()
        if not clean_q:
            return []
        data = client.table('users').select('id, username').ilike('username', f"%{clean_q}%").limit(limit).execute()
        return [{"id": row["id"], "username": row["username"]} for row in data.data]
    except Exception as e:
        logger.error(f"Error searching users by query '{query_str}': {e}")
        return []

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

def _normalize_flag(val):
    if val in (1, '1', True, 'true', 'True'):
        return 1
    return 0

#############################################
######## MOVIES #############################
#############################################

def insert_movies(title, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema, season=None, tmdb_id=None):
    try:
        payload = {
            "movie": title, "director": director, "genre": genre, 
            "p_year": p_year, "v_date": v_date, "rating": rating, 
            "rewatch": _normalize_flag(rewatch), "tv_show": _normalize_flag(tv_show), "poster": poster, 
            "parent_id": parent_id, "cinema": _normalize_flag(cinema)
        }
        if season is not None:
            try:
                payload["season"] = int(season)
            except (ValueError, TypeError):
                pass
        if tmdb_id is not None:
            try:
                payload["tmdb_id"] = int(tmdb_id)
            except (ValueError, TypeError):
                pass
        client.table('lista').insert(payload).execute()
    except Exception as e:
        logger.error(f"Error inserting movie {title}: {e}")

def get_movies(parent_id):
    try:
        from utils import format_display_title
        data = client.table('lista').select('*').eq("parent_id", parent_id).execute()
        lista_dicts = []
        for row in data.data:
            movie_dict = {
                "id": row['lista_id'],
                "movie": format_display_title(row['movie'], season=row.get('season')),
                "series_title": row['movie'],
                "director": row['director'],
                "genre": row['genre'],
                "p_year": row['p_year'],
                "v_date": datetime.strptime(row['v_date'], "%Y-%m-%d").date() if isinstance(row['v_date'], str) else row['v_date'],
                "rating": row['rating'],
                "rewatch": _normalize_flag(row.get('rewatch')),
                "tv_show": _normalize_flag(row.get('tv_show')),
                "poster": row['poster'],
                "cinema": _normalize_flag(row.get('cinema')),
                "season": row.get('season'),
                "tmdb_id": row.get('tmdb_id')
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
                s_match = re.search(r'(?i)\bseason\s*(\d+)\b', clean_search)
                if s_match:
                    season_num = int(s_match.group(1))
                    clean_title_search = re.sub(r'(?i)\bseason\s*\d+\b', '', clean_search).strip(' ,-')
                    if clean_title_search:
                        query = query.ilike('movie', f'%{clean_title_search}%').eq('season', season_num)
                    else:
                        query = query.eq('season', season_num)
                else:
                    query = query.or_(f"movie.ilike.%{clean_search}%,director.ilike.%{clean_search}%")

        if year is not None and str(year).isdigit():
            query = query.eq('p_year', int(year))

        if rating is not None and str(rating).isdigit() and int(rating) in [1, 2, 3, 4, 5]:
            r_int = int(rating)
            query = query.eq('rating', r_int)

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
            
        from utils import format_display_title
        lista_dicts = []
        for row in data.data:
            movie_dict = {
                "id": row['lista_id'],
                "movie": format_display_title(row['movie'], season=row.get('season')),
                "series_title": row['movie'],
                "director": row['director'],
                "genre": row['genre'],
                "p_year": row['p_year'],
                "v_date": datetime.strptime(row['v_date'], "%Y-%m-%d").date() if isinstance(row['v_date'], str) else row['v_date'],
                "rating": row['rating'],
                "rewatch": _normalize_flag(row.get('rewatch')),
                "tv_show": _normalize_flag(row.get('tv_show')),
                "poster": row['poster'],
                "cinema": _normalize_flag(row.get('cinema')),
                "season": row.get('season'),
                "tmdb_id": row.get('tmdb_id')
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
        from utils import format_display_title
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
                "id": row['lista_id'], 
                "movie": format_display_title(row['movie'], season=row.get('season')),
                "series_title": row['movie'],
                "director": row['director'],
                "genre": row['genre'], 
                "p_year": row['p_year'], 
                "v_date": row['v_date'],
                "rating": row['rating'], 
                "rewatch": _normalize_flag(row.get('rewatch')), 
                "tv_show": _normalize_flag(row.get('tv_show')),
                "poster": row['poster'], 
                "cinema": _normalize_flag(row.get('cinema')),
                "season": row.get('season'),
                "tmdb_id": row.get('tmdb_id')
            }
            for row in response.data
        ]
    except Exception as e:
        logger.error(f"Error fetching monthly movies: {e}")
        return []

def get_yearly_movie_and_cinema_counts(parent_id, year=None):
    """Fetch both total yearly movies watched and cinema visits in a single fast query."""
    try:
        if year is None:
            year = datetime.now().year
        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"
        response = client.table('lista') \
            .select('lista_id, cinema') \
            .eq('parent_id', parent_id) \
            .gte('v_date', start_date) \
            .lt('v_date', end_date) \
            .execute()
        rows = response.data or []
        yearly_count = len(rows)
        yearly_cinema_count = sum(1 for r in rows if _normalize_flag(r.get('cinema')) == 1)
        return yearly_count, yearly_cinema_count
    except Exception as e:
        logger.error(f"Error fetching yearly counts for {parent_id}: {e}")
        return 0, 0

def get_yearly_movie_count(parent_id, year=None):
    try:
        if year is None:
            year = datetime.now().year
        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"
        response = client.table('lista') \
            .select('lista_id', count='exact') \
            .eq('parent_id', parent_id) \
            .gte('v_date', start_date) \
            .lt('v_date', end_date) \
            .execute()
        return getattr(response, 'count', len(response.data or []))
    except Exception as e:
        logger.error(f"Error fetching yearly movie count for {parent_id}: {e}")
        return 0

def get_yearly_cinema_count(parent_id, year=None):
    try:
        if year is None:
            year = datetime.now().year
        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"
        response = client.table('lista') \
            .select('lista_id', count='exact') \
            .eq('parent_id', parent_id) \
            .gte('v_date', start_date) \
            .lt('v_date', end_date) \
            .eq('cinema', 1) \
            .execute()
        return getattr(response, 'count', len(response.data or []))
    except Exception as e:
        logger.error(f"Error fetching yearly cinema count for {parent_id}: {e}")
        return 0

def remove_movie_by_id(movie_id):
    try:
        client.table('lista').delete().eq('lista_id', movie_id).execute()
    except Exception as e:
        logger.error(f"Error removing movie {movie_id}: {e}")

def update_movie(lista_id, movie, director, p_year, rating, poster, season=None, tmdb_id=None):
    try:
        payload = {
            "movie": movie, "director": director, 
            "p_year": p_year, "rating": rating, "poster": poster
        }
        if season is not None:
            try:
                payload["season"] = int(season)
            except (ValueError, TypeError):
                pass
        if tmdb_id is not None:
            try:
                payload["tmdb_id"] = int(tmdb_id)
            except (ValueError, TypeError):
                pass
        client.table('lista').update(payload).eq('lista_id', lista_id).execute()
    except Exception as e:
        logger.error(f"Error updating movie {lista_id}: {e}")

# --- DRY Fetching for Ordered Lists ---
def _get_movies_ordered_by(parent_id, order_column):
    try:
        from utils import format_display_title
        data = client.table('lista').select('*').eq('parent_id', parent_id).order(order_column).execute()
        return [
            {
                "id": row['lista_id'], 
                "movie": format_display_title(row['movie'], season=row.get('season')), 
                "series_title": row['movie'],
                "director": row['director'],
                "genre": row['genre'], 
                "p_year": row['p_year'], 
                "v_date": row['v_date'],
                "rating": row['rating'], 
                "rewatch": row['rewatch'], 
                "tv_show": row['tv_show'],
                "poster": row['poster'],
                "season": row.get('season'),
                "tmdb_id": row.get('tmdb_id')
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
            
        from utils import format_display_title
        lista_dicts = []
        for row in data.data:
            try:
                v_date_obj = datetime.strptime(row['v_date'], "%Y-%m-%d").date()
            except:
                v_date_obj = row['v_date']
                
            lista_dicts.append({
                "id": row['lista_id'], 
                "movie": format_display_title(row['movie'], season=row.get('season')), 
                "series_title": row['movie'],
                "director": row['director'],
                "genre": row['genre'], 
                "p_year": row['p_year'], 
                "v_date": v_date_obj,
                "rating": row['rating'], 
                "rewatch": _normalize_flag(row.get('rewatch')), 
                "tv_show": _normalize_flag(row.get('tv_show')),
                "poster": row['poster'], 
                "cinema": _normalize_flag(row.get('cinema')),
                "season": row.get('season'),
                "tmdb_id": row.get('tmdb_id'),
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

def get_enriched_friends(parent_id):
    try:
        friends = get_friends(parent_id)
        if not friends:
            return []
        
        from utils import format_display_title
        friend_ids = [f.get('user_id') for f in friends if f.get('user_id')]
        
        # Batch fetch all movies for all friends in 1 query
        movies_by_friend = {uid: [] for uid in friend_ids}
        if friend_ids:
            try:
                res = client.table('lista').select('*').in_('parent_id', friend_ids).execute()
                for row in (res.data or []):
                    uid = row.get('parent_id')
                    if uid in movies_by_friend:
                        try:
                            v_date_obj = datetime.strptime(row['v_date'], "%Y-%m-%d").date() if isinstance(row['v_date'], str) else row['v_date']
                        except Exception:
                            v_date_obj = row['v_date']
                        movies_by_friend[uid].append({
                            "id": row.get('lista_id'),
                            "movie": format_display_title(row.get('movie'), season=row.get('season')),
                            "series_title": row.get('movie'),
                            "director": row.get('director'),
                            "genre": row.get('genre'),
                            "p_year": row.get('p_year'),
                            "v_date": v_date_obj,
                            "rating": row.get('rating'),
                            "rewatch": _normalize_flag(row.get('rewatch')),
                            "tv_show": _normalize_flag(row.get('tv_show')),
                            "poster": row.get('poster'),
                            "cinema": _normalize_flag(row.get('cinema')),
                            "season": row.get('season'),
                            "tmdb_id": row.get('tmdb_id')
                        })
            except Exception as e:
                logger.error(f"Error batch fetching friend movies: {e}")

        enriched = []
        for f in friends:
            f_uid = f.get('user_id')
            f_movies = movies_by_friend.get(f_uid, [])
            film_count = len(f_movies)
            cinephile_level = max(1, film_count // 20)
            
            # Top genre
            genre_counts = {}
            for m in f_movies:
                g_str = m.get('genre') or ''
                if g_str and g_str.lower() != 'unknown':
                    for g in g_str.split(','):
                        g_clean = g.strip()
                        if g_clean:
                            genre_counts[g_clean] = genre_counts.get(g_clean, 0) + 1
            favorite_genre = max(genre_counts, key=genre_counts.get) if genre_counts else "Cinema"
            
            # Last log
            last_log = None
            if f_movies:
                def _sort_vdate(m):
                    v = m.get('v_date')
                    if isinstance(v, datetime):
                        return v.date()
                    elif isinstance(v, str):
                        try:
                            return datetime.strptime(v, "%Y-%m-%d").date()
                        except Exception:
                            pass
                    return v or datetime.min.date()
                
                sorted_m = sorted(f_movies, key=_sort_vdate, reverse=True)
                top_m = sorted_m[0]
                last_log = {
                    "movie": top_m.get("movie", "Untitled"),
                    "rating": top_m.get("rating", 0),
                    "p_year": top_m.get("p_year", ""),
                    "poster": top_m.get("poster", "")
                }
                
            enriched.append({
                "id": f.get('id'),
                "user_id": f.get('user_id'),
                "f_username": f.get('f_username'),
                "film_count": film_count,
                "cinephile_level": cinephile_level,
                "favorite_genre": favorite_genre,
                "last_log": last_log,
                "sync_score": None  # Fast on-demand via /compare/<username>
            })
        return enriched
    except Exception as e:
        logger.error(f"Error fetching enriched friends for {parent_id}: {e}")
        return get_friends(parent_id)

def get_taste_match(user_id, friend_id):
    try:
        user_movies = get_movies(user_id)
        friend_movies = get_movies(friend_id)
        
        def safe_genres_list(g_str):
            if not g_str or not isinstance(g_str, str):
                return []
            return [g.strip() for g in g_str.split(',') if g.strip() and g.strip().lower() != 'unknown']

        def norm_title(t):
            return ''.join(c for c in (t or '').lower() if c.isalnum() or c.isspace()).strip()
            
        def get_primary_key(m):
            return f"{norm_title(m.get('movie'))}_{norm_title(m.get('director'))}_{m.get('p_year', '')}"
            
        user_movies_clean = {}
        for m in user_movies:
            k = get_primary_key(m)
            r = float(m.get('rating') or 3)
            if r > 5: r = math.ceil(r / 2)
            m_copy = dict(m, rating=int(max(1, min(5, round(r)))))
            if k not in user_movies_clean or m_copy['rating'] > user_movies_clean[k]['rating']:
                user_movies_clean[k] = m_copy
                
        friend_movies_clean = {}
        for m in friend_movies:
            k = get_primary_key(m)
            r = float(m.get('rating') or 3)
            if r > 5: r = math.ceil(r / 2)
            m_copy = dict(m, rating=int(max(1, min(5, round(r)))))
            if k not in friend_movies_clean or m_copy['rating'] > friend_movies_clean[k]['rating']:
                friend_movies_clean[k] = m_copy
                
        shared_movie_pairs = []
        user_matched_keys = set()
        friend_matched_keys = set()
        
        # Pass 1: Match by title + director + year
        for u_key, u_m in user_movies_clean.items():
            if u_key in friend_movies_clean:
                f_m = friend_movies_clean[u_key]
                user_matched_keys.add(u_key)
                friend_matched_keys.add(u_key)
                shared_movie_pairs.append((u_m, f_m))
                
        # Pass 2: Match by Title + Year or exact Poster
        for u_key, u_m in user_movies_clean.items():
            if u_key not in user_matched_keys:
                u_norm = norm_title(u_m.get('movie'))
                u_year = u_m.get('p_year')
                u_post = u_m.get('poster') or ''
                for f_key, f_m in friend_movies_clean.items():
                    if f_key not in friend_matched_keys:
                        f_norm = norm_title(f_m.get('movie'))
                        f_year = f_m.get('p_year')
                        f_post = f_m.get('poster') or ''
                        
                        is_match = False
                        if u_year and f_year and u_year == f_year and u_norm and f_norm and u_norm == f_norm:
                            is_match = True
                        elif u_post and f_post and u_post == f_post and 'tmdb.org' in u_post:
                            is_match = True
                            
                        if is_match:
                            user_matched_keys.add(u_key)
                            friend_matched_keys.add(f_key)
                            shared_movie_pairs.append((u_m, f_m))
                            break

        user_total = len(user_movies_clean)
        friend_total = len(friend_movies_clean)
        shared_count = len(shared_movie_pairs)
        total_unique = user_total + friend_total - shared_count
        
        u_avg = round(sum(m['rating'] for m in user_movies_clean.values()) / user_total, 2) if user_total else 0.0
        f_avg = round(sum(m['rating'] for m in friend_movies_clean.values()) / friend_total, 2) if friend_total else 0.0
        
        # Genre Affinity Analysis
        u_genre_ratings = {}
        f_genre_ratings = {}
        for m in user_movies_clean.values():
            for g in safe_genres_list(m.get('genre')):
                u_genre_ratings.setdefault(g, []).append(m['rating'])
        for m in friend_movies_clean.values():
            for g in safe_genres_list(m.get('genre')):
                f_genre_ratings.setdefault(g, []).append(m['rating'])
                
        shared_genres = set(u_genre_ratings.keys()).intersection(f_genre_ratings.keys())
        genre_diffs = []
        genre_comparison = []
        for g in shared_genres:
            u_g_avg = sum(u_genre_ratings[g]) / len(u_genre_ratings[g])
            f_g_avg = sum(f_genre_ratings[g]) / len(f_genre_ratings[g])
            genre_diffs.append(abs(u_g_avg - f_g_avg))
            genre_comparison.append({
                "genre": g,
                "u_avg": round(u_g_avg, 1),
                "f_avg": round(f_g_avg, 1),
                "u_count": len(u_genre_ratings[g]),
                "f_count": len(f_genre_ratings[g]),
                "total_count": len(u_genre_ratings[g]) + len(f_genre_ratings[g])
            })
        genre_comparison.sort(key=lambda x: -x['total_count'])
        
        if genre_diffs:
            avg_g_diff = sum(genre_diffs) / len(genre_diffs)
            genre_alignment = max(0, min(100, 100 - (avg_g_diff * 25)))
        else:
            genre_alignment = 60.0

        shared_movies = []
        mutual_favorites = []
        biggest_debates = []
        
        diffs = [abs(um['rating'] - fm['rating']) for um, fm in shared_movie_pairs]
        
        from utils import format_display_title
        for um, fm in shared_movie_pairs:
            u_r, f_r = um['rating'], fm['rating']
            diff = abs(u_r - f_r)
            s_val = fm.get('season') or um.get('season')
            item = {
                "movie": format_display_title(fm.get('movie') or um.get('movie'), season=s_val),
                "series_title": fm.get('movie') or um.get('movie'),
                "poster": fm.get('poster') or um.get('poster'),
                "year": fm.get('p_year') or um.get('p_year'),
                "director": fm.get('director') or um.get('director'),
                "genre": fm.get('genre') or um.get('genre'),
                "tv_show": fm.get('tv_show') or um.get('tv_show'),
                "season": s_val,
                "u_rating": u_r,
                "f_rating": f_r,
                "diff": diff
            }
            shared_movies.append(item)
            if u_r >= 4 and f_r >= 4:
                mutual_favorites.append(item)
            if diff >= 2:
                biggest_debates.append(item)
                
        shared_movies.sort(key=lambda x: (x['diff'], -x['u_rating']))
        mutual_favorites.sort(key=lambda x: -(x['u_rating'] + x['f_rating']))
        biggest_debates.sort(key=lambda x: -x['diff'])

        if shared_count > 0:
            agreement_points = sum(1.0 if d == 0 else (0.8 if d == 1 else (0.4 if d == 2 else 0.0)) for d in diffs)
            rating_similarity = round((agreement_points / shared_count) * 100)
            agreement_rate = round((sum(1 for d in diffs if d == 0) / shared_count) * 100)
            library_overlap = round((shared_count / total_unique) * 100) if total_unique else 0
            raw_composite = 0.60 * rating_similarity + 0.25 * genre_alignment + 0.15 * min(100, library_overlap * 3)
            final_match = round((shared_count * raw_composite + 3 * 50) / (shared_count + 3))
        else:
            rating_similarity = 0
            agreement_rate = 0
            library_overlap = 0
            final_match = round(genre_alignment * 0.5) if (user_total and friend_total) else 0

        final_match = max(1, min(100, final_match)) if (user_total and friend_total) else 0

        # Cross Recommendations (top rated blindspots)
        recs_for_you = [
            m for k, m in friend_movies_clean.items() if k not in friend_matched_keys and m['rating'] >= 4
        ]
        recs_for_you.sort(key=lambda x: (-x['rating'], -int(x.get('p_year') or 0)))
        recs_for_you = recs_for_you[:8]

        recs_for_friend = [
            m for k, m in user_movies_clean.items() if k not in user_matched_keys and m['rating'] >= 4
        ]
        recs_for_friend.sort(key=lambda x: (-x['rating'], -int(x.get('p_year') or 0)))
        recs_for_friend = recs_for_friend[:8]

        if shared_count > 0:
            u_shared_avg = round(sum(um['rating'] for um, fm in shared_movie_pairs) / shared_count, 2)
            f_shared_avg = round(sum(fm['rating'] for um, fm in shared_movie_pairs) / shared_count, 2)
            critic_delta = round(abs(u_shared_avg - f_shared_avg), 2)
            if critic_delta == 0.0:
                harsher_critic = "Equal"
            elif u_shared_avg < f_shared_avg:
                harsher_critic = "You"
            else:
                harsher_critic = "Friend"
        else:
            u_shared_avg = u_avg
            f_shared_avg = f_avg
            critic_delta = round(abs(u_avg - f_avg), 2)
            if critic_delta == 0.0:
                harsher_critic = "Equal"
            elif u_avg < f_avg:
                harsher_critic = "You"
            else:
                harsher_critic = "Friend"

        return {
            "match_percent": int(final_match),
            "shared_count": shared_count,
            "user_total": user_total,
            "friend_total": friend_total,
            "u_avg": u_avg,
            "f_avg": f_avg,
            "u_shared_avg": u_shared_avg,
            "f_shared_avg": f_shared_avg,
            "critic_delta": critic_delta,
            "shared_movies": shared_movies,
            "mutual_favorites": mutual_favorites,
            "biggest_debates": biggest_debates,
            "recommendations_for_you": recs_for_you,
            "recommendations_for_friend": recs_for_friend,
            "genre_comparison": genre_comparison[:6],
            "library_overlap": int(library_overlap),
            "rating_similarity": int(rating_similarity),
            "agreement_rate": int(agreement_rate),
            "harsher_critic": harsher_critic
        }
    except Exception as e:
        logger.error(f"Error calculating taste match: {e}")
        return {
            "match_percent": 0, "shared_count": 0, "user_total": 0, "friend_total": 0,
            "u_avg": 0, "f_avg": 0, "u_shared_avg": 0, "f_shared_avg": 0, "critic_delta": 0,
            "shared_movies": [], "mutual_favorites": [],
            "biggest_debates": [], "recommendations_for_you": [], "recommendations_for_friend": [],
            "genre_comparison": [], "library_overlap": 0, "rating_similarity": 0,
            "agreement_rate": 0, "harsher_critic": "Error"
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

def delete_user_tokens(user_id):
    try:
        client.table('tokens').delete().eq('user_id', user_id).execute()
    except Exception as e:
        logger.error(f"Error deleting user tokens: {e}")

#############################################
####### WATCHLISTS ##########################
#############################################

_PERSONAL_WATCHLIST_CACHE = {}

def get_or_create_personal_watchlist(user_id):
    if user_id in _PERSONAL_WATCHLIST_CACHE:
        return _PERSONAL_WATCHLIST_CACHE[user_id]
    try:
        data = client.table('watchlists').select('*').eq('user1_id', user_id).is_('user2_id', 'null').execute()
        if data.data:
            wl = data.data[0]
            _PERSONAL_WATCHLIST_CACHE[user_id] = wl
            return wl
        else:
            new_list = client.table('watchlists').insert({"user1_id": user_id}).execute()
            if new_list.data:
                wl = new_list.data[0]
                _PERSONAL_WATCHLIST_CACHE[user_id] = wl
                return wl
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