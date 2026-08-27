"""Quick CLI tool to test your email provider configuration from .env."""
import sys
import os
from dotenv import load_dotenv

# Load local .env
load_dotenv()

from config import Config
from app import create_app
from auth.restore import send_email_direct, build_reset_url

def main():
    recipient = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not recipient:
        print("Usage: python test_email.py <your_email@example.com>")
        print("\nExample: .\\.venv\\Scripts\\python test_email.py myemail@gmail.com")
        sys.exit(1)

    print("========================================")
    print("        Kineto Email Sender Test        ")
    print("========================================")
    print(f"BREVO API KEY  : {'Set' if Config.BREVO_API_KEY else 'Not set'}")
    print(f"SENDER         : {Config.MAIL_DEFAULT_SENDER}")
    print(f"TARGET INBOX   : {recipient}")
    print("========================================\n")

    app = create_app()
    with app.test_request_context():
        sample_url = build_reset_url("test-token-abcdef123456")
        print(f"Sending test email with reset URL:\n{sample_url}\n")
        
        success = send_email_direct(app, recipient, sample_url)
        
        if success:
            print("\n✓ SUCCESS: Test email was dispatched! Please check your inbox (and spam folder).")
        else:
            print("\n✗ FAILED: Email could not be sent. Check the error logs above.")

if __name__ == "__main__":
    main()
