from flask import Flask, render_template, jsonify, request, flash, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import *
import os
import datetime
import requests
from bs4 import BeautifulSoup
from tmdbv3api import TMDb, Movie, TV, Season
from flask_mail import Mail, Message
import secrets

tmdb = TMDb()
tmdb.api_key = os.environ.get('TMDB_API_KEY')

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'kinetowebapp@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('KINETO_MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)

year_now = datetime.date.today().year
month_now = datetime.date.today().month
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
dict_months = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}

def get_movie_poster(movie_title):
    # Replace spaces with underscores
    movie_title = movie_title.replace(' ', '_')
    # Construct URL
    url = f'https://en.wikipedia.org/wiki/{movie_title}'
    # Send GET request
    response = requests.get(url)
    # Parse HTML content
    soup = BeautifulSoup(response.content, 'html.parser')
    # Find poster image
    img_tag = soup.find('a', {'class': 'image'})
    # Return image URL
    return str(img_tag)

movie = Movie()
tv = TV()

########################### Login - Logout - Register 
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']
        try:
            users = load_users_from_email(email)
        except:
            users = []
            flash('Something went wrong, please try again', category='error')
        if users != []:
            if users[0]['email'] == email and check_password_hash(users[0]['password'], password) == True:
                session['loggedin'] = True
                session['id'] = users[0]['id']
                session['email'] = users[0]['email']
                flash ('Logged in successfully!', category='success')
                return redirect('/home')
            # If account exists in accounts table in out database
            else:
            # Account doesnt exist or username/password incorrect
                flash ('Incorrect username/password!', category='error')
        else:
            flash ('Something went wrong, please try again', category='error')
    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("login.html", session=session)

@app.route('/register', methods=['GET', 'POST'])
def register():
        """Register user"""
        if request.method == "POST":
            # Require username
            email = request.form.get("email")
            name = request.form.get("username")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")

            # Check if email already exists
            users = load_users_from_email(email)
            usernames = load_users_from_username(name)
            if users:
                flash('Email already exists', category='error')
            elif not email or len(email) < 4:
                flash('Email must be valid', category='error')
            if usernames:
                flash('Username already taken', category='error')
            elif len(name) < 2 :
                flash('Username must be greater than 1 character', category='error')
            # Check and validate passwords
            elif not password:
                flash("Must provide password", category='error')
            elif len(password) < 3:
                flash("Password must be greater than 3 characters", category='error')
            elif password != confirm_password:
                flash("Passwords must match", category='error')
            else:
            # Create hash of password to insert into the database
                hash = generate_password_hash(request.form.get("password"), method='sha256')
                insert_user(name, email, password=hash)
                flash('Account created', category='success')
                return redirect("/home")
        return render_template('register.html')
    
@app.route('/logout')
def logout():
    # Remove session data, this will log the user out
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('email', None)
    # Redirect to login page
    return redirect('/login')

########################################### Main pages ################

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
def lista():
    if 'loggedin' in session:
        try:
            movies = get_movies(session['id'])
            # sort movies in descendig order by v_date
            movies.sort(key=lambda movie: movie["v_date"], reverse=True)
        except Exception as e:
            print(f"Error{e}")
            movies = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
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
def show_directors():
    if 'loggedin' in session:
        try:
            movies = get_movies_groupby_director(session['id'])
            directors = get_directors(session['id'])
        except:
            movies = []
            directors = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
    return render_template('directors.html', movies=movies, directors=directors)

@app.route('/directors/<username>', methods=['GET'])
def show_directors_friends(username):
    if 'loggedin' in session:
        try:
            id = get_user_id(username)
            id = id[0]['id']
            movies = get_movies_groupby_director(id)
            directors = get_directors(id)
        except:
            movies = []
            directors = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
    return render_template('_directors.html', movies=movies, directors=directors)

@app.route('/genres', methods=['GET'])
def show_genres():
    if 'loggedin' in session:
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
    else:
        return redirect('/login')
    return render_template('genres.html', movies=movies, genres=final_genres)

@app.route('/genres/<username>', methods=['GET'])
def show_genres_friends(username):
    if 'loggedin' in session:
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
    else:
        return redirect('/login')
    return render_template('_genres.html', movies=movies, genres=final_genres)


@app.route('/years', methods=['GET'])
def show_years():
    if 'loggedin' in session:
        try:
            movies = get_movies_groupby_year(session['id'])
            anni = get_years(session['id'])
        except:
            movies = []
            anni = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
    return render_template('years.html', movies=movies, years=anni)

@app.route('/years/<username>', methods=['GET'])
def show_years_friends(username):
    if 'loggedin' in session:
        try:
            id = get_user_id(username)
            id = id[0]['id']
            movies = get_movies_groupby_year(id)
            anni = get_years(id)
        except:
            movies = []
            anni = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
    return render_template('_years.html', movies=movies, years=anni)

@app.route('/ratings', methods=['GET'])
def show_ratings():
    if 'loggedin' in session:
        try:
            movies = get_movies_groupby_year(session['id'])
            ratings = get_ratings(session['id'])
        except:
            movies = []
            ratings = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
    return render_template('ratings.html', movies=movies, ratings=ratings)

@app.route('/ratings/<username>', methods=['GET'])
def show_ratings_friends(username):
    if 'loggedin' in session:
        try:
            id = get_user_id(username)
            id = id[0]['id']
            movies = get_movies_groupby_year(id)
            ratings = get_ratings(id)
        except:
            movies = []
            ratings = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return redirect('/login')
    return render_template('_ratings.html', movies=movies, ratings=ratings)

@app.route("/users/<name>")
def show_user_profile(name):
    user = load_users_from_username(name)
    return jsonify(user)

@app.route('/data')
def list_about():
    if 'loggedin' in session:
        users = get_user_by_id(session['id'])
        movies = get_movies(session['id'])
    return jsonify(movies)

@app.route('/data/<username>')
def list_about_friend(username):
    if 'loggedin' in session:
        users = get_user_id(username)
        movies = get_movies(users[0]['id'])
    return jsonify(movies)

@app.route('/profile')
def profile():
    if 'loggedin' in session:
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
    return redirect('/login')

@app.route('/profile/<username>')
def profile_friend(username):
    if 'loggedin' in session:
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
    return redirect('/login')

@app.route('/friends', methods=['GET', 'POST'])
def search_friends():
    if 'loggedin' in session:
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
    return redirect('/login')

@app.route('/follow', methods=['GET', 'POST'])
def follow():
    if request.method == "POST":
        if 'loggedin' in session:
            friend_id = request.form['user_id']
            friend_username = request.form['username']
            insert_friends(friend_id, friend_username, session['id'])
            return redirect('/friends')
        else:
            return redirect('/login')
    return redirect('/friends')


@app.route('/discover')
def discover():
    if 'loggedin' in session:   
        movies = get_highest_rating()                 
        return render_template('explore.html', movies=movies, session=session)
    return redirect('/login')

####################### Add / edit / remove movies ################################
movie_genres = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Musical",
    9648: "Mystery",
    10749: "Romance",
    878: "Sci-Fi",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western"
}

tv_genres = {
    10759: "Action & Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    10762: "Kids",
    9648: "Mystery",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
    37: "Western"
}


def clean_and_format(word):
    word = word.strip()
    word = " ".join(word.split())
    word = word.lower()
    return word

def clean_and_capitalize_name(name):
    # Remove leading and trailing spaces and convert to lowercase
    cleaned_name = name.strip().lower()
    
    # Capitalize the first letter of each word
    capitalized_name = ' '.join(word.capitalize() for word in cleaned_name.split())
    
    return capitalized_name

@app.route('/add_movie', methods=['GET', 'POST'])
def add_movie():
    season = Season()
    if 'loggedin' not in session:
        return redirect('/login')
    else:
        if request.method == "POST":
            try:
                if 'loggedin' in session:
                    parent_id = get_user_by_id(session['id'])
                    title = request.form["title"]
                    title = clean_and_format(title)
                    director = request.form["director"]
                    director = clean_and_capitalize_name(director)
                    year = request.form["year"]
                    date = request.form["date"]
                    genre = ""
                    rating = request.form["rating"]
                    rewatch = request.form["rewatch"] # 0 false, 1 true
                    tv_show = request.form["tv"] # 0 if movie, 1 if tv show
                    which_season = request.form["season"]
                    cinema = request.form["cinema"]
                    try:
                        if tv_show == '1':
                            res = tv.search(title)
                            for i, result in enumerate(res):
                                print(f"Result_{i}", result)
                                if result['first_air_date'][:4] == str(year):
                                    #print(result['first_air_date'][:4])
                                    ids = result['id']
                                    show_season = season.details(ids, which_season)
                                    poster = "https://image.tmdb.org/t/p/w200" + show_season.poster_path
                                    title = title + ', ' + show_season.name
                                    genre_ids = show_season.genre_ids
                                    genre = genre.join([tv_genres[genre_id] + ", " for genre_id in genre_ids])
                                    genre = genre[:-2]
                                    break
                        else:
                            res = movie.search(title)
                            for i, result in enumerate(res):
                                print(f"Result_{i}", result)
                                if result['release_date'][:4] == str(year):
                                    #print(result['release_date'][:4])
                                    poster = "https://image.tmdb.org/t/p/w200/" + result['poster_path']
                                    genre_ids = result['genre_ids']
                                    genre = genre.join([movie_genres[genre_id] + ", " for genre_id in genre_ids])
                                    genre = genre[:-2]
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
                    flash('Movie added', category='success')
                else:
                    flash('You need to be logged in to add a movie', category='error')
            except:
                redirect('/add_movie')
                flash('Something went wrong, please try again', category='error')
                
    return render_template('add_movie.html')

@app.route('/remove_movie', methods=['GET', 'POST'])
def remove_movie():
    if 'loggedin' in session:
        if request.method == "POST":
            movie_id = request.form['movie_id']
            remove_movie_by_id(movie_id)
            flash('Movie removed', category='success')
            return redirect('/home')
    return redirect('/login')

@app.route('/edit_movie', methods=['GET', 'POST'])
def edit_movie():
    if 'loggedin' in session:
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
            flash('Movie updated', category='success')
            return redirect('/home')
    return redirect('/login')
   
    
########################### Restore password #########################################
def generate_token():
        return secrets.token_hex(16)

def is_expired(creation_date):
        return datetime.datetime.now() > (creation_date + datetime.timedelta(hours=24))

@app.route('/passwordreset', methods=['GET', 'POST'])
def request_password_reset():
    if request.method == 'POST':
        email = request.form['email']
        if not email:
            return jsonify({'error': 'Email is required'}), 400

        user = get_user_by_email(email)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        print(user)

        # Generate a new reset token
        token = generate_token()
        now = datetime.datetime.now()
        now =  now.strftime("%Y-%m-%d %H:%M:%S") 
        insert_token(user['id'], token, now)
        
        # Send an email to the user with the reset link
        reset_url = f"https://lista-film-v2.onrender.com/passwordreset/{token}"
        msg = Message('Reset Your Password', sender='kinetowebapp@gmail.com', recipients=[user['email']])
        msg.body = f"Click this link to reset your password: {reset_url}"
        mail.send(msg)
        return jsonify({'message': 'Password reset email sent, if you do not find it check your spam folder'})
    return render_template('passwordreset.html')

@app.route('/passwordreset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        password = request.form['password']
        hash = generate_password_hash(password, method='sha256')
        if not password:
            return jsonify({'error': 'Password is required'}), 400
    
        # Find the reset token
        reset_token = get_token(token)
        if not reset_token:
            return jsonify({'error': 'Invalid token'}), 404
        if is_expired(reset_token.created_at):
            return jsonify({'error': 'Token has expired'}), 400
    
        # Update the user's password
        user_id = reset_token.user_id
        update_user_password(user_id, hash)
        delete_token(token)
    
        return jsonify({'message': 'Password reset successful'})
    return render_template('reset2.html')

################################################################################################
if __name__ == '__main__':
    app.run(debug=True)
    
    
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