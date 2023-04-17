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
        
def insert_movies(title, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id):
     with engine.connect() as conn:
        query = text('INSERT INTO lista (movie, director, genre, p_year, v_date, rating, rewatch, tv_show, poster, parent_id) \
                     VALUES (:movie, :director, :genre, :p_year, :v_date, :rating, :rewatch, :tv_show, :poster, :parent_id)'
                     ).bindparams(movie=title, director=director, genre=genre, p_year=p_year, v_date=v_date, rating=rating, rewatch=rewatch, tv_show=tv_show, poster=poster, parent_id=parent_id)
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