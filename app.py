from flask import Flask, render_template, jsonify
from database import load_users_from_db

app = Flask(__name__)
   
months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


@app.route('/')
def hello():
    return render_template('home.html')

@app.route('/lista')
def lista():
    users = load_users_from_db()
    return render_template('lista.html', users=users, months=months)

#@app.route('/api/about')
#def list_about():
#    return jsonify()
#

if __name__ == '__main__':
    app.run(debug=True)