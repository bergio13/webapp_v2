from flask import Flask, render_template, jsonify, request, flash, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import load_users_from_db, load_users_from_username, engine, load_users_from_email, insert_user, get_user_id
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)


#class User(db.Model, UserMixin):
#    __tablename__ = 'users'
#
#    id = Column(Integer, primary_key=True, autoincrement=True)
#    username = Column(String(50), unique=True, nullable=False)
#    email = Column(String(120), unique=True, nullable=False)
#    password = Column(String(120), nullable=False)
#    
#    def __init__(self, username, email, password):
#        self.username = username
#        self.email = email
#        self.password = password
#
##    def __repr__(self):
##        return f"<User(username='{self.username}', email='{self.email}')>"
##
   
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


@app.route('/')
def hello():
    return render_template('home.html', session=session)

@app.route('/lista')
def lista():
    try:
        users = load_users_from_db()
    except:
        users = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('lista.html', users=users, months=months)

@app.route("/users/<name>")
def show_user_profile(name):
    user = load_users_from_username(name)
    return jsonify(user)

#@app.route('/api/about')
#def list_about():
#    data = get_user_id(1)
#    user = User(id=data[0]['id'], username=data[0]['username'], email=data[0]['email'], password=data[0]['password'])
#    return jsonify(data[0])
##

@app.route('/register', methods=['GET', 'POST'])
def register():
        """Register user"""
        if request.method == "POST":
            # Require username
            email = request.form.get("email")
            name = request.form.get("username")
            password = request.form.get("password")

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
            else:
            # Create hash of password to insert into the database
                hash = generate_password_hash(request.form.get("password"), method='sha256')

                insert_user(name, email, password=hash)
                flash('Account created', category='success')

                return redirect("/")

        return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        email = request.form['email']
        password = request.form['password']
        
        users = load_users_from_email(email)
        if users != []:
            if users[0]['email'] == email and users[0]['password'] == password:
                session['loggedin'] = True
                session['id'] = users[0]['id']
                session['email'] = users[0]['email']
                flash ('Logged in successfully!', category='success')
                return redirect('/')
         # If account exists in accounts table in out database
            else:
            # Account doesnt exist or username/password incorrect
                flash ('Incorrect username/password!')

    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("login.html", session=session)

@app.route('/profile')
def profile():
    if 'loggedin' in session:
        users = get_user_id(session['id'])
        return render_template('profile.html', user=users[0])
    return redirect('/login')

@app.route('/logout')
def logout():
    # Remove session data, this will log the user out
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('email', None)
   # Redirect to login page
    return redirect('/')

@app.route('/add_movie', methods=['GET', 'POST'])
def add_movie():
    if request.method == "POST":
        title = request.form.get("title")
        director = request.form.get("director")
        year = request.form.get("year")
        date = request.form.get("date")
        genre = request.form.get("genre")
        rating = request.form.get("rating")
        rewatch = request.form.get("rewatch")
        tv = request.form.get("tv")
    return render_template('add_movie.html')
        

if __name__ == '__main__':
    app.run(debug=True)