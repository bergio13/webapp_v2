import os
import supabase
from datetime import datetime
from dotenv import load_dotenv
import math

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASEURL")
SUPABASE_KEY = os.environ.get("SUPABASEKEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing Supabase configuration: set SUPABASEURL and SUPABASEKEY.")

client = supabase.create_client(SUPABASE_URL, SUPABASE_KEY)

def load_users_from_db():
    # Fetch data from Supabase table
    data = client.table('users').select('*').execute()
    user_dicts = []
    for row in data.data:
        user_dict = {
            "id": row['id'],
            "username": row['username'],
            "email": row['email']
        }
        user_dicts.append(user_dict)
    return user_dicts

def load_users_from_username(name):
    # Fetch data from Supabase table
    data = client.table('users').select('*').eq("username", name).execute()
    user_dicts = []
    for row in data.data:
        user_dict = {
            "id": row['id'],
            "username": row['username'],
            "email": row['email']
        }
        user_dicts.append(user_dict)
    return user_dicts

def load_users_from_email(email):
    # Fetch data from Supabase table
    data = client.table('users').select('*').eq("email", email).execute()
    user_dicts = []
    for row in data.data:
        user_dict = {
            "id": row['id'],
            "username": row['username'],
            "email": row['email'],
            "password": row['password']
        }
        user_dicts.append(user_dict)
    return user_dicts


def insert_user(username, email, password):
    # Insert data into Supabase table
    client.table('users').insert([{"username": username, "email": email, "password": password}]).execute()
    

def get_user_by_id(id):
    # Fetch data from Supabase table
    data = client.table('users').select('*').eq("id", id).execute()
    user_dicts = []
    for row in data.data:
        user_dict = {
            "id": row['id'],
            "username": row['username'],
            "email": row['email'],
            "password": row['password']
        }
        user_dicts.append(user_dict)
    return user_dicts

def get_user_name(name):
    # Fetch data from Supabase table
    data = client.table('users').select('*').eq("username", name).execute()
    user_dicts = []
    for row in data.data:
        user_dict = {
            "id": row['id'],
            "username": row['username'],
        }
        user_dicts.append(user_dict)
    return user_dicts

def get_user_id(name):
    # Fetch data from Supabase table
    data = client.table('users').select('*').eq("username", name).execute()
    user_dicts = []
    for row in data.data:
        user_dict = {
            "id": row['id'],
        }
        user_dicts.append(user_dict)
    return user_dicts

def get_user_by_email(email):
    data = client.table('users').select('*').eq("email", email).single().execute()
    return data.data

#############################################
######## MOVIES #############################
#############################################

def insert_movies(title, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema):
    # Insert data into Supabase table
    client.table('lista').insert({"movie": title, "director": director, "genre": genre, "p_year": p_year, "v_date": v_date, "rating": rating, "rewatch": rewatch, "tv_show": tv_show, "poster": poster, "parent_id": parent_id, "cinema": cinema}).execute()
    
def get_movies(parent_id):
    # Fetch data from Supabase table
    data = client.table('lista').select('*').eq("parent_id", parent_id).execute()
    lista_dicts = []
    for row in data.data:
        movie_dict = {
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": datetime.strptime(row['v_date'], "%Y-%m-%d").date(),
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster'],
            "cinema": row['cinema']
        }
        lista_dicts.append(movie_dict)
    return lista_dicts


def get_monthly_movies(parent_id, month):
    current_year = datetime.now().year
    start_date = datetime(year=current_year, month=month, day=1)
    if month == 12:
        end_date = datetime(year=current_year + 1, month=1, day=1)
    else:
        end_date = datetime(year=current_year, month=month + 1, day=1)

    # Execute the query
    response = client.table('lista') \
        .select('*') \
        .eq('parent_id', parent_id) \
        .gte('v_date', start_date.strftime('%Y-%m-%d')) \
        .lt('v_date', end_date.strftime('%Y-%m-%d')) \
        .execute()
    lista_dicts = []
    for row in response.data:
        movie_dict = {
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": row['v_date'],
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster'],
            "cinema": row['cinema']
        }
        lista_dicts.append(movie_dict)
    return lista_dicts

def remove_movie_by_id(movie_id):
    # Remove data from Supabase table
    client.table('lista').delete().eq('lista_id', movie_id).execute()
    
def update_movie(lista_id, movie, director, p_year, rating, poster):
    # Update data in Supabase table
    client.table('lista').update({"movie": movie, "director": director, "p_year": p_year, "rating": rating, "poster": poster}).eq('lista_id', lista_id).execute()

def get_movies_groupby_director(parent_id):
    data = client.table('lista') \
        .select('*') \
        .eq('parent_id', parent_id) \
        .order('director') \
        .execute() 
    # Process the results
    lista_dicts = []
    for row in data.data:
        lista_dicts.append({
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": row['v_date'],
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster']
        })
    return lista_dicts

def get_directors(parent_id):
    data = client.table('lista') \
        .select('director') \
        .eq('parent_id', parent_id) \
        .order('director') \
        .execute()
    # Process the results
    distinct_directors = set()
    lista_dicts = []
    for row in data.data:
        distinct_directors.add(row['director'])
    for director in distinct_directors:
        lista_dicts.append({
            "name": director
        })
    return lista_dicts


def get_movies_groupby_genre(parent_id):
    data = client.table('lista') \
        .select('*') \
        .eq('parent_id', parent_id) \
        .order('genre') \
        .execute()
    
    # Process the results
    lista_dicts = []
    for row in data.data:
        lista_dicts.append({
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": row['v_date'],
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster']
        })
    return lista_dicts

def get_genres(parent_id):
    data = client.table('lista') \
        .select('genre') \
        .eq('parent_id', parent_id) \
        .order('genre') \
        .execute()
    # Process the results
    distinct_genres = set()
    lista_dicts = []
    for row in data.data:
        distinct_genres.add(row['genre'])
    for genre in distinct_genres:
        lista_dicts.append({
            "name": genre
        })
    return lista_dicts

def get_movies_groupby_year(parent_id):
    data = client.table('lista') \
        .select('*') \
        .eq('parent_id', parent_id) \
        .order('p_year') \
        .execute()
    
    # Process the results
    lista_dicts = []
    for row in data.data:
        lista_dicts.append({
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": row['v_date'],
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster']
        })
    return lista_dicts


def get_years(parent_id):
    data = client.table('lista') \
        .select('p_year') \
        .eq('parent_id', parent_id) \
        .order('p_year') \
        .execute()
    # Process the results
    distinct_years = set()
    lista_dicts = []
    for row in data.data:
        distinct_years.add(row['p_year'])
    for year in distinct_years:
        lista_dicts.append({
            "name": year
        })
    return lista_dicts

def get_movies_groupby_rating(parent_id):
    data = client.table('lista') \
        .select('*') \
        .eq('parent_id', parent_id) \
        .order('rating') \
        .execute()
    
    # Process the results
    lista_dicts = []
    for row in data.data:
        lista_dicts.append({
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": row['v_date'],
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster']
        })
    return lista_dicts

def get_ratings(parent_id):
    data = client.table('lista') \
        .select('rating') \
        .eq('parent_id', parent_id) \
        .order('rating') \
        .execute()
    # Process the results
    distinct_ratings = set()
    lista_dicts = []
    for row in data.data:
        distinct_ratings.add(row['rating'])
    for rating in distinct_ratings:
        lista_dicts.append({
            "name": rating
        })
    return lista_dicts

def get_highest_rating():
    now = datetime.now()
    if now.month == 1:
        start_date = datetime(year=now.year - 1, month=12, day=1)
    else:
        start_date = datetime(year=now.year, month=now.month - 1, day=1)

    if now.month == 12:
        end_date = datetime(year=now.year + 1, month=1, day=1)
    else:
        end_date = datetime(year=now.year, month=now.month + 1, day=1)
    # Execute the query
    data = client.table('lista') \
        .select('movie', 'director', 'p_year', 'poster') \
        .gte('rating', 9) \
        .gte('v_date', start_date.strftime('%Y-%m-%d')) \
        .lt('v_date', end_date.strftime('%Y-%m-%d')) \
        .execute()
        
    distinct_movies = set()
    lista_dicts = []
    
    for row in data.data:
        distinct_movies.add((row['movie'], row['director'], row['p_year'], row['poster']))
    for movie in distinct_movies:
        lista_dicts.append({
            "movie": movie[0],
            "director": movie[1],
            "p_year": movie[2],
            "poster": movie[3]
        })
    return lista_dicts

#############################################
######## FRIENDS ############################
#############################################

def insert_friends(user_id, f_username, parent_id):
    # Insert data into Supabase table
    client.table('friends').insert({"user_id": user_id, "f_username": f_username, "parent_id": parent_id}).execute()
    
def get_friends(parent_id):
    # Fetch data from Supabase table
    data = client.table('friends').select('*').eq("parent_id", parent_id).execute()
    friends_dicts = []
    for row in data.data:
        friend_dict = {
            "id": row['friend_id'],
            "user_id": row['user_id'],
            "f_username": row['f_username']
        }
        friends_dicts.append(friend_dict)
    return friends_dicts

def get_friend_activity(parent_id, limit=20):
    friends = get_friends(parent_id)
    if not friends:
        return []
    
    friend_ids = [f['user_id'] for f in friends]
    friend_map = {f['user_id']: f['f_username'] for f in friends}
    
    # Supabase allows 'in' filtering using .in_()
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
            
        movie_dict = {
            "id": row['lista_id'],
            "movie": row['movie'],
            "director": row['director'],
            "genre": row['genre'],
            "p_year": row['p_year'],
            "v_date": v_date_obj,
            "rating": row['rating'],
            "rewatch": row['rewatch'],
            "tv_show": row['tv_show'],
            "poster": row['poster'],
            "cinema": row['cinema'],
            "f_username": friend_map.get(row['parent_id'], "Unknown"),
            "f_user_id": row['parent_id']
        }
        lista_dicts.append(movie_dict)
    return lista_dicts

def remove_friend(parent_id, friend_id):
    client.table('friends').delete().eq('parent_id', parent_id).eq('user_id', friend_id).execute()

def get_taste_match(user_id, friend_id):
    user_movies = get_movies(user_id)
    friend_movies = get_movies(friend_id)
    
    # 1. Create fast lookups and determine unique libraries
    user_dict = {f"{m['movie'].lower()}_{m['p_year']}": m['rating'] for m in user_movies}
    friend_dict = {f"{m['movie'].lower()}_{m['p_year']}": m['rating'] for m in friend_movies}
    
    shared_keys = set(user_dict.keys()).intersection(set(friend_dict.keys()))
    total_unique_movies = len(set(user_dict.keys()).union(set(friend_dict.keys())))
    
    shared_count = len(shared_keys)
    
    # Handle edge case where they share zero movies
    if shared_count == 0:
        return {
            "match_percent": 0, 
            "shared_count": 0, 
            "shared_movies": [],
            "library_overlap": 0,
            "rating_similarity": 0,
            "harsher_critic": "None"
        }
        
    shared_movies = []
    sum_squared_diff = 0
    
    # Track totals to determine who is the harsher critic
    user_rating_sum = 0
    friend_rating_sum = 0

    for m in friend_movies:
        key = f"{m['movie'].lower()}_{m['p_year']}"
        if key in shared_keys:
            u_rating = user_dict[key]
            f_rating = m['rating']
            
            diff = abs(u_rating - f_rating)
            sum_squared_diff += diff ** 2  # Square the difference for RMSE
            
            user_rating_sum += u_rating
            friend_rating_sum += f_rating
            
            shared_movies.append({
                "movie": m['movie'],
                "poster": m['poster'],
                "year": m['p_year'],
                "u_rating": u_rating,
                "f_rating": f_rating,
                "diff": diff
            })
            
    # 2. Root Mean Square Error (RMSE)
    # Penalizes large disagreements heavily compared to minor differences
    rmse = math.sqrt(sum_squared_diff / shared_count)
    
    # Map RMSE to a 0-100 score (Assumes a 10-point scale. If using 5-point, change 10 to 20)
    rating_match_score = max(0, min(100, 100 - (rmse * 10)))
    
    # 3. Jaccard Index (Library Overlap)
    # What percentage of their combined unique libraries have they BOTH seen?
    overlap_percent = (shared_count / total_unique_movies) * 100 if total_unique_movies > 0 else 0
    
    # 4. Confidence Scaling
    # If they only share 1 or 2 movies, the match percentage is unreliable.
    # This gently scales the score down if they share fewer than 5 movies.
    confidence_multiplier = min(1.0, shared_count / 5.0) 
    
    final_match_percent = rating_match_score * confidence_multiplier

    # Sort shared movies by biggest agreements first, then by highest user rating
    shared_movies.sort(key=lambda x: (x['diff'], -x['u_rating']))
    
    # Determine the harsher critic for fun UI insights
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
#############################################
####### TOKENS ##############################
#############################################

def insert_token(user_id, token, date):
    client.table('tokens') \
        .insert([{'token': token, 'user_id': user_id, 'created_at': date}]) \
        .execute()

def get_token(token):
    data = client.table('tokens').select('*').eq("token", token).single().execute()
    return data.data
    
    
def delete_token(token):
    client.table('tokens').delete().eq('token', token).execute()
    
def update_user_password(user_id, password):
    client.table('users').update({"password": password}).eq('id', user_id).execute()

#from sqlalchemy import create_engine, text
#db_connection_string = os.environ.get("SECRET_DB_CONNECTION_STRING")
#
#engine = create_engine(db_connection_string,
#                       #connect_args= {
#                       #    "ssl": {
#                       #        "ssl_ca": "/etc/ssl/cert.pem"
#                       #     }
#                       # }
#                    )    
#
#def load_users_from_db():
#    with engine.connect() as conn:
#        rows = conn.execute(text("SELECT * FROM users"))
#        user_dicts = []
#        for row in rows:
#            user_dict = {}
#            user_dict["id"] = row[0]
#            user_dict["username"] = row[1]
#            user_dict["email"] = row[2]
#            user_dicts.append(user_dict)
#        return user_dicts
#
#def load_users_from_username(name):
#    with engine.connect() as conn:
#        # define a SQL query with a parameter
#        query = text('SELECT * FROM users WHERE username = :username').bindparams(username=name)
#        # execute the query with a parameter value
#        result = conn.execute(query)
#        
#        user_dicts = []
#        for row in result:
#            user_dict = {}
#            user_dict["id"] = row[0]
#            user_dict["username"] = row[1]
#            user_dict["email"] = row[2]
#            user_dicts.append(user_dict)
#        return user_dicts
#
#def load_users_from_email(email):
#    with engine.connect() as conn:
#        # define a SQL query with a parameter
#        query = text('SELECT * FROM users WHERE email = :email').bindparams(email=email)
#        # execute the query with a parameter value
#        result = conn.execute(query)
#        user_dicts = []
#        for row in result:
#            user_dict = {}
#            user_dict["id"] = row[0]
#            user_dict["username"] = row[1]
#            user_dict["email"] = row[2]
#            user_dict["password"] = row[3]
#            user_dicts.append(user_dict)
#        return user_dicts
#
#def insert_user(username, email, password):
#    with engine.connect() as conn:
#        query = text('INSERT INTO users (username, email, password) VALUES (:username, :email, :password)').bindparams(username=username, email=email, password=password)
#        conn.execute(query)
#        
#def get_user_by_id(id):
#    with engine.connect() as conn:
#        # define a SQL query with a parameter
#        query = text('SELECT * FROM users WHERE id = :id').bindparams(id=id)
#        # execute the query with a parameter value
#        result = conn.execute(query)
#        user_dicts = []
#        for row in result:
#            user_dict = {}
#            user_dict["id"] = row[0]
#            user_dict["username"] = row[1]
#            user_dict["email"] = row[2]
#            user_dict["password"] = row[3]
#            user_dicts.append(user_dict)
#        return user_dicts
#        
#def insert_movies(title, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema):
#     with engine.connect() as conn:
#        query = text('INSERT INTO lista (movie, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema) \
#                     VALUES (:movie, :director, :genre, :p_year, :v_date, :rating, :rewatch, :tv_show, :poster, :parent_id, :cinema)'
#                     ).bindparams(movie=title, director=director, genre=genre, p_year=p_year, v_date=v_date, rating=rating, rewatch=rewatch, tv_show=tv_show, poster=poster, parent_id=parent_id, cinema=cinema)
#        conn.execute(query)
#        
#def get_movies(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM lista WHERE parent_id = :parent_id').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["id"] = row[0]
#            lista_dict["movie"] = row[1]
#            lista_dict["director"] = row[2]
#            lista_dict["genre"] = row[3]
#            lista_dict["p_year"] = row[4]
#            lista_dict["v_date"] = row[5]
#            lista_dict["rating"] = row[6]
#            lista_dict["rewatch"] = row[7]
#            lista_dict["tv_show"] = row[8]
#            lista_dict["poster"] = row[9]
#            lista_dict["cinema"] = row[11]  
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#
#def get_monthly_movies(parent_id, month):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM lista WHERE parent_id = :parent_id and MONTH(v_date) = :month').bindparams(parent_id=parent_id, month=month)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["id"] = row[0]
#            lista_dict["movie"] = row[1]
#            lista_dict["director"] = row[2]
#            lista_dict["genre"] = row[3]
#            lista_dict["p_year"] = row[4]
#            lista_dict["v_date"] = row[5]
#            lista_dict["rating"] = row[6]
#            lista_dict["rewatch"] = row[7]
#            lista_dict["tv_show"] = row[8]
#            lista_dict["poster"] = row[9]     
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#    
#def get_user_name(name):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM users WHERE username = :username').bindparams(username=name)
#        result = conn.execute(query)
#        user_dicts = []
#        for row in result:
#            user_dict = {}
#            user_dict["id"] = row[0]
#            user_dict["username"] = row[1]
#            user_dicts.append(user_dict)
#        return user_dicts
#    
#def get_user_id(name):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM users WHERE username = :username').bindparams(username=name)
#        result = conn.execute(query)
#        user_dicts = []
#        for row in result:
#            user_dict = {}
#            user_dict["id"] = row[0]
#            user_dicts.append(user_dict)
#        return user_dicts
#
#def insert_friends(user_id, f_username, parent_id):
#    with engine.connect() as conn:
#        query = text('INSERT INTO friends (user_id, f_username, parent_id) VALUES (:user_id,:f_username, :parent_id)').bindparams(user_id=user_id, f_username=f_username ,parent_id=parent_id)
#        conn.execute(query)
#        
#def get_friends(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM friends WHERE parent_id = :parent_id').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        friends_dicts = []
#        for row in result:
#            friends_dict = {}
#            friends_dict["id"] = row[0]
#            friends_dict["user_id"] = row[1]
#            friends_dict["f_username"] = row[2]
#            friends_dicts.append(friends_dict)
#        return friends_dicts
#    
#def remove_movie_by_id(lista_id):
#    with engine.connect() as conn:
#        query = text('DELETE FROM lista WHERE lista_id = :lista_id').bindparams(lista_id=lista_id)
#        conn.execute(query)
#
#def update_movie(lista_id, movie, director, p_year, rating, poster):
#    with engine.connect() as conn:
#        query = text('UPDATE lista SET movie=:movie, director=:director, p_year=:p_year, rating=:rating, poster=:poster WHERE lista_id = :lista_id').bindparams(lista_id=lista_id, movie=movie, director=director, p_year=p_year, rating=rating, poster=poster)
#        conn.execute(query)
#        
#def get_movies_groupby_director(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY director').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["id"] = row[0]
#            lista_dict["movie"] = row[1]
#            lista_dict["director"] = row[2]
#            lista_dict["genre"] = row[3]
#            lista_dict["p_year"] = row[4]
#            lista_dict["v_date"] = row[5]
#            lista_dict["rating"] = row[6]
#            lista_dict["rewatch"] = row[7]
#            lista_dict["tv_show"] = row[8]
#            lista_dict["poster"] = row[9]    
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#
#def get_directors(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT DISTINCT director FROM lista WHERE parent_id = :parent_id ORDER BY director').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["name"] = row[0]
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#    
#def get_movies_groupby_genre(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY genre').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["id"] = row[0]
#            lista_dict["movie"] = row[1]
#            lista_dict["director"] = row[2]
#            lista_dict["genre"] = row[3]
#            lista_dict["p_year"] = row[4]
#            lista_dict["v_date"] = row[5]
#            lista_dict["rating"] = row[6]
#            lista_dict["rewatch"] = row[7]
#            lista_dict["tv_show"] = row[8]
#            lista_dict["poster"] = row[9]    
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#
#def get_genres(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT DISTINCT genre FROM lista WHERE parent_id = :parent_id ORDER BY genre').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["name"] = row[0]
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#    
#def get_movies_groupby_year(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY p_year').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["id"] = row[0]
#            lista_dict["movie"] = row[1]
#            lista_dict["director"] = row[2]
#            lista_dict["genre"] = row[3]
#            lista_dict["p_year"] = row[4]
#            lista_dict["v_date"] = row[5]
#            lista_dict["rating"] = row[6]
#            lista_dict["rewatch"] = row[7]
#            lista_dict["tv_show"] = row[8]
#            lista_dict["poster"] = row[9]    
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#
#def get_years(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT DISTINCT p_year FROM lista WHERE parent_id = :parent_id ORDER BY p_year').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["name"] = row[0]
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#    
#def get_movies_groupby_rating(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY rating').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["id"] = row[0]
#            lista_dict["movie"] = row[1]
#            lista_dict["director"] = row[2]
#            lista_dict["genre"] = row[3]
#            lista_dict["p_year"] = row[4]
#            lista_dict["v_date"] = row[5]
#            lista_dict["rating"] = row[6]
#            lista_dict["rewatch"] = row[7]
#            lista_dict["tv_show"] = row[8]
#            lista_dict["poster"] = row[9]    
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#
#def get_ratings(parent_id):
#    with engine.connect() as conn:
#        query = text('SELECT DISTINCT rating FROM lista WHERE parent_id = :parent_id ORDER BY rating').bindparams(parent_id=parent_id)
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["name"] = row[0]
#            lista_dicts.append(lista_dict)      
#        return lista_dicts
#    
#def get_user_by_email(email):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM users WHERE email = :email').bindparams(email=email)
#        result = conn.execute(query)
#        user = result.fetchone()
#        return user
#
#def insert_token(token, user_id, date):
#    with engine.connect() as conn:
#        query = text('INSERT INTO tokens (token, user_id, created_at) VALUES (:token, :user_id, :created_at)').bindparams(token=token, user_id=user_id, created_at=date)
#        conn.execute(query)
#        
#def get_token(token):
#    with engine.connect() as conn:
#        query = text('SELECT * FROM tokens WHERE token = :token').bindparams(token=token)
#        result = conn.execute(query)
#        token = result.fetchone()
#        return token
#    
#def delete_token(token):
#    with engine.connect() as conn:
#        query = text('DELETE FROM tokens WHERE token = :token').bindparams(token=token)
#        conn.execute(query)
#
#def update_user_password(user_id, password):
#    with engine.connect() as conn:
#        query = text('UPDATE users SET password = :password WHERE id = :user_id').bindparams(password=password, user_id=user_id)
#        conn.execute(query)
#        
#def get_highest_rating():
#    with engine.connect() as conn:
#        query = text('SELECT DISTINCT movie, director, p_year, poster FROM lista WHERE rating >= 9 AND v_date >= DATE_SUB(CURDATE(), INTERVAL 2 MONTH)')
#        result = conn.execute(query)
#        lista_dicts = []
#        for row in result:
#            lista_dict = {}
#            lista_dict["movie"] = row[0]
#            lista_dict["director"] = row[1]
#            lista_dict["p_year"] = row[2]
#            lista_dict["poster"] = row[3]    
#            lista_dicts.append(lista_dict)      
#        return lista_dicts