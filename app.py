from flask import Flask, render_template, jsonify, request, flash, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import *
import os
import datetime
import requests
import re
from functools import wraps
from bs4 import BeautifulSoup
from tmdbv3api import TMDb, Movie, TV, Season
from flask_mail import Mail, Message
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from auth.auth import auth # Import the auth blueprint
from auth.restore import restore # Import the restore blueprint
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# Load environment variables from .env file
load_dotenv()

# ========================================
# APP CONFIGURATION
# ========================================

tmdb = TMDb()
tmdb.api_key = os.environ.get('TMDB_API_KEY')

app = Flask(__name__)
# Register the auth blueprint with the main app
app.register_blueprint(auth)

app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# Enable CSRF protection for all forms
csrf = CSRFProtect(app)

# Rate limiting to prevent brute-force attacks
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["1000 per day", "50 per hour"],
    storage_uri="memory://"
)

# ========================================
# LOGIN REQUIRED DECORATOR
# ========================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session:
            flash('Please log in to access this page', category='error')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587  # Changed from 465 to 587 for better compatibility
app.config['MAIL_USERNAME'] = 'kinetowebapp@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('KINETO_MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True  # Changed to TLS instead of SSL
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEFAULT_SENDER'] = 'kinetowebapp@gmail.com'
app.config['MAIL_MAX_EMAILS'] = None
app.config['MAIL_ASCII_ATTACHMENTS'] = False
app.config['MAIL_TIMEOUT'] = 30  # 30 second timeout

# Verify mail configuration
if not os.environ.get('KINETO_MAIL_PASSWORD'):
    print("WARNING: KINETO_MAIL_PASSWORD environment variable not set!")
else:
    print("Mail configuration loaded successfully")
    print(f"SMTP Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
    print(f"SMTP User: {app.config['MAIL_USERNAME']}")
    print(f"TLS: {app.config['MAIL_USE_TLS']}, SSL: {app.config['MAIL_USE_SSL']}")

mail = Mail(app)
app.register_blueprint(restore)

# Test SMTP connection on startup (optional, only in debug mode)
if os.environ.get('TEST_SMTP_ON_STARTUP') == '1':
    try:
        with mail.connect() as conn:
            print("✓ SMTP connection test successful!")
    except Exception as e:
        print(f"✗ SMTP connection test failed: {str(e)}")
        import traceback
        traceback.print_exc()

# ========================================
# CACHING CONFIGURATION
# ========================================

# Configure Flask-Caching
app.config['CACHE_TYPE'] = 'SimpleCache'  # Use 'RedisCache' for production with Redis
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes default

cache = Cache(app)

def make_user_cache_key():
    """Create a cache key based on the current user's session ID"""
    user_id = session.get('id', 'anonymous')
    return f"user_{user_id}_{request.path}"

def clear_user_cache(user_id):
    """Clear all cached data for a specific user (call after add/edit/remove movie)"""
    # With SimpleCache, we clear everything. For Redis, you could be more selective
    cache.clear()

# ========================================
# GLOBAL VARIABLES & CONSTANTS
# ========================================

year_now = datetime.date.today().year
month_now = datetime.date.today().month
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
dict_months = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}

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

movie = Movie()
tv = TV()
season = Season()

# ========================================
# UTILITY FUNCTIONS
# ========================================

def clean_and_format(word):
    """Clean and format movie titles"""
    word = word.strip()
    word = " ".join(word.split())
    word = word.lower()
    return word

def clean_and_capitalize_name(name):
    """Clean and capitalize names (directors, etc.)"""
    cleaned_name = name.strip().lower()
    capitalized_name = ' '.join(word.capitalize() for word in cleaned_name.split())
    return capitalized_name

def get_movie_poster(movie_title):
    """Get movie poster from Wikipedia (fallback method)"""
    movie_title = movie_title.replace(' ', '_')
    url = f'https://en.wikipedia.org/wiki/{movie_title}'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    img_tag = soup.find('a', {'class': 'image'})
    return str(img_tag)

def get_user_watch_history_summary(user_id, percentage=50, max_cap=100):
    """Get a formatted summary of user's recent watch history for AI analysis"""
    try:
        movies = get_movies(user_id)
        if not movies:
            return "No movies watched yet."
        
        # Sort by watch date and get recent ones
        movies.sort(key=lambda x: x['v_date'], reverse=True)
        
        # Calculate how many movies to include based on percentage
        total_movies = len(movies)
        movies_to_include = min(int(total_movies * percentage / 100), max_cap)
        movies_to_include = max(movies_to_include, 1)  # At least 1 movie
        
        recent_movies = movies[:movies_to_include]
        
        # Create a formatted summary
        summary = f"Recent movies I've watched ({movies_to_include} out of {total_movies} total movies, {percentage}% of my collection):\n"
        for i, movie in enumerate(recent_movies, 1):
            rating_text = f"({movie['rating']}/10)" if movie['rating'] else "(unrated)"
            summary += f"{i}. {movie['movie']} ({movie['p_year']}) - Director: {movie['director']} - Genre: {movie['genre']} - My Rating: {rating_text}\n"
        
        # Add some statistics
        if len(movies) > 0:
            avg_rating = sum(m['rating'] for m in movies if m['rating']) / len([m for m in movies if m['rating']])
            genres = {}
            for movie in recent_movies:
                if movie['genre']:
                    for genre in movie['genre'].split(', '):
                        genres[genre.strip()] = genres.get(genre.strip(), 0) + 1
            
            top_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:3]
            summary += f"\nMy average rating: {avg_rating:.1f}/10\n"
            summary += f"My most watched genres in this selection: {', '.join([g[0] for g in top_genres])}\n"
        
        return summary
    except Exception as e:
        print(f"Error getting watch history: {e}")
        return "Unable to retrieve watch history."

def get_ai_movie_recommendation(user_request, user_history):
    """Get AI-powered movie recommendations using Hugging Face InferenceClient"""
    try:
        client = InferenceClient(
            provider="together",
            api_key=os.environ.get('HUGGINGFACE_API_KEY')
        )
        
        # Create a comprehensive prompt for movie recommendations
        prompt = f"""You are a movie recommendation expert. Based on the user's watch history and their request, provide 3-5 specific movie recommendations.

User's Recent Watch History:
{user_history}

User's Request: {user_request}

Please provide movie recommendations in the following format:
1. **Movie Title (Year) - Director**
   Genre: [genres]
   Why I recommend it: [brief explanation based on their history and request]

2. **Movie Title (Year) - Director**
   Genre: [genres]
   Why I recommend it: [brief explanation based on their history and request]

[Continue for 3-5 movies]

Keep recommendations diverse and consider the user's rating patterns and favorite genres. Explain why each movie fits their taste based on their watch history."""

        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        completion = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3", 
            messages=messages, 
            max_tokens=1000
        )
        
        response_text = completion.choices[0].message.content
        
        # Convert markdown-style formatting to HTML for better display
        formatted_response = format_ai_response_to_html(response_text)
        
        return formatted_response
        
    except Exception as e:
        print(f"Error getting AI recommendations: {e}")
        return f"<p>Sorry, I couldn't generate recommendations at the moment.</p><p><strong>Error:</strong> {str(e)}</p>"

def format_ai_response_to_html(text):
    """Convert AI response text to HTML with better formatting"""
    
    # Split the text into lines for processing
    lines = text.split('\n')
    html_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        
        # Check for numbered list items
        if re.match(r'^\d+\.\s*\*\*(.*?)\*\*', line):
            if not in_list:
                html_lines.append('<ol>')
                in_list = True
            # Extract the movie title
            title_match = re.match(r'^\d+\.\s*\*\*(.*?)\*\*', line)
            if title_match:
                html_lines.append(f'<li><strong>{title_match.group(1)}</strong>')
        elif line.startswith('Genre:') or line.startswith('Why I recommend it:'):
            # Handle metadata lines
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            html_lines.append(f'<p>{line}</p>')
        elif line and not re.match(r'^\d+\.', line):
            # Handle regular text lines
            if in_list:
                html_lines.append('</li>')
                # Don't close the list yet, there might be more items
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            if line:
                html_lines.append(f'<p>{line}</p>')
        elif not line:
            # Empty line - close list item if we're in a list
            if in_list:
                html_lines.append('</li>')
    
    # Close any open list at the end
    if in_list:
        html_lines.append('</li>')
        html_lines.append('</ol>')
    
    return '\n'.join(html_lines)

# ========================================
# MAIN NAVIGATION ROUTES
# ========================================

@app.route('/home')
def hello():
    if 'loggedin' in session:
        try:
            movies = get_monthly_movies(session['id'], month_now)
        except:
            movies = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return render_template('home.html', movies=[])
    return render_template('home.html', session=session, movies=movies)

@app.route('/')
def animation():
    return render_template('animation.html', session=session)

@app.route('/lista')
@login_required
@cache.cached(timeout=120, key_prefix=make_user_cache_key)
def lista():
    try:
        movies = get_movies(session['id'])
        # sort movies in descendig order by v_date
        movies.sort(key=lambda movie: movie["v_date"], reverse=True)
    except Exception as e:
        print(f"Error{e}")
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('lista1.html', movies=movies, months=months, year_now=year_now, dict_months=dict_months)

@app.route('/list/<username>')
def lista_user(username):
    user = get_user_id(username)
    print(user)
    id = user[0]['id']
    print(id)
    try:
        movies = get_movies(id)
        movies.sort(key=lambda movie: movie["v_date"], reverse=True)
    except Exception as e:
        print(f"Error{e}")
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_lista1.html', movies=movies, months=months, year_now=year_now, dict_months=dict_months, username=username)


@app.route('/directors', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_directors():
    try:
        movies = get_movies_groupby_director(session['id'])
        directors = get_directors(session['id'])
    except:
        movies = []
        directors = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('directors.html', movies=movies, directors=directors)

@app.route('/directors/<username>', methods=['GET'])
@login_required
def show_directors_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_director(id)
        directors = get_directors(id)
    except:
        movies = []
        directors = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_directors.html', movies=movies, directors=directors)

@app.route('/genres', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_genres():
    try:
        movies = get_movies_groupby_genre(session['id'])
        in_genres = ""
        generi = get_genres(session['id'])
        for genre in generi:
            in_genres += genre['name'] + ', '
        mid_genres = in_genres.split(', ')
        final_genres = set([genre for genre in mid_genres if genre != ''])
        print(final_genres)
    except:
        movies = []
        generi = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('genres.html', movies=movies, genres=final_genres)

@app.route('/genres/<username>', methods=['GET'])
@login_required
def show_genres_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_genre(id)
        in_genres = ""
        generi = get_genres(id)
        for genre in generi:
            in_genres += genre['name'] + ', '
        mid_genres = in_genres.split(', ')
        final_genres = set([genre for genre in mid_genres if genre != ''])
        print(final_genres)
    except:
        movies = []
        generi = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_genres.html', movies=movies, genres=final_genres)


@app.route('/years', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_years():
    try:
        movies = get_movies_groupby_year(session['id'])
        anni = get_years(session['id'])
    except:
        movies = []
        anni = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('years.html', movies=movies, years=anni)

@app.route('/years/<username>', methods=['GET'])
@login_required
def show_years_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_year(id)
        anni = get_years(id)
    except:
        movies = []
        anni = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_years.html', movies=movies, years=anni)

# ========================================
# STATISTICS & ANALYTICS ROUTES
# ========================================

@app.route('/ratings', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_ratings():
    try:
        movies = get_movies_groupby_year(session['id'])
        ratings = get_ratings(session['id'])
    except:
        movies = []
        ratings = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('ratings.html', movies=movies, ratings=ratings)

@app.route('/ratings/<username>', methods=['GET'])
@login_required
def show_ratings_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_year(id)
        ratings = get_ratings(id)
    except:
        movies = []
        ratings = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_ratings.html', movies=movies, ratings=ratings)

# ========================================
# USER PROFILE & DATA ROUTES
# ========================================

@app.route("/users/<name>")
def show_user_profile(name):
    user = load_users_from_username(name)
    return jsonify(user)

@app.route('/data')
@login_required
def list_about():
    users = get_user_by_id(session['id'])
    movies = get_movies(session['id'])
    return jsonify(movies)

@app.route('/data/<username>')
@login_required
def list_about_friend(username):
    users = get_user_id(username)
    movies = get_movies(users[0]['id'])
    return jsonify(movies)

@app.route('/profile')
@login_required
def profile():
    users = get_user_by_id(session['id'])
    try:
        movies = get_movies(session['id'])
        length = len(movies)
        lenght_month = len(get_monthly_movies(session['id'], month_now))
        rating = 0
        genres = {}
        for movie in movies:
            rating += movie['rating']
            genres[movie['genre']] = genres.get(movie['genre'], 0) + 1
            if movie['rating'] > 5:
                premium = (movie['rating'] - 5)/2
                genres[movie['genre']] += premium
        print(genres)
        favorite_genre = max(genres, key=genres.get)
        
        if length == 0:
            avg_rating = 0
            favorite_genre = 'No movies added'
        else:
            avg_rating = round(rating/length, 2)
    except:
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('profile.html', user=users[0], movies=movies, length = length, lmonth=lenght_month, avg_rating=avg_rating, favorite_genre=favorite_genre)

@app.route('/profile/<username>')
@login_required
def profile_friend(username):
    users = get_user_id(username)
    try:
        movies = get_movies(users[0]['id'])
        length = len(movies)
        lenght_month = len(get_monthly_movies(users[0]['id'], month_now))
        rating = 0
        genres = {}
        for movie in movies:
            rating += movie['rating']
            genres[movie['genre']] = genres.get(movie['genre'], 0) + 1
            favorite_genre = max(genres, key=genres.get)
        if length == 0:
            avg_rating = 0
            favorite_genre = 'No movies added'
        else:
            avg_rating = round(rating/length, 2)
    except:
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_profile.html', username= username, user=users[0], movies=movies, length = length, lmonth=lenght_month, avg_rating=avg_rating, favorite_genre=favorite_genre)

# ========================================
# SOCIAL FEATURES (FRIENDS & DISCOVERY)
# ========================================

@app.route('/friends', methods=['GET', 'POST'])
@login_required
def search_friends():
    friends = get_friends(session['id'])
    if request.method == "POST":
        name = request.form['name']
        users = get_user_name(name)
        if users == []:
            flash('No user found', category='error')
        else:
            return render_template('friends.html', users=users, friends=friends, session=session) 
    liked = []   
    for friend in friends:
        movies = get_movies(friend['user_id'])
        for movie in movies:
            if movie['rating'] >= 8 and datetime.date.today() - movie['v_date'] < datetime.timedelta(days=30):
                liked.append(movie)                  
    return render_template('friends.html', friends=friends, liked=liked, session=session)

@app.route('/follow', methods=['GET', 'POST'])
@login_required
def follow():
    if request.method == "POST":
        friend_id = request.form['user_id']
        friend_username = request.form['username']
        insert_friends(friend_id, friend_username, session['id'])
        return redirect('/friends')
    return redirect('/friends')


@app.route('/discover', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")  # Rate limit AI recommendations
def discover():
    ai_response = None
    user_request = ""
    history_percentage = 50
    
    if request.method == 'POST':
        user_request = request.form.get('user_request', '').strip()
        history_percentage = int(request.form.get('history_percentage', 50))
        
        if user_request:
            # Get user's watch history with the specified percentage
            user_history = get_user_watch_history_summary(session['id'], percentage=history_percentage)
            
            # Get AI recommendations
            ai_response = get_ai_movie_recommendation(user_request, user_history)
        else:
            flash('Please enter a request for movie recommendations', 'error')
    
    return render_template('discover.html', 
                         ai_response=ai_response, 
                         user_request=user_request,
                         history_percentage=history_percentage,
                         session=session)

# ========================================
# MOVIE MANAGEMENT (ADD/EDIT/REMOVE)
# ========================================

@app.route('/add_movie', methods=['GET', 'POST'])
@login_required
@limiter.limit("100 per hour")  # Rate limit movie additions
def add_movie():
    if request.method == "POST":
        try:
            parent_id = get_user_by_id(session['id'])
            title = request.form["title"]
            title = clean_and_format(title)
            manual_director = request.form["director"].strip()
            year = request.form["year"]
            date = request.form["date"]
            genre = ""
            director = ""
            rating = request.form["rating"]
            rewatch = request.form["rewatch"] # 0 false, 1 true
            tv_show = request.form["tv"] # 0 if movie, 1 if tv show
            which_season = request.form["season"]
            cinema = request.form["cinema"]
            
            # Use manual director if provided, otherwise auto-fetch
            if manual_director:
                director = clean_and_capitalize_name(manual_director)
            
            try:
                if tv_show == '1':
                    res = tv.search(title)
                    for i, result in enumerate(res):
                        print(f"Result_{i}", result)
                        if result['first_air_date'][:4] == str(year):
                            ids = result['id']
                            show_season = season.details(ids, which_season)
                            poster = "https://image.tmdb.org/t/p/w200" + show_season.poster_path
                            title = title + ', ' + show_season.name
                            genre_ids = result['genre_ids']
                            genre = genre.join([tv_genres[genre_id] + ", " for genre_id in genre_ids])
                            genre = genre[:-2]
                            
                            # Get TV show creator/director only if not manually provided
                            if not director:
                                try:
                                    tv_details = tv.details(ids)
                                    print(tv_details)
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
                                        
                                        if not director:
                                            director = "Various Directors"
                                except:
                                    director = "Unknown"
                            print(genre)
                            break
                else:
                    res = movie.search(title)
                    for i, result in enumerate(res):
                        print(f"Result_{i}", result)
                        if result['release_date'][:4] == str(year):
                            poster = "https://image.tmdb.org/t/p/w200/" + result['poster_path']
                            genre_ids = result['genre_ids']
                            genre = genre.join([movie_genres[genre_id] + ", " for genre_id in genre_ids])
                            genre = genre[:-2]
                            
                            # Get movie director only if not manually provided
                            if not director:
                                try:
                                    movie_details = movie.details(result['id'])
                                    # Try to get credits using the tmdbv3api
                                    credits = movie_details.credits
                                    if credits and 'crew' in credits:
                                        for crew_member in credits['crew']:
                                            if crew_member['job'] == 'Director':
                                                director = crew_member['name']
                                                break
                                except:
                                    # Fallback: try manual API call for credits
                                    try:
                                        api_key = tmdb.api_key
                                        credits_url = f"https://api.themoviedb.org/3/movie/{result['id']}/credits?api_key={api_key}"
                                        credits_response = requests.get(credits_url)
                                        if credits_response.status_code == 200:
                                            credits_data = credits_response.json()
                                            for crew_member in credits_data.get('crew', []):
                                                if crew_member['job'] == 'Director':
                                                    director = crew_member['name']
                                                    break
                                    except:
                                        pass

                                if not director:
                                    director = "Unknown"
                            break
            except:
                html = get_movie_poster(title)
                if html != 'None':
                    soup = BeautifulSoup(html, 'html.parser')
                    img_tag = soup.find('img')
                    src_link = img_tag['src']   
                    poster = src_link
                else: 
                    res = movie.search(title)
                    poster = res[0]['poster_path']
            
            print(title, director, year, date, genre, rating, rewatch, tv_show, session['id'])
            insert_movies(title, director, genre, year, date, rating, rewatch, tv_show, poster, session['id'], cinema)
            clear_user_cache(session['id'])  # Clear cache after adding movie
            flash('Movie added', category='success')
        except Exception as e:
            print(f"Error adding movie: {e}")
            flash('Something went wrong, please try again', category='error')
            return redirect('/add_movie')
                
    return render_template('add_movie.html')

@app.route('/remove_movie', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per hour")  # Rate limit movie removals
def remove_movie():
    if request.method == "POST":
        movie_id = request.form['movie_id']
        remove_movie_by_id(movie_id)
        clear_user_cache(session['id'])  # Clear cache after removing movie
        flash('Movie removed', category='success')
        return redirect('/home')
    return redirect('/home')

@app.route('/edit_movie', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per hour")  # Rate limit movie edits
def edit_movie():
    if request.method == "GET":
        return render_template('edit_movie.html')
    else:
        movie_id = request.form['movie_id']
        title = request.form['movie']
        director = request.form['director']
        p_year = request.form['year']
        rating = request.form['rating']
        tv_show = request.form['tv']
        try:
            if tv_show == '1':
                res = tv.search(title)
            else:
                res = movie.search(title)
            poster = "https://image.tmdb.org/t/p/w200/" + res[0]['poster_path']
        except:
            html = get_movie_poster(title)
            if html != 'None':
                soup = BeautifulSoup(html, 'html.parser')
                img_tag = soup.find('img')
                src_link = img_tag['src']   
                poster = src_link
            else: 
                res = movie.search(title)
                poster = res[0]['poster_path']
        update_movie(movie_id, title, director, p_year, rating, poster)
        clear_user_cache(session['id'])  # Clear cache after updating movie
        flash('Movie updated', category='success')
        return redirect('/home')

# ========================================
# APPLICATION ENTRY POINT
# ========================================

if __name__ == '__main__':
    # Use environment variable to control debug mode
    # Set FLASK_DEBUG=1 for development, omit or set to 0 for production
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)
    
    
#@app.route('/lista_<year_selected>')
#def lista_year(year_selected):
#    if 'loggedin' in session:
#        try:
#            movies = get_movies(session['id'])
#        except:
#            movies = []
#            flash('Something went wrong, please refresh the page', category='error')
#    else:
#        return redirect('/login')
#    return render_template('lista_year.html', year=int(year_selected), movies=movies, months=months, dict_months=dict_months)