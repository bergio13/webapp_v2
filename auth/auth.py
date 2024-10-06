from flask import Blueprint, render_template, request, redirect, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import *

# Create the blueprint
auth = Blueprint('auth', __name__)

# Login route
@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Log user in"""
    # If user is already logged in, redirect to home
    if session.get('loggedin'):
        return redirect('/home')

    # Forget any user_id
    session.clear()

    # User reached route via POST (submitting a form)
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        # Validate inputs
        if not email or not password:
            flash('Email and password are required!', category='error')
            return render_template("login.html", session=session)

        try:
            users = load_users_from_email(email)
        except Exception as e:
            users = []
            flash('Something went wrong, please try again', category='error')

        if users:
            user = users[0]
            # Verify the user's password
            if user['email'] == email and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['id'] = user['id']
                session['email'] = user['email']
                flash('Logged in successfully!', category='success')
                return redirect('/home')
            else:
                flash('Incorrect username or password!', category='error')
        else:
            flash('No account found for this email!', category='error')

    # User reached route via GET (clicking a link or via redirect)
    return render_template("login.html", session=session)


# Register route
@auth.route('/register', methods=['GET', 'POST'])
def register():
        """Register user"""
        if request.method == "POST":
            # Require username
            email = request.form.get("email")
            name = request.form.get("username")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")

             # Validate email
            if not email or len(email) < 4:
                flash('Please provide a valid email address (at least 4 characters)', category='error')
                return render_template('register.html')
    
            # Validate username
            if not name or len(name) < 2:
                flash('Username must be at least 2 characters long', category='error')
                return render_template('register.html')
    
            # Check password length and match
            if not password or len(password) < 3:
                flash('Password must be at least 3 characters long', category='error')
                return render_template('register.html')
    
            if password != confirm_password:
                flash('Passwords do not match', category='error')
                return render_template('register.html')
            
            
            # Check if the email or username already exists in the database
            existing_user_email = load_users_from_email(email)
            existing_user_username = load_users_from_username(name)
            
            if existing_user_email:
                flash('An account with this email already exists', category='error')
                return render_template('register.html')
    
            if existing_user_username:
                flash('Username is already taken, please choose a different one', category='error')
                return render_template('register.html')
    
            # If validation passed, hash the password and insert the new user into the database
            try:
                hashed_password = generate_password_hash(password, method='sha256')
                insert_user(name, email, password=hashed_password)
                flash('Your account has been created successfully!', category='success')
                return redirect('/home')
            except Exception as e:
                flash('An error occurred while creating your account. Please try again.', category='error')
            
        return render_template('register.html')

# Logout route
@auth.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect('/login')
