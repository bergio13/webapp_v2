from sqlalchemy import create_engine, text
import os

db_connection_string = os.environ.get("SECRET_DB_CONNECTION_STRING")

engine = create_engine(db_connection_string,
                       connect_args= {
                           "ssl": {
                               "ssl_ca": "/etc/ssl/cert.pem"
                            }
                        })

def load_users_from_db():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM users"))
        user_dicts = []
        for row in rows:
            user_dict = {}
            user_dict["id"] = row[0]
            user_dict["username"] = row[1]
            user_dict["email"] = row[2]
            user_dicts.append(user_dict)
        return user_dicts

def load_users_from_username(name):
    with engine.connect() as conn:
        # define a SQL query with a parameter
        query = text('SELECT * FROM users WHERE username = :username').bindparams(username=name)
        # execute the query with a parameter value
        result = conn.execute(query)
        
        user_dicts = []
        for row in result:
            user_dict = {}
            user_dict["id"] = row[0]
            user_dict["username"] = row[1]
            user_dict["email"] = row[2]
            user_dicts.append(user_dict)
        return user_dicts

def load_users_from_email(email):
    with engine.connect() as conn:
        # define a SQL query with a parameter
        query = text('SELECT * FROM users WHERE email = :email').bindparams(email=email)
        # execute the query with a parameter value
        result = conn.execute(query)
        user_dicts = []
        for row in result:
            user_dict = {}
            user_dict["id"] = row[0]
            user_dict["username"] = row[1]
            user_dict["email"] = row[2]
            user_dict["password"] = row[3]
            user_dicts.append(user_dict)
        return user_dicts

def insert_user(username, email, password):
    with engine.connect() as conn:
        query = text('INSERT INTO users (username, email, password) VALUES (:username, :email, :password)').bindparams(username=username, email=email, password=password)
        conn.execute(query)
        
def get_user_by_id(id):
    with engine.connect() as conn:
        # define a SQL query with a parameter
        query = text('SELECT * FROM users WHERE id = :id').bindparams(id=id)
        # execute the query with a parameter value
        result = conn.execute(query)
        user_dicts = []
        for row in result:
            user_dict = {}
            user_dict["id"] = row[0]
            user_dict["username"] = row[1]
            user_dict["email"] = row[2]
            user_dict["password"] = row[3]
            user_dicts.append(user_dict)
        return user_dicts
        
def insert_movies(title, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema):
     with engine.connect() as conn:
        query = text('INSERT INTO lista (movie, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id, cinema) \
                     VALUES (:movie, :director, :genre, :p_year, :v_date, :rating, :rewatch, :tv_show, :poster, :parent_id, :cinema)'
                     ).bindparams(movie=title, director=director, genre=genre, p_year=p_year, v_date=v_date, rating=rating, rewatch=rewatch, tv_show=tv_show, poster=poster, parent_id=parent_id, cinema=cinema)
        conn.execute(query)
        
def get_movies(parent_id):
    with engine.connect() as conn:
        query = text('SELECT * FROM lista WHERE parent_id = :parent_id').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["id"] = row[0]
            lista_dict["movie"] = row[1]
            lista_dict["director"] = row[2]
            lista_dict["genre"] = row[3]
            lista_dict["p_year"] = row[4]
            lista_dict["v_date"] = row[5]
            lista_dict["rating"] = row[6]
            lista_dict["rewatch"] = row[7]
            lista_dict["tv_show"] = row[8]
            lista_dict["poster"] = row[9]
            lista_dict["cinema"] = row[11]  
            lista_dicts.append(lista_dict)      
        return lista_dicts

def get_monthly_movies(parent_id, month):
    with engine.connect() as conn:
        query = text('SELECT * FROM lista WHERE parent_id = :parent_id and MONTH(v_date) = :month').bindparams(parent_id=parent_id, month=month)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["id"] = row[0]
            lista_dict["movie"] = row[1]
            lista_dict["director"] = row[2]
            lista_dict["genre"] = row[3]
            lista_dict["p_year"] = row[4]
            lista_dict["v_date"] = row[5]
            lista_dict["rating"] = row[6]
            lista_dict["rewatch"] = row[7]
            lista_dict["tv_show"] = row[8]
            lista_dict["poster"] = row[9]     
            lista_dicts.append(lista_dict)      
        return lista_dicts
    
def get_user_name(name):
    with engine.connect() as conn:
        query = text('SELECT * FROM users WHERE username = :username').bindparams(username=name)
        result = conn.execute(query)
        user_dicts = []
        for row in result:
            user_dict = {}
            user_dict["id"] = row[0]
            user_dict["username"] = row[1]
            user_dicts.append(user_dict)
        return user_dicts
    
def get_user_id(name):
    with engine.connect() as conn:
        query = text('SELECT * FROM users WHERE username = :username').bindparams(username=name)
        result = conn.execute(query)
        user_dicts = []
        for row in result:
            user_dict = {}
            user_dict["id"] = row[0]
            user_dicts.append(user_dict)
        return user_dicts

def insert_friends(user_id, f_username, parent_id):
    with engine.connect() as conn:
        query = text('INSERT INTO friends (user_id, f_username, parent_id) VALUES (:user_id,:f_username, :parent_id)').bindparams(user_id=user_id, f_username=f_username ,parent_id=parent_id)
        conn.execute(query)
        
def get_friends(parent_id):
    with engine.connect() as conn:
        query = text('SELECT * FROM friends WHERE parent_id = :parent_id').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        friends_dicts = []
        for row in result:
            friends_dict = {}
            friends_dict["id"] = row[0]
            friends_dict["user_id"] = row[1]
            friends_dict["f_username"] = row[2]
            friends_dicts.append(friends_dict)
        return friends_dicts
    
def remove_movie_by_id(lista_id):
    with engine.connect() as conn:
        query = text('DELETE FROM lista WHERE lista_id = :lista_id').bindparams(lista_id=lista_id)
        conn.execute(query)

def update_movie(lista_id, movie, director, p_year, rating, poster):
    with engine.connect() as conn:
        query = text('UPDATE lista SET movie=:movie, director=:director, p_year=:p_year, rating=:rating, poster=:poster WHERE lista_id = :lista_id').bindparams(lista_id=lista_id, movie=movie, director=director, p_year=p_year, rating=rating, poster=poster)
        conn.execute(query)
        
def get_movies_groupby_director(parent_id):
    with engine.connect() as conn:
        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY director').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["id"] = row[0]
            lista_dict["movie"] = row[1]
            lista_dict["director"] = row[2]
            lista_dict["genre"] = row[3]
            lista_dict["p_year"] = row[4]
            lista_dict["v_date"] = row[5]
            lista_dict["rating"] = row[6]
            lista_dict["rewatch"] = row[7]
            lista_dict["tv_show"] = row[8]
            lista_dict["poster"] = row[9]    
            lista_dicts.append(lista_dict)      
        return lista_dicts

def get_directors(parent_id):
    with engine.connect() as conn:
        query = text('SELECT DISTINCT director FROM lista WHERE parent_id = :parent_id ORDER BY director').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["name"] = row[0]
            lista_dicts.append(lista_dict)      
        return lista_dicts
    
def get_movies_groupby_genre(parent_id):
    with engine.connect() as conn:
        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY genre').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["id"] = row[0]
            lista_dict["movie"] = row[1]
            lista_dict["director"] = row[2]
            lista_dict["genre"] = row[3]
            lista_dict["p_year"] = row[4]
            lista_dict["v_date"] = row[5]
            lista_dict["rating"] = row[6]
            lista_dict["rewatch"] = row[7]
            lista_dict["tv_show"] = row[8]
            lista_dict["poster"] = row[9]    
            lista_dicts.append(lista_dict)      
        return lista_dicts

def get_genres(parent_id):
    with engine.connect() as conn:
        query = text('SELECT DISTINCT genre FROM lista WHERE parent_id = :parent_id ORDER BY genre').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["name"] = row[0]
            lista_dicts.append(lista_dict)      
        return lista_dicts
    
def get_movies_groupby_year(parent_id):
    with engine.connect() as conn:
        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY p_year').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["id"] = row[0]
            lista_dict["movie"] = row[1]
            lista_dict["director"] = row[2]
            lista_dict["genre"] = row[3]
            lista_dict["p_year"] = row[4]
            lista_dict["v_date"] = row[5]
            lista_dict["rating"] = row[6]
            lista_dict["rewatch"] = row[7]
            lista_dict["tv_show"] = row[8]
            lista_dict["poster"] = row[9]    
            lista_dicts.append(lista_dict)      
        return lista_dicts

def get_years(parent_id):
    with engine.connect() as conn:
        query = text('SELECT DISTINCT p_year FROM lista WHERE parent_id = :parent_id ORDER BY p_year').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["name"] = row[0]
            lista_dicts.append(lista_dict)      
        return lista_dicts
    
def get_movies_groupby_rating(parent_id):
    with engine.connect() as conn:
        query = text('SELECT * FROM lista WHERE parent_id = :parent_id ORDER BY rating').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["id"] = row[0]
            lista_dict["movie"] = row[1]
            lista_dict["director"] = row[2]
            lista_dict["genre"] = row[3]
            lista_dict["p_year"] = row[4]
            lista_dict["v_date"] = row[5]
            lista_dict["rating"] = row[6]
            lista_dict["rewatch"] = row[7]
            lista_dict["tv_show"] = row[8]
            lista_dict["poster"] = row[9]    
            lista_dicts.append(lista_dict)      
        return lista_dicts

def get_ratings(parent_id):
    with engine.connect() as conn:
        query = text('SELECT DISTINCT rating FROM lista WHERE parent_id = :parent_id ORDER BY rating').bindparams(parent_id=parent_id)
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["name"] = row[0]
            lista_dicts.append(lista_dict)      
        return lista_dicts
    
def get_user_by_email(email):
    with engine.connect() as conn:
        query = text('SELECT * FROM users WHERE email = :email').bindparams(email=email)
        result = conn.execute(query)
        user = result.fetchone()
        return user

def insert_token(token, user_id, date):
    with engine.connect() as conn:
        query = text('INSERT INTO tokens (token, user_id, created_at) VALUES (:token, :user_id, :created_at)').bindparams(token=token, user_id=user_id, created_at=date)
        conn.execute(query)
        
def get_token(token):
    with engine.connect() as conn:
        query = text('SELECT * FROM tokens WHERE token = :token').bindparams(token=token)
        result = conn.execute(query)
        token = result.fetchone()
        return token
    
def delete_token(token):
    with engine.connect() as conn:
        query = text('DELETE FROM tokens WHERE token = :token').bindparams(token=token)
        conn.execute(query)

def update_user_password(user_id, password):
    with engine.connect() as conn:
        query = text('UPDATE users SET password = :password WHERE id = :user_id').bindparams(password=password, user_id=user_id)
        conn.execute(query)
        
def get_highest_rating():
    with engine.connect() as conn:
        query = text('SELECT DISTINCT movie, director, p_year, poster FROM lista WHERE rating >= 9 AND v_date >= DATE_SUB(CURDATE(), INTERVAL 2 MONTH)')
        result = conn.execute(query)
        lista_dicts = []
        for row in result:
            lista_dict = {}
            lista_dict["movie"] = row[0]
            lista_dict["director"] = row[1]
            lista_dict["p_year"] = row[2]
            lista_dict["poster"] = row[3]    
            lista_dicts.append(lista_dict)      
        return lista_dicts