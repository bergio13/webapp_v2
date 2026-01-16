from flask import Blueprint, render_template, request, jsonify, current_app, redirect, flash
from flask_mail import Message
import secrets
from datetime import datetime, timedelta
from database import *
from werkzeug.security import generate_password_hash


# Create a Password Reset Blueprint
restore = Blueprint('restore', __name__)  

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
        
        # Use the app context to send the email
        try:
            from flask import current_app
            mail = current_app.extensions.get('mail')
            if not mail:
                error_msg = "ERROR: Mail extension not found in app"
                print(error_msg)
                return jsonify({'error': 'Email service not configured'}), 500
            
            print(f"Attempting to send email to {user['email']}...")
            print(f"SMTP Config: {current_app.config.get('MAIL_SERVER')}:{current_app.config.get('MAIL_PORT')}")
            print(f"Using TLS: {current_app.config.get('MAIL_USE_TLS')}, SSL: {current_app.config.get('MAIL_USE_SSL')}")
            
            import socket
            import time
            start_time = time.time()
            
            mail.send(msg)
            
            elapsed = time.time() - start_time
            print(f"✓ Password reset email sent successfully to {user['email']} in {elapsed:.2f}s")
            
        except socket.timeout as e:
            error_msg = f"SMTP Timeout: Connection timed out after {current_app.config.get('MAIL_TIMEOUT', 'unknown')}s"
            print(f"ERROR: {error_msg}")
            print(f"Full error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Email server timeout. Please try again later.'}), 500
        except socket.error as e:
            error_msg = f"SMTP Socket Error: {str(e)}"
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Cannot connect to email server. Please contact support.'}), 500
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"{error_type}: {str(e)}"
            print(f"ERROR sending email: {error_msg}")
            import traceback
            traceback.print_exc()
            
            # Provide more helpful error messages
            if 'authentication' in str(e).lower():
                return jsonify({'error': 'Email authentication failed. Please contact support.'}), 500
            elif 'refused' in str(e).lower():
                return jsonify({'error': 'Email server refused connection. Please try again later.'}), 500
            else:
                return jsonify({'error': f'Failed to send email: {error_msg}'}), 500

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
