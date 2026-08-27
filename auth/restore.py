"""Password reset blueprint — token generation, email dispatching, and password updating."""
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from threading import Thread

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_mail import Message
import requests
from werkzeug.security import generate_password_hash

from database import (
    delete_token,
    delete_user_tokens,
    get_token,
    get_user_by_email,
    insert_token,
    update_user_password,
)

logger = logging.getLogger(__name__)

# Create a Password Reset Blueprint
restore = Blueprint("restore", __name__)


def generate_token():
    """Generate a secure cryptographically random URL-safe token."""
    return secrets.token_urlsafe(32)


def parse_token_date(creation_date_val):
    """Safely parse creation_date into a timezone-aware UTC datetime."""
    if not creation_date_val:
        return None
    if isinstance(creation_date_val, datetime):
        if creation_date_val.tzinfo is None:
            return creation_date_val.replace(tzinfo=timezone.utc)
        return creation_date_val.astimezone(timezone.utc)
    if isinstance(creation_date_val, str):
        val = creation_date_val.strip()
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    dt = datetime.strptime(val, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    return None


def is_expired(creation_date, max_age_hours=24):
    """Check if token is older than max_age_hours."""
    dt = parse_token_date(creation_date)
    if not dt:
        return True
    now = datetime.now(timezone.utc)
    return now > (dt + timedelta(hours=max_age_hours))


def build_reset_url(token):
    """Build reset URL respecting Render environment variables, reverse proxy headers, and local hosts."""
    base_url = (
        current_app.config.get("RENDER_EXTERNAL_URL")
        or current_app.config.get("BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("BASE_URL")
    )
    if base_url:
        return f"{base_url.rstrip('/')}/passwordreset/{token}"
    return url_for("restore.reset_password", token=token, _external=True)


def build_email_content(reset_url):
    """Generate HTML and plain text email content with Kineto styling."""
    plain_text = (
        f"Kineto - Password Reset\n\n"
        f"We received a request to reset your password for your Kineto account.\n"
        f"Click the link below to set a new password:\n{reset_url}\n\n"
        f"This link will expire in 24 hours.\n"
        f"If you did not request this reset, you can safely ignore this email."
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Reset Your Password</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #0b0f19; padding: 40px 10px;">
        <tr>
          <td align="center">
            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 520px; background: linear-gradient(180deg, #111827 0%, #0f172a 100%); border: 1px solid #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
              <tr>
                <td style="padding: 32px 32px 16px 32px; text-align: center; border-bottom: 1px solid #1e293b;">
                  <h1 style="margin: 0; font-family: 'Courier New', Courier, monospace; font-size: 26px; letter-spacing: 2px; color: #00f0ff; text-transform: uppercase;">
                    [ KINETO ]
                  </h1>
                  <p style="margin: 6px 0 0 0; font-size: 13px; color: #64748b; letter-spacing: 1px;">
                    // SECURITY SYSTEM //
                  </p>
                </td>
              </tr>
              <tr>
                <td style="padding: 32px 32px 24px 32px;">
                  <h2 style="margin: 0 0 16px 0; font-size: 20px; color: #f8fafc; font-weight: 600;">
                    Password Reset Request
                  </h2>
                  <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #94a3b8;">
                    We received a request to reset your password. Click the button below to choose a new password for your account:
                  </p>
                  <table border="0" cellpadding="0" cellspacing="0" width="100%">
                    <tr>
                      <td align="center" style="padding: 8px 0 28px 0;">
                        <a href="{reset_url}" target="_blank" style="display: inline-block; background-color: #00f0ff; color: #050b14; font-size: 15px; font-weight: 700; text-decoration: none; padding: 14px 32px; border-radius: 6px; letter-spacing: 0.5px; box-shadow: 0 0 15px rgba(0, 240, 255, 0.4);">
                          Reset Password
                        </a>
                      </td>
                    </tr>
                  </table>
                  <p style="margin: 0 0 12px 0; font-size: 13px; color: #64748b; line-height: 1.5;">
                    If the button doesn't work, copy and paste this URL into your browser:
                  </p>
                  <p style="margin: 0 0 24px 0; font-size: 12px; color: #38bdf8; word-break: break-all; font-family: monospace; background: #070d18; padding: 10px 12px; border-radius: 4px; border: 1px solid #1e293b;">
                    {reset_url}
                  </p>
                  <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.5; border-top: 1px solid #1e293b; padding-top: 16px;">
                    This link will expire in <strong style="color: #cbd5e1;">24 hours</strong>. If you didn't request a password reset, you can safely ignore this email.
                  </p>
                </td>
              </tr>
              <tr>
                <td style="padding: 20px 32px; background-color: #070b12; text-align: center; border-top: 1px solid #1e293b;">
                  <p style="margin: 0; font-size: 12px; color: #475569;">
                    © Kineto Web App. All rights reserved.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    return plain_text, html_content


def send_email_direct(app, recipient_email, reset_url):
    """Send reset email via Gmail SMTP using Flask-Mail."""
    with app.app_context():
        plain_text, html_content = build_email_content(reset_url)
        subject = "Reset Your Password - Kineto"
        sender = app.config.get("MAIL_DEFAULT_SENDER", "kinetoweb@gmail.com")

        start_time = time.time()
        logger.info("[Email Dispatch] Starting send to %s via Gmail SMTP...", recipient_email)

        try:
            mail = app.extensions.get("mail")
            if not mail:
                logger.error("[Email Dispatch] Flask-Mail extension not found")
                return False

            msg = Message(subject=subject, sender=sender, recipients=[recipient_email])
            msg.body = plain_text
            msg.html = html_content

            mail.send(msg)
            elapsed = time.time() - start_time
            logger.info("[Email Dispatch] ✓ Sent via SMTP to %s in %.2fs", recipient_email, elapsed)
            return True
        except Exception as e:
            logger.exception("[Email Dispatch] SMTP error sending email: %s", e)
            return False


@restore.route("/passwordreset", methods=["GET", "POST"])
def request_password_reset():
    """Handle password reset request — accepts both HTML form post and AJAX/JSON."""
    if request.method == "POST":
        email = ""
        if request.is_json and request.json:
            email = request.json.get("email", "").strip()
        elif request.form:
            email = request.form.get("email", "").strip()

        if not email:
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"error": "Email is required"}), 400
            flash("Please enter a valid email address.", category="error")
            return render_template("passwordreset.html")

        user = get_user_by_email(email)
        if user:
            try:
                # Clean up any existing tokens for this user
                delete_user_tokens(user["id"])

                # Generate new secure token and save with timezone-aware timestamp
                token = generate_token()
                now_utc = datetime.now(timezone.utc).isoformat()
                insert_token(user["id"], token, now_utc)

                # Build dynamic reset URL
                reset_url = build_reset_url(token)

                # Dispatch email
                app_obj = current_app._get_current_object()
                send_email_direct(app_obj, user["email"], reset_url)
            except Exception as e:
                logger.exception("Error processing password reset token: %s", e)

        # Consistent user-facing response to prevent email enumeration
        success_msg = "If an account exists with this email, a password reset link has been sent. Please check your inbox (and spam folder)."
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"message": success_msg})

        flash(success_msg, category="success")
        return redirect(url_for("auth.login"))

    return render_template("passwordreset.html")


@restore.route("/passwordreset/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Handle token validation and password setting."""
    reset_token = get_token(token)

    if not reset_token:
        flash("The password reset link is invalid or has already been used.", category="error")
        return redirect(url_for("restore.request_password_reset"))

    creation_date = reset_token.get("created_at")
    if is_expired(creation_date):
        delete_token(token)
        flash("The password reset link has expired (valid for 24 hours). Please request a new one.", category="error")
        return redirect(url_for("restore.request_password_reset"))

    if request.method == "POST":
        password = ""
        confirm_password = ""
        if request.is_json and request.json:
            password = request.json.get("password", "").strip()
            confirm_password = request.json.get("confirm_password", "").strip()
        elif request.form:
            password = request.form.get("password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

        if not password or len(password) < 3:
            err_msg = "Password must be at least 3 characters long."
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"error": err_msg}), 400
            flash(err_msg, category="error")
            return render_template("reset2.html", token=token)

        if confirm_password and password != confirm_password:
            err_msg = "Passwords do not match."
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"error": err_msg}), 400
            flash(err_msg, category="error")
            return render_template("reset2.html", token=token)

        try:
            user_id = reset_token.get("user_id")
            hashed_password = generate_password_hash(password, method="scrypt")
            update_user_password(user_id, hashed_password)
            delete_token(token)

            flash("Password has been reset successfully! Please log in with your new password.", category="success")
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"message": "Password has been reset successfully."})

            return redirect(url_for("auth.login"))
        except Exception as e:
            logger.exception("Error updating user password: %s", e)
            err_msg = "An error occurred while updating your password. Please try again."
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"error": err_msg}), 500
            flash(err_msg, category="error")
            return render_template("reset2.html", token=token)

    return render_template("reset2.html", token=token)
