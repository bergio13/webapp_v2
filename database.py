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
            user_dict["password"] = row[3]
            user_dicts.append(user_dict)
        return user_dicts