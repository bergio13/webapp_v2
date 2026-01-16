from flask import Blueprint, render_template, request, jsonify, current_app, redirect, flash
from flask_mail import Message
import secrets
from datetime import datetime, timedelta
from database import *
from werkzeug.security import generate_password_hash
from threading import Thread
import time


# Create a Password Reset Blueprint
restore = Blueprint('restore', __name__)

def send_async_email(app, msg, recipient_email):
    """Send email in background thread with timeout"""
    with app.app_context():
        try:
            mail = app.extensions.get('mail')
            if not mail:
                print("ERROR: Mail extension not found in background thread")
                return
            
            print(f"[Background Thread] Attempting to send email to {recipient_email}...")
            start_time = time.time()
            
            mail.send(msg)
            
            elapsed = time.time() - start_time
            print(f"[Background Thread] ✓ Email sent successfully to {recipient_email} in {elapsed:.2f}s")
            
        except Exception as e:
            error_type = type(e).__name__
            print(f"[Background Thread] ERROR sending email: {error_type}: {str(e)}")
            import traceback
            traceback.print_exc()  

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
        msg.html = f"<p>Click <a href='{reset_url}'>here</a> to reset your password.</p><p>Or copy this link: {reset_url}</p><p>This link will expire in 24 hours.</p>"
        
        # Send email in background thread to avoid blocking the request
        print(f"Queueing password reset email to {user['email']}...")
        print(f"SMTP Config: {current_app.config.get('MAIL_SERVER')}:{current_app.config.get('MAIL_PORT')}")
        print(f"Using TLS: {current_app.config.get('MAIL_USE_TLS')}, SSL: {current_app.config.get('MAIL_USE_SSL')}")
        
        # Start background thread for email sending
        thread = Thread(target=send_async_email, args=(current_app._get_current_object(), msg, user['email']))
        thread.daemon = True
        thread.start()
        
        print(f"Email queued successfully. Sending in background...")
        
        # Return immediately without waiting for email to send
        return jsonify({'message': 'Password reset email is being sent. Please check your inbox (and spam folder) in a few moments.'})
    
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
