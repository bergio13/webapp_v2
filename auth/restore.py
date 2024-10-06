from flask import Blueprint, render_template, request, jsonify, current_app, redirect, flash
from flask_mail import Message, Mail
import secrets
from datetime import datetime, timedelta
from database import *
from werkzeug.security import generate_password_hash


# Create a Password Reset Blueprint
restore = Blueprint('restore', __name__)

# Use the 'mail' object that should be defined in your main app file
mail = Mail()  

def generate_token():
    return secrets.token_hex(16)

def is_expired(creation_date):
    return datetime.now() > (creation_date + timedelta(hours=24))

@restore.route('/passwordreset', methods=['GET', 'POST'])
def request_password_reset():
    if request.method == 'POST':
        email = request.form['email']
        if not email:
            return jsonify({'error': 'Email is required'}), 400

        user = get_user_by_email(email)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        print(user)

        # Generate a new reset token
        token = generate_token()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        insert_token(user['id'], token, now)
        
        # Send an email to the user with the reset link
        reset_url = f"https://lista-film-v2.onrender.com/passwordreset/{token}"
        msg = Message('Reset Your Password', sender='kinetowebapp@gmail.com', recipients=[user['email']])
        msg.body = f"Click this link to reset your password: {reset_url}"
        
        # Use the app context to send the email
        with current_app.app_context():
            mail.send(msg)

        return jsonify({'message': 'Password reset email sent, if you do not find it check your spam folder'})
    
    return render_template('passwordreset.html')

@restore.route('/passwordreset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        password = request.form['password']
        hash = generate_password_hash(password, method='sha256')
        if not password:
            return jsonify({'error': 'Password is required'}), 400
    
        # Find the reset token
        reset_token = get_token(token)
        print(reset_token)
        if not reset_token:
            return jsonify({'error': 'Invalid token'}), 404
        
        creation_date = reset_token.get('created_at')
        creation_date = datetime.fromisoformat(creation_date)
        print(creation_date)
        if is_expired(creation_date):
            return jsonify({'error': 'Token has expired'}), 400
    
        # Update the user's password
        user_id = reset_token.get('user_id')
        update_user_password(user_id, hash)
        delete_token(token)
        flash('Password has been reset successfully!', category='success')
        return redirect('/home')
    
    return render_template('reset2.html')
