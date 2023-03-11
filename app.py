from flask import Flask, render_template, jsonify

app = Flask(__name__)

months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
movies = ['a', 'b']

@app.route('/')
def hello():
    return render_template('home.html')

@app.route('/lista')
def lista():
    return render_template('lista.html', months=months, movies=movies)

@app.route('/api/about')
def list_about():
    return jsonify(months)


if __name__ == '__main__':
    app.run(debug=True)