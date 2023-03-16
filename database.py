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
        
def get_user_id(id):
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
        