import os
import requests
from tmdbv3api import TMDb, Movie, TV, Season, Search

# Initialize TMDb
tmdb = TMDb()
tmdb.api_key = os.environ.get('TMDB_API_KEY')

movie_api = Movie()
tv_api = TV()
season_api = Season()
search_api = Search()

movie_genres = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Musical", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}

tv_genres = {
    10759: "Action & Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 10762: "Kids", 9648: "Mystery",
    10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
    10767: "Talk", 10768: "War & Politics", 37: "Western"
}

def get_movie_details(title, year, manual_director=None):
    """
    Search TMDB for a movie or TV show, extracting poster, genres, and director.
    Handles season title stripping (e.g. 'Reacher, Season 1' -> 'Reacher') and falls back to TV API.
    """
    import re
    clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
    if not clean_title:
        clean_title = title

    try:
        # 1. Check TV search if title matches known show patterns or media hints
        movie_res = movie_api.search(clean_title) or []
        tv_res = tv_api.search(clean_title) or []

        # Find exact title match in TV vs Movie
        norm_input = re.sub(r'[^a-z0-9]', '', clean_title.lower())
        
        best_match = None
        is_tv_result = False

        # Check for exact title match in TV first if title is short/known TV title
        for t_item in tv_res:
            t_name = re.sub(r'[^a-z0-9]', '', (t_item.get('name') or '').lower())
            if t_name == norm_input:
                best_match = t_item
                is_tv_result = True
                break

        # Check exact title match in Movies if not found in TV
        if not best_match:
            for m_item in movie_res:
                m_title = re.sub(r'[^a-z0-9]', '', (m_item.get('title') or '').lower())
                if m_title == norm_input:
                    best_match = m_item
                    is_tv_result = False
                    break

        # Fallback to year matching
        if not best_match:
            for m_item in movie_res:
                date_str = m_item.get('release_date') or ''
                if date_str and str(year) and date_str[:4] == str(year):
                    best_match = m_item
                    is_tv_result = False
                    break

        if not best_match:
            for t_item in tv_res:
                date_str = t_item.get('first_air_date') or ''
                if date_str and str(year) and date_str[:4] == str(year):
                    best_match = t_item
                    is_tv_result = True
                    break

        if not best_match:
            if movie_res:
                best_match = movie_res[0]
                is_tv_result = False
            elif tv_res:
                best_match = tv_res[0]
                is_tv_result = True

        if not best_match:
            return {
                "poster": f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(clean_title[:20])}",
                "genre": "Cinematic Pick",
                "director": manual_director or "Unknown",
                "title": title
            }
            
        poster_path = best_match.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(clean_title[:20])}"
        rating = best_match.get('vote_average')
        if rating is not None:
            try:
                rating = round(float(rating), 1)
            except (TypeError, ValueError):
                rating = None
        
        genre_ids = best_match.get('genre_ids', [])
        genre_map = tv_genres if is_tv_result else movie_genres
        genre_list = [genre_map.get(gid, "") for gid in genre_ids if genre_map.get(gid)]
        genre = ", ".join(genre_list) if genre_list else ("TV Series" if is_tv_result else "Feature Film")
        
        director = "Unknown"
        if manual_director:
            director = manual_director
        else:
            try:
                if not is_tv_result:
                    movie_details = movie_api.details(best_match['id'])
                    credits = movie_details.credits
                    if credits and 'crew' in credits:
                        for crew_member in credits['crew']:
                            if crew_member['job'] == 'Director':
                                director = crew_member['name']
                                break
                else:
                    created_by = best_match.get('created_by', [])
                    if created_by:
                        director = created_by[0].get('name', 'Unknown')
            except Exception:
                pass

        matched_name = best_match.get('name') if is_tv_result else best_match.get('title')
        return {
            "poster": poster,
            "genre": genre,
            "director": director if director != "Unknown" else (manual_director or "Unknown"),
            "title": matched_name or title,
            "rating": rating,
        }
    except Exception as e:
        print(f"Error in tmdb_service.get_movie_details: {e}")
        return {
            "poster": f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(title[:20])}",
            "genre": "Unknown",
            "director": manual_director or "Unknown",
            "title": title,
            "rating": None,
        }

def get_tv_details(title, year, season_num, manual_director=None):
    """
    Search TMDB for a TV show and extract poster, genres, and creator/director.
    """
    try:
        res = tv_api.search(title)
        if not res:
            return {
                "poster": "https://via.placeholder.com/200x300?text=No+Poster",
                "genre": "Unknown",
                "director": manual_director or "Unknown",
                "title": title
            }
        
        # Try to find exact year match
        best_match = None
        for result in res:
            first_air_date = result.get('first_air_date')
            if first_air_date and first_air_date[:4] == str(year):
                best_match = result
                break
        
        # Fallback to first result if no year match
        if not best_match:
            best_match = res[0]
            
        ids = best_match['id']
        
        # Get season details for poster
        try:
            show_season = season_api.details(ids, season_num or 1)
            poster_path = show_season.poster_path
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else f"https://image.tmdb.org/t/p/w500{best_match.get('poster_path') or ''}"
            full_title = f"{title}, {show_season.name}" if show_season.name else title
        except:
            poster_path = best_match.get('poster_path')
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://via.placeholder.com/200x300?text=No+Poster"
            full_title = title
            
        genre_ids = best_match.get('genre_ids', [])
        genre_list = [tv_genres.get(gid, "") for gid in genre_ids if tv_genres.get(gid)]
        genre = ", ".join(genre_list) if genre_list else "Unknown"
        
        director = "Unknown"
        if manual_director:
            director = manual_director
        else:
            try:
                tv_details = tv_api.details(ids)
                if hasattr(tv_details, 'created_by') and tv_details.created_by:
                    director = tv_details.created_by[0]['name']
                else:
                    # Try to get credits for TV show
                    try:
                        api_key = tmdb.api_key
                        credits_url = f"https://api.themoviedb.org/3/tv/{ids}/credits?api_key={api_key}"
                        credits_response = requests.get(credits_url)
                        if credits_response.status_code == 200:
                            credits_data = credits_response.json()
                            for crew_member in credits_data.get('crew', []):
                                if crew_member['job'] in ['Director', 'Creator', 'Executive Producer']:
                                    director = crew_member['name']
                                    break
                    except:
                        pass
                    
                    if not director or director == "Unknown":
                        director = "Various Directors"
            except:
                director = "Unknown"
                
        return {
            "poster": poster,
            "genre": genre,
            "director": director,
            "title": full_title
        }
    except Exception as e:
        print(f"Error in tmdb_service.get_tv_details: {e}")
        return {
            "poster": "https://via.placeholder.com/200x300?text=Error",
            "genre": "Unknown",
            "director": manual_director or "Unknown",
            "title": title
        }

def search_titles(query, is_tv=False):
    """
    Quick search for autocomplete suggestions.
    Returns a list of dicts with title, year, poster, and type.
    """
    try:
        res = search_api.multi({"query": query})
        results = []
        for item in res:
            media_type = item.get('media_type')
            
            # Skip if it's a person or if is_tv is strictly requested and this is a movie (or vice versa if we wanted to enforce it)
            # Actually, the user wants to search both regardless, but maybe we prioritize what they selected, 
            # or just show everything and let them pick. We will show everything.
            if media_type not in ['movie', 'tv']:
                continue

            if media_type == 'tv':
                date = item.get('first_air_date', '')
                year = date[:4] if date else ''
                title = item.get('name', '')
            else:
                date = item.get('release_date', '')
                year = date[:4] if date else ''
                title = item.get('title', '')
                
            poster_path = item.get('poster_path')
            poster = f"https://image.tmdb.org/t/p/w92{poster_path}" if poster_path else "https://via.placeholder.com/92x138?text=No+Poster"
            
            results.append({
                "id": item.get('id'),
                "title": title, 
                "year": year, 
                "poster": poster,
                "type": media_type
            })
            
            if len(results) >= 5:
                break
                
        return results
    except Exception as e:
        print(f"Error in tmdb_service.search_titles: {e}")
        return []

def get_director_by_id(media_id, media_type):
    """
    Fetch the director or creator for a specific media ID.
    """
    try:
        api_key = tmdb.api_key
        if media_type == 'tv':
            # Check created_by first for TV shows
            tv_details = tv_api.details(media_id)
            if hasattr(tv_details, 'created_by') and tv_details.created_by:
                return tv_details.created_by[0]['name']
                
            credits_url = f"https://api.themoviedb.org/3/tv/{media_id}/credits?api_key={api_key}"
            credits_response = requests.get(credits_url)
            if credits_response.status_code == 200:
                for crew in credits_response.json().get('crew', []):
                    if crew['job'] in ['Director', 'Creator', 'Executive Producer']:
                        return crew['name']
        else:
            credits_url = f"https://api.themoviedb.org/3/movie/{media_id}/credits?api_key={api_key}"
            credits_response = requests.get(credits_url)
            if credits_response.status_code == 200:
                for crew in credits_response.json().get('crew', []):
                    if crew['job'] == 'Director':
                        return crew['name']
    except Exception as e:
        print(f"Error in tmdb_service.get_director_by_id: {e}")
        
    return ""
