import os
import supabase
from datetime import datetime, timedelta

SUPABASE_URL = os.environ.get("SUPABASEURL")
SUPABASE_KEY = os.environ.get("SUPABASEKEY")

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
    start_date = datetime(year=datetime.now().year, month=month, day=1)
    end_date = start_date + timedelta(days=31)  # Assuming 31 days maximum for a month

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
    start_date = datetime(year=datetime.now().year, month=datetime.now().month - 1, day=1)
    end_date = start_date + timedelta(days=62)  # Assuming 31 days maximum for a month
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