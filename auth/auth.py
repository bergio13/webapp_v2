"""Authentication blueprint — login, register, logout."""
from flask import Blueprint, flash, redirect, render_template, request, session
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from auth.models import User
from database import (
    insert_user,
    load_users_from_email,
    load_users_from_username,
)

auth = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@auth.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an existing user."""
    if current_user.is_authenticated:
        return redirect("/home")

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if not email or not password:
            flash("Email and password are required!", category="error")
            return render_template("login.html")

        try:
            users = load_users_from_email(email)
        except Exception:
            users = []
            flash("Something went wrong, please try again", category="error")

        if users:
            user_data = users[0]
            if user_data["email"] == email and check_password_hash(user_data["password"], password):
                user_obj = User(id=user_data["id"], username=user_data["username"], email=user_data["email"])
                login_user(user_obj)
                session["loggedin"] = True
                session["id"] = user_data["id"]
                session["email"] = user_data["email"]
                flash("Logged in successfully!", category="success")
                return redirect("/home")
            else:
                flash("Incorrect username or password!", category="error")
        else:
            flash("No account found for this email!", category="error")

    return render_template("login.html")


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@auth.route("/register", methods=["GET", "POST"])
def register():
    """Create a new user account."""
    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not email or len(email) < 4:
            flash("Please provide a valid email address (at least 4 characters)", category="error")
            return render_template("register.html")

        if not name or len(name) < 2:
            flash("Username must be at least 2 characters long", category="error")
            return render_template("register.html")

        if not password or len(password) < 3:
            flash("Password must be at least 3 characters long", category="error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match", category="error")
            return render_template("register.html")

        if load_users_from_email(email):
            flash("An account with this email already exists", category="error")
            return render_template("register.html")

        if load_users_from_username(name):
            flash("Username is already taken, please choose a different one", category="error")
            return render_template("register.html")

        try:
            hashed = generate_password_hash(password, method="scrypt")
            insert_user(name, email, password=hashed)

            users = load_users_from_email(email)
            if users:
                user_data = users[0]
                user_obj = User(id=user_data["id"], username=user_data["username"], email=user_data["email"])
                login_user(user_obj)
                session["loggedin"] = True
                session["id"] = user_data["id"]
                session["email"] = user_data["email"]

            flash("Your account has been created successfully!", category="success")
            return redirect("/home")
        except Exception:
            flash("An error occurred while creating your account. Please try again.", category="error")

    return render_template("register.html")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth.route("/logout")
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out", "success")
    return redirect("/login")
