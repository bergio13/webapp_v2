from flask import Flask, render_template, jsonify
from database import load_users_from_db, load_users_from_username

app = Flask(__name__)
   
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


@app.route('/')
def hello():
    return render_template('home.html')

@app.route('/lista')
def lista():
    users = load_users_from_db()
    return render_template('lista.html', users=users, months=months)

@app.route("/users/<name>")
def show_user_profile(name):
    user = load_users_from_username(name)
    return jsonify(user)

#@app.route('/api/about')
#def list_about():
#    return jsonify()
#

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/login')
def login():
    return render_template('login.html')

if __name__ == '__main__':
    app.run(debug=True)