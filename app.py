#Install the required Python packages
# pip install flask
# pip install flask-sqlalchemy
# pip install sqlalchemy
# pip install werkzeug

# Current Email Configuration:
# Email: braculostandfound6@gmail.com
# Server: smtp.gmail.com
# Port: 587
# TLS: Enabled
# Make sure to set MAIL_USERNAME and MAIL_PASSWORD environment variables



from flask import Flask, render_template, request, redirect, jsonify, session, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
import re
from datetime import datetime, timedelta
from io import BytesIO
from flask_mail import Mail, Message as MailMessage
import secrets
import json
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.graphics.barcode import qr
    from reportlab.graphics import renderPDF
except Exception as e:
    # ReportLab may not be installed in some environments; route will guard accordingly
    canvas = None
    A4 = None
    inch = 72
    qr = None
    renderPDF = None

app = Flask(__name__)

# Database Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///ecommerce.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "ecommerce_secret"

# Email Configuration (via environment variables; sensible defaults)
# Current email: braculostandfound6@gmail.com
# Make sure to set MAIL_USERNAME and MAIL_PASSWORD environment variables
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME'))

mail = Mail(app)

# File upload configuration
UPLOAD_FOLDER = 'static/uploads'
# Allow common image types and a few document formats for chat/file uploads
ALLOWED_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp',
    'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'
}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# Helper to check mail credentials presence
def are_mail_credentials_present():
    return bool(app.config.get('MAIL_USERNAME')) and bool(app.config.get('MAIL_PASSWORD'))

# Helper functions for user suspension checks
def is_user_suspended(user_id, suspension_type='full_suspension'):
    """Check if a user is currently suspended"""
    now = datetime.now()
    active_suspension = UserSuspension.query.filter_by(
        user_id=user_id,
        suspension_type=suspension_type,
        is_active=True
    ).filter(UserSuspension.end_date > now).first()
    
    return active_suspension is not None

def can_user_post(user_id):
    """Check if a user can post items"""
    if is_user_suspended(user_id, 'full_suspension'):
        return False
    if is_user_suspended(user_id, 'posting_ban'):
        return False
    return True

def can_user_chat(user_id):
    """Check if a user can send chat messages"""
    if is_user_suspended(user_id, 'full_suspension'):
        return False
    if is_user_suspended(user_id, 'chat_ban'):
        return False
    return True

def get_user_report_count(user_id):
    """Get the current number of active reports against a user"""
    return Report.query.filter_by(
        reported_user_id=user_id,
        status='pending'
    ).count()

# Helper functions for points and badge system
def get_or_create_user_points(user_id, commit=True):
    """Get or create user points record"""
    user_points = UserPoints.query.filter_by(user_id=user_id).first()
    if not user_points:
        user_points = UserPoints(user_id=user_id, return_points=0, total_points=0)
        db.session.add(user_points)
        if commit:
            db.session.commit()
    else:
        # Ensure existing records have proper default values
        if user_points.return_points is None:
            user_points.return_points = 0
        if user_points.total_points is None:
            user_points.total_points = 0
    return user_points

def award_return_points(user_id, points=1, commit=True):
    """Award return points to a user and check for badge unlocks"""
    print(f"DEBUG: award_return_points - Awarding {points} points to user {user_id}")
    
    user_points = get_or_create_user_points(user_id, commit=False)
    print(f"DEBUG: award_return_points - User points record: {user_points.id if user_points else 'None'}")
    
    # Safety check: ensure points are not None
    if user_points.return_points is None:
        user_points.return_points = 0
    if user_points.total_points is None:
        user_points.total_points = 0
    
    print(f"DEBUG: award_return_points - Before: return_points={user_points.return_points}, total_points={user_points.total_points}")
    user_points.return_points += points
    user_points.total_points += points
    print(f"DEBUG: award_return_points - After: return_points={user_points.return_points}, total_points={user_points.total_points}")
    
    # Check for badge unlocks
    check_and_award_badges(user_id, user_points.return_points)
    
    # Only commit if explicitly requested
    if commit:
        print(f"DEBUG: award_return_points - Committing changes")
        db.session.commit()
    else:
        print(f"DEBUG: award_return_points - Not committing (commit=False)")
    
    return user_points

def check_and_award_badges(user_id, return_points):
    """Check if user qualifies for new badges and award them"""
    existing_badges = {badge.badge_type for badge in UserBadge.query.filter_by(user_id=user_id).all()}
    
    # Badge definitions
    badges_to_check = [
        (1, 'first_return', 'First Return', 'Successfully returned your first item'),
        (5, 'trusted_finder', 'Trusted Finder', 'Returned 5 items - you are trusted by the community'),
        (10, 'community_hero', 'Community Hero', 'Returned 10 items - you are a community hero!')
    ]
    
    badges_awarded = []
    notifications_created = []
    
    for required_points, badge_type, badge_name, badge_description in badges_to_check:
        if return_points >= required_points and badge_type not in existing_badges:
            new_badge = UserBadge(
                user_id=user_id,
                badge_type=badge_type,
                badge_name=badge_name,
                badge_description=badge_description
            )
            db.session.add(new_badge)
            badges_awarded.append(new_badge)
            
            # Create notification for badge unlock
            notification = Notification(
                user_id=user_id,
                title=f'🎖️ New Badge Unlocked: {badge_name}',
                message=f'Congratulations! You\'ve earned the {badge_name} badge for returning {required_points} items.',
                url='/profile'
            )
            db.session.add(notification)
            notifications_created.append(notification)
    
    # Commit all badges and notifications if any were created
    if badges_awarded or notifications_created:
        try:
            db.session.commit()
            print(f"DEBUG: Successfully awarded {len(badges_awarded)} badges and created {len(notifications_created)} notifications for user {user_id}")
        except Exception as e:
            print(f"DEBUG: Error committing badges/notifications: {e}")
            db.session.rollback()

def get_user_badges(user_id):
    """Get all badges for a user"""
    return UserBadge.query.filter_by(user_id=user_id).order_by(UserBadge.unlocked_at.desc()).all()

def get_user_return_points(user_id):
    """Get user's return points"""
    user_points = UserPoints.query.filter_by(user_id=user_id).first()
    points = user_points.return_points if user_points else 0
    print(f"DEBUG: User {user_id} has {points} return points")
    return points

# ---------------- Matching helpers (lightweight) ----------------
def _tokenize_text(text: str):
    try:
        text = (text or '').lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return [t for t in text.split() if t]
    except Exception:
        return []

def _match_score(a, b) -> float:
    a_tokens = set(_tokenize_text(getattr(a, 'name', '')) + _tokenize_text(getattr(a, 'description', '')) + _tokenize_text(getattr(a, 'location', '')))
    b_tokens = set(_tokenize_text(getattr(b, 'name', '')) + _tokenize_text(getattr(b, 'description', '')) + _tokenize_text(getattr(b, 'location', '')))
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    jaccard = inter / union
    value_bonus = 0.0
    try:
        av = float(getattr(a, 'value', 0)) if getattr(a, 'value', None) is not None else None
        bv = float(getattr(b, 'value', 0)) if getattr(b, 'value', None) is not None else None
        if av is not None and bv is not None:
            diff = abs(av - bv)
            base = max(1.0, max(av, bv))
            value_bonus = max(0.0, 0.2 - (diff / base))
    except Exception:
        value_bonus = 0.0
    loc_bonus = 0.1 if (getattr(a, 'location', None) and getattr(b, 'location', None) and str(getattr(a, 'location')).strip().lower() == str(getattr(b, 'location')).strip().lower()) else 0.0
    return jaccard + value_bonus + loc_bonus

def _has_token_overlap(a, b) -> bool:
    a_tokens = set(_tokenize_text(getattr(a, 'name', '')) + _tokenize_text(getattr(a, 'description', '')) + _tokenize_text(getattr(a, 'location', '')))
    b_tokens = set(_tokenize_text(getattr(b, 'name', '')) + _tokenize_text(getattr(b, 'description', '')) + _tokenize_text(getattr(b, 'location', '')))
    return len(a_tokens & b_tokens) >= 1

# ------------ Email Verification Model ------------
class EmailVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    verification_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

# ------------ Lost Item Model ------------
class LostItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Float, nullable=True)  # Optional value
    description = db.Column(db.String(500), nullable=False)
    photo_filename = db.Column(db.String(200), nullable=True)  # Optional photo filename
    photo_filenames = db.Column(db.Text, nullable=True)  # JSON array of filenames
    location = db.Column(db.String(200), nullable=True)  # Where it was lost/found
    date_lost = db.Column(db.DateTime, default=db.func.current_timestamp())
    status = db.Column(db.String(20), default='lost')  # lost, found, claimed, warehouse
    reported_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    warehouse_deadline = db.Column(db.DateTime, nullable=True)  # When item will be sent to warehouse
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# ------------ User Model ------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    student_faculty_id = db.Column(db.String(8), nullable=False, unique=True)  # 8-digit ID
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    profile_photo = db.Column(db.String(200))
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# ------------ Notification Model ------------
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(300), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# ------------ Activity Log Model ------------
class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for anonymous actions
    action_type = db.Column(db.String(50), nullable=False)  # login, logout, create_item, edit_item, delete_item, etc.
    action_description = db.Column(db.String(500), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('lost_item.id'), nullable=True)  # Related item if applicable
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    user_agent = db.Column(db.String(500), nullable=True)  # Browser/device info
    additional_data = db.Column(db.Text, nullable=True)  # JSON data for extra context
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref='activities')
    item = db.relationship('LostItem', backref='activities')

# ------------ Report Models ------------
class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('lost_item.id'), nullable=True)
    report_type = db.Column(db.String(20), nullable=False)  # 'scam' or 'harassment'
    reason = db.Column(db.String(500), nullable=False)
    evidence = db.Column(db.String(1000), nullable=True)  # Additional evidence or description
    status = db.Column(db.String(20), default='pending')  # 'pending', 'reviewed', 'resolved', 'dismissed'
    admin_notes = db.Column(db.String(1000), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationships
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='reports_filed')
    reported_user = db.relationship('User', foreign_keys=[reported_user_id], backref='reports_received')
    item = db.relationship('LostItem', backref='reports')
    admin_reviewer = db.relationship('User', foreign_keys=[reviewed_by], backref='reports_reviewed')

class UserSuspension(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    suspension_type = db.Column(db.String(20), nullable=False)  # 'posting_ban', 'chat_ban', 'full_suspension'
    reason = db.Column(db.String(500), nullable=False)
    report_count = db.Column(db.Integer, nullable=False)  # Number of reports that triggered this suspension
    start_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref='suspensions')

# ------------ Points and Badge Models ------------
class UserPoints(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    return_points = db.Column(db.Integer, default=0)  # Points earned from returning items
    total_points = db.Column(db.Integer, default=0)  # Total points (can be expanded later)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref='points')

class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_type = db.Column(db.String(50), nullable=False)  # 'first_return', 'trusted_finder', 'community_hero'
    badge_name = db.Column(db.String(100), nullable=False)
    badge_description = db.Column(db.String(200), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref='badges')

class ItemReturn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('lost_item.id'), nullable=True)  # Allow NULL for deleted items
    finder_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    return_type = db.Column(db.String(20), nullable=False)  # 'found_item_return', 'lost_item_recovery'
    helper_type = db.Column(db.String(20), nullable=True)  # 'user', 'non_user'
    helper_identifier = db.Column(db.String(200), nullable=True)  # User ID, email, or name for non-users
    points_awarded = db.Column(db.Integer, default=0)
    confirmed_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationships
    item = db.relationship('LostItem', backref='returns')
    finder = db.relationship('User', foreign_keys=[finder_id], backref='items_returned')
    owner = db.relationship('User', foreign_keys=[owner_id], backref='items_received')

# ------------ Chat Models ------------
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_b_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint('user_a_id', 'user_b_id', name='uq_conversation_pair'),
    )

    def has_participant(self, user_id: int) -> bool:
        return user_id in (self.user_a_id, self.user_b_id)

    @staticmethod
    def get_or_create_between(user_one_id: int, user_two_id: int):
        # Keep user_a_id < user_b_id to satisfy unique constraint deterministically
        a_id = min(user_one_id, user_two_id)
        b_id = max(user_one_id, user_two_id)
        convo = Conversation.query.filter_by(user_a_id=a_id, user_b_id=b_id).first()
        if convo:
            return convo
        convo = Conversation(user_a_id=a_id, user_b_id=b_id)
        db.session.add(convo)
        db.session.commit()
        return convo


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), index=True)
    # Optional attachment filename stored under static/uploads
    attachment = db.Column(db.String(300), nullable=True)

# Ensure new columns exist in SQLite without full migrations (run once on import)
def _ensure_chat_schema():
    try:
        with db.engine.connect() as conn:
            try:
                info = conn.execute(text("PRAGMA table_info(message)")).fetchall()
                columns = [row[1] for row in info]
                if 'attachment' not in columns:
                    conn.execute(text("ALTER TABLE message ADD COLUMN attachment VARCHAR(300)"))
            except Exception:
                pass
    except Exception:
        pass

def _fix_existing_user_points():
    """Fix any existing UserPoints records that have NULL values"""
    try:
        with db.engine.connect() as conn:
            # Update any NULL return_points to 0
            conn.execute(text("UPDATE user_points SET return_points = 0 WHERE return_points IS NULL"))
            # Update any NULL total_points to 0
            conn.execute(text("UPDATE user_points SET total_points = 0 WHERE total_points IS NULL"))
            conn.commit()
            print("DEBUG: Fixed existing UserPoints records with NULL values")
    except Exception as e:
        print(f"DEBUG: Error fixing UserPoints records: {e}")
        pass

def _fix_item_return_schema():
    """Fix ItemReturn table to allow NULL item_id"""
    try:
        with db.engine.connect() as conn:
            # Check if item_id column allows NULL
            info = conn.execute(text("PRAGMA table_info(item_return)")).fetchall()
            columns = {row[1]: row for row in info}
            
            if 'item_id' in columns and columns['item_id'][3] == 0:  # 0 means NOT NULL
                print("DEBUG: Updating ItemReturn table to allow NULL item_id")
                # Create a new table with the correct schema
                conn.execute(text("""
                    CREATE TABLE item_return_new (
                        id INTEGER PRIMARY KEY,
                        item_id INTEGER REFERENCES lost_item(id),
                        finder_id INTEGER NOT NULL REFERENCES user(id),
                        owner_id INTEGER NOT NULL REFERENCES user(id),
                        return_type VARCHAR(20) NOT NULL,
                        helper_type VARCHAR(20),
                        helper_identifier VARCHAR(200),
                        points_awarded INTEGER DEFAULT 0,
                        confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                # Copy data from old table
                conn.execute(text("INSERT INTO item_return_new SELECT * FROM item_return"))
                
                # Drop old table and rename new one
                conn.execute(text("DROP TABLE item_return"))
                conn.execute(text("ALTER TABLE item_return_new RENAME TO item_return"))
                
                conn.commit()
                print("DEBUG: Successfully updated ItemReturn table schema")
            else:
                print("DEBUG: ItemReturn table already allows NULL item_id")
    except Exception as e:
        print(f"DEBUG: Error fixing ItemReturn schema: {e}")
        pass

# Call the schema check once at startup
try:
    with app.app_context():
        _ensure_chat_schema()
        _fix_existing_user_points()
        _fix_item_return_schema()
except Exception:
    pass

# Helper function to check if file extension is allowed
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper function to calculate warehouse deadline (150 hours from creation)
def calculate_warehouse_deadline():
    return datetime.now() + timedelta(hours=150)

# Helper function to format time remaining
def format_time_remaining(deadline):
    if not deadline:
        return "No deadline set"
    
    now = datetime.now()
    if now >= deadline:
        return "Expired - Sent to warehouse"
    
    remaining = deadline - now
    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m remaining"
    elif hours > 0:
        return f"{hours}h {minutes}m remaining"
    else:
        return f"{minutes}m remaining"

# Helper function to generate verification code
def generate_verification_code():
    return ''.join(secrets.choice('0123456789') for _ in range(6))

# Helper function to send verification email
def send_verification_email(email, verification_code):
    try:
        # Guard: ensure credentials exist
        if not are_mail_credentials_present():
            print("Email not sent: MAIL_USERNAME/MAIL_PASSWORD environment variables are not set.")
            print(f"[VERIFICATION CODE] For email {email}: {verification_code}")
            return True
        msg = MailMessage(
            subject='Email Verification Code',
            sender=app.config.get('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_USERNAME'),
            recipients=[email]
        )
        msg.body = f'''
Thank you for signing up!

Your verification code is: {verification_code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.
'''
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        print(f"[VERIFICATION CODE] For email {email}: {verification_code}")
        return True

# Helper function to send password reset verification email
def send_password_reset_verification_email(email, verification_code):
    try:
        # Guard: ensure credentials exist
        if not are_mail_credentials_present():
            print("Email not sent: MAIL_USERNAME/MAIL_PASSWORD environment variables are not set.")
            print(f"[PASSWORD RESET VERIFICATION CODE] For email {email}: {verification_code}")
            return True
        msg = MailMessage(
            subject='Password Reset Verification Code',
            sender=app.config.get('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_USERNAME'),
            recipients=[email]
        )
        msg.body = f'''
You have requested to reset your password.

Your verification code is: {verification_code}

This code will expire in 10 minutes.

If you did not request this code, please ignore this email.
'''
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        print(f"[PASSWORD RESET VERIFICATION CODE] For email {email}: {verification_code}")
        return True

# Helper to send verification for identity (to current email)
def send_identity_verification_email(email, verification_code):
    try:
        if not are_mail_credentials_present():
            print("Email not sent: MAIL_USERNAME/MAIL_PASSWORD environment variables are not set.")
            print(f"[IDENTITY VERIFY CODE] For email {email}: {verification_code}")
            return True
        msg = MailMessage(
            subject='Verify your identity to change email',
            sender=app.config.get('MAIL_USERNAME'),
            recipients=[email]
        )
        msg.body = f'''\
You requested to change your account email.\n\nVerification code: {verification_code}\n\nThis code will expire in 10 minutes.\nIf you did not request this, please secure your account.'''
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending identity verification email: {e}")
        print(f"[IDENTITY VERIFY CODE] For email {email}: {verification_code}")
        return True

# Helper to send verification to new email
def send_new_email_verification(email, verification_code):
    try:
        if not are_mail_credentials_present():
            print("Email not sent: MAIL_USERNAME/MAIL_PASSWORD environment variables are not set.")
            print(f"[NEW EMAIL VERIFY CODE] For email {email}: {verification_code}")
            return True
        msg = MailMessage(
            subject='Verify your new email address',
            sender=app.config.get('MAIL_USERNAME'),
            recipients=[email]
        )
        msg.body = f'''\
You're changing your account email to this address.\n\nVerification code: {verification_code}\n\nThis code will expire in 10 minutes.\nIf you did not request this, ignore this email.'''
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending new email verification: {e}")
        print(f"[NEW EMAIL VERIFY CODE] For email {email}: {verification_code}")
        return True

# Helper to send verification for profile updates (distinct subject/body)
def send_profile_update_verification_email(email, verification_code):
    try:
        if not are_mail_credentials_present():
            print("Email not sent: MAIL_USERNAME/MAIL_PASSWORD environment variables are not set.")
            print(f"[PROFILE UPDATE VERIFY CODE] For email {email}: {verification_code}")
            return True
        msg = MailMessage(
            subject='Confirm Profile Update',
            sender=app.config.get('MAIL_USERNAME'),
            recipients=[email]
        )
        msg.body = f'''\
You attempted to update your profile information.\n\nVerification code: {verification_code}\n\nThis code will expire in 10 minutes.\nIf you did not request this change, please review your account activity.'''
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending profile update verification: {e}")
        print(f"[PROFILE UPDATE VERIFY CODE] For email {email}: {verification_code}")
        return True

# Helper function to send email-change verification email (code goes to current email)
 

# ---------------- Generic Email + Notification Helpers ----------------
def send_email(subject, recipients, body):
    try:
        if not are_mail_credentials_present():
            print("Email not sent: MAIL_USERNAME/MAIL_PASSWORD environment variables are not set.")
            print(f"[EMAIL FALLBACK] Subject: {subject}\nTo: {', '.join(recipients)}\n\n{body}")
            return True
        msg = MailMessage(
            subject=subject,
            sender=app.config.get('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_USERNAME'),
            recipients=recipients
        )
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        print(f"[EMAIL FALLBACK] Subject: {subject}\nTo: {', '.join(recipients)}\n\n{body}")
        return True

def send_item_submission_email(user, item, submission_type):
    if not user or not user.email:
        return False
    item_url = url_for('home', _external=False)
    subject = f"{submission_type.capitalize()} item submitted: {item.name}"
    include_deadline = submission_type == 'found'
    deadline_line = (
        f"- Warehouse deadline: {item.warehouse_deadline.strftime('%Y-%m-%d %H:%M:%S') if item.warehouse_deadline else 'N/A'}\n"
        if include_deadline else ""
    )
    body = (
        f"Hello {user.first_name or user.username},\n\n"
        f"Your {submission_type} item has been submitted successfully.\n\n"
        f"Item details:\n"
        f"- Name: {item.name}\n"
        f"- Description: {item.description}\n"
        f"- Status: {item.status}\n"
        f"{deadline_line}\n"
        f"You can view the list on the portal: {item_url}\n\n"
        f"This is an automated message."
    )
    return send_email(subject, [user.email], body)

def send_item_status_update_email(user, item, old_status, new_status):
    if not user or not user.email:
        return False
    item_url = url_for('home', _external=False)
    subject = f"Status update for '{item.name}': {old_status} → {new_status}"
    body = (
        f"Hello {user.first_name or user.username},\n\n"
        f"The status of your item has changed.\n\n"
        f"Item details:\n"
        f"- Name: {item.name}\n"
        f"- Previous status: {old_status}\n"
        f"- New status: {new_status}\n"
        f"- Warehouse deadline: {item.warehouse_deadline.strftime('%Y-%m-%d %H:%M:%S') if item.warehouse_deadline else 'N/A'}\n\n"
        f"Visit the portal for more details: {item_url}\n\n"
        f"This is an automated message."
    )
    return send_email(subject, [user.email], body)

def send_item_deleted_email(user, item, previous_status, undo_url=None):
    if not user or not user.email:
        return False
    subject = f"Item removed: {item.name}"
    undo_line = f"\nUndo removal: {undo_url}\n" if undo_url else "\n"
    body = (
        f"Hello {user.first_name or user.username},\n\n"
        f"Your item has been removed from the portal.\n\n"
        f"Item details:\n"
        f"- Name: {item.name}\n"
        f"- Previous status: {previous_status}\n"
        f"- New status: deleted\n"
        f"{undo_line}"
        f"This is an automated message."
    )
    return send_email(subject, [user.email], body)

def create_notification(user_id, title, message, url=None):
    try:
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            url=url or url_for('home', _external=False)
        )
        db.session.add(notification)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification: {e}")
        return False

# ---------------- Activity Logging Helpers ----------------
def log_activity(user_id=None, action_type='', action_description='', item_id=None, additional_data=None):
    """Helper function to log user activities"""
    try:
        # Get client information
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None
        
        # Convert additional_data to JSON string if it's a dict
        if isinstance(additional_data, dict):
            additional_data = json.dumps(additional_data)
        
        activity = ActivityLog(
            user_id=user_id,
            action_type=action_type,
            action_description=action_description,
            item_id=item_id,
            ip_address=ip_address,
            user_agent=user_agent,
            additional_data=additional_data
        )
        db.session.add(activity)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error logging activity: {e}")
        return False

def get_user_activity_summary(user_id):
    """Get a comprehensive summary of user activities"""
    try:
        from datetime import datetime, timedelta
        
        # Get all user activities
        all_activities = ActivityLog.query.filter_by(user_id=user_id).all()
        
        # Calculate time periods
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        # Filter activities by time period
        this_week = [a for a in all_activities if a.created_at and a.created_at >= week_ago]
        this_month = [a for a in all_activities if a.created_at and a.created_at >= month_ago]
        
        # Get last activity date
        last_activity = ActivityLog.query.filter_by(user_id=user_id)\
            .order_by(ActivityLog.created_at.desc()).first()
        
        # Activity type breakdown
        activity_types = {}
        for activity in all_activities:
            activity_type = activity.action_type
            activity_types[activity_type] = activity_types.get(activity_type, 0) + 1
        
        summary = {
            'total_activities': len(all_activities),
            'this_week': len(this_week),
            'this_month': len(this_month),
            'last_activity_date': last_activity.created_at.strftime('%Y-%m-%d') if last_activity and last_activity.created_at else None,
            'activity_types': activity_types,
            'recent_activities': [
                {
                    'action_type': a.action_type,
                    'description': a.action_description,
                    'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S') if a.created_at else None,
                    'item_id': a.item_id
                } for a in all_activities[:10]  # Last 10 activities
            ]
        }
        return summary
    except Exception as e:
        print(f"Error getting activity summary: {e}")
        return None

# Helper function to clean expired verification codes
def clean_expired_codes():
    now_utc = datetime.now()
    expired_codes = EmailVerification.query.filter(
        EmailVerification.expires_at < now_utc
    ).all()
    for code in expired_codes:
        db.session.delete(code)
    if expired_codes:
        db.session.commit()

# Helper function to check and move expired items to warehouse
def check_warehouse_deadlines():
    expired_items = LostItem.query.filter(
        LostItem.warehouse_deadline <= datetime.now(),
        LostItem.status.in_(['lost', 'found'])
    ).all()
    # Prepare notifications before status change
    notifications = []
    for item in expired_items:
        old_status = item.status
        item.status = 'warehouse'
        if item.reported_by:
            reporter = db.session.get(User, item.reported_by)
            if reporter:
                notifications.append((reporter, item, old_status, 'warehouse'))
    if expired_items:
        db.session.commit()
        print(f"Moved {len(expired_items)} items to warehouse")
        # Send notifications after commit
        for reporter, item, old_status, new_status in notifications:
            send_item_status_update_email(reporter, item, old_status, new_status)
            create_notification(
                user_id=reporter.id,
                title="Item moved to warehouse",
                message=f"Your item '{item.name}' has been moved to the warehouse.",
                url=f"{url_for('home', _external=False)}#item-{item.id}"
            )
            
            # Log warehouse movement activity
            log_activity(
                user_id=reporter.id,
                action_type='item_moved_to_warehouse',
                action_description=f'Item "{item.name}" automatically moved to warehouse after deadline',
                item_id=item.id,
                additional_data={
                    'item_name': item.name,
                    'previous_status': old_status,
                    'new_status': new_status,
                    'warehouse_deadline': item.warehouse_deadline.isoformat() if item.warehouse_deadline else None,
                    'reason': 'automatic_deadline_expiry'
                }
            )
    return len(expired_items)

# Create Database Tables
with app.app_context():
    db.create_all()
    # Lightweight migration: ensure photo_filename exists on lost_item
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('lost_item')]
        if 'photo_filename' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE lost_item ADD COLUMN photo_filename VARCHAR(200)'))
                print("Added column 'photo_filename' to lost_item table")
        if 'photo_filenames' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE lost_item ADD COLUMN photo_filenames TEXT'))
                print("Added column 'photo_filenames' to lost_item table")
            # Best-effort backfill: seed photo_filenames from photo_filename
            try:
                items = LostItem.query.filter(LostItem.photo_filename.isnot(None)).all()
                for it in items:
                    if not it.photo_filenames:
                        it.photo_filenames = json.dumps([it.photo_filename])
                if items:
                    db.session.commit()
            except Exception as be:
                db.session.rollback()
                print(f"Backfill photo_filenames skipped: {be}")
    except Exception as e:
        # If inspection/alter fails, log and continue without blocking app start
        print(f"Migration check for photo_filename failed or skipped: {e}")

# ------------ Routes ------------

# Profile Management Routes
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('Please log in to access your profile.')
        return redirect(url_for('login'))
    
    user = db.session.get(User, session['user_id'])
    
    if not user:
        flash('User not found. Please log in again.')
        session.clear()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Stage changes in session and verify via email before applying
        pending = {
            'first_name': request.form.get('first_name', user.first_name or ''),
            'last_name': request.form.get('last_name', user.last_name or ''),
            'phone': request.form.get('phone', user.phone or ''),
            'address': request.form.get('address', user.address or ''),
            'profile_photo_filename': None
        }
        # Handle profile photo upload to temp name; only commit after verification
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename != '' and allowed_file(file.filename):
                original = secure_filename(file.filename)
                temp_token = secrets.token_hex(8)
                temp_name = f"user_{user.id}_pending_{temp_token}_{original}"
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_name)
                file.save(temp_path)
                pending['profile_photo_filename'] = temp_name

        session['pending_profile_update'] = pending

        # Send verification code to current email
        clean_expired_codes()
        code = generate_verification_code()
        print(f"=== GENERATED PROFILE UPDATE VERIFY CODE: {code} for {user.email} ===")
        expires_at = datetime.now() + timedelta(minutes=10)
        verification = EmailVerification(
            email=user.email,
            verification_code=code,
            expires_at=expires_at
        )
        db.session.add(verification)
        db.session.commit()
        send_profile_update_verification_email(user.email, code)
        flash('We sent a verification code to your email to confirm profile updates.')
        return redirect(url_for('verify_profile_update'))
    
    # Get user's report and suspension information
    report_count = get_user_report_count(user.id)
    active_suspensions = UserSuspension.query.filter_by(
        user_id=user.id,
        is_active=True
    ).filter(UserSuspension.end_date > datetime.now()).all()
    
    # Get recent reports against this user
    recent_reports = Report.query.filter_by(
        reported_user_id=user.id
    ).order_by(Report.created_at.desc()).limit(5).all()
    
    # Get user's points and badges
    user_points = get_user_return_points(user.id)
    user_badges = get_user_badges(user.id)
    print(f"DEBUG: Profile view - User {user.id} ({user.username}) has {user_points} points and {len(user_badges)} badges")
    
    return render_template('profile.html', 
                         user=user, 
                         report_count=report_count,
                         active_suspensions=active_suspensions,
                         recent_reports=recent_reports,
                         user_points=user_points,
                         user_badges=user_badges)

# Home Route (Displays Lost and Found Items)
@app.route("/")
def home():
    # Check for expired items and move them to warehouse
    check_warehouse_deadlines()
    
    # --- Search Filters ---
    item_name = request.args.get('item', '').strip()
    location = request.args.get('location', '').strip()
    keyword = request.args.get('keyword', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    def parse_date(value):
        try:
            if not value:
                return None
            # Accept YYYY-MM-DD
            return datetime.strptime(value, '%Y-%m-%d')
        except Exception:
            return None

    dt_from = parse_date(date_from)
    dt_to = parse_date(date_to)
    if dt_to:
        # include the whole end day by adding almost one day and subtracting a microsecond
        dt_to = dt_to + timedelta(days=1) - timedelta(microseconds=1)

    def apply_filters(query):
        if item_name:
            query = query.filter(LostItem.name.ilike(f"%{item_name}%"))
        if location:
            query = query.filter(LostItem.location.ilike(f"%{location}%"))
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                (LostItem.description.ilike(like)) |
                (LostItem.name.ilike(like)) |
                (LostItem.location.ilike(like))
            )
        if dt_from:
            query = query.filter(LostItem.created_at >= dt_from)
        if dt_to:
            query = query.filter(LostItem.created_at <= dt_to)
        return query

    # Get items by status - ensure we only get items that actually exist
    lost_items = apply_filters(
        LostItem.query.filter_by(status='lost')
    ).order_by(LostItem.created_at.desc()).all()
    
    found_items = apply_filters(
        LostItem.query.filter_by(status='found')
    ).order_by(LostItem.created_at.desc()).all()
    
    # Debug: Print item counts to verify deletion
    print(f"DEBUG: Found {len(lost_items)} lost items and {len(found_items)} found items")
    # Apply filters to warehouse as well; cap to 6 only when no filters provided
    base_warehouse_q = apply_filters(
        LostItem.query.filter_by(status='warehouse')
    ).order_by(LostItem.created_at.desc())
    if any([item_name, location, keyword, dt_from, dt_to]):
        warehouse_items = base_warehouse_q.all()
    else:
        warehouse_items = base_warehouse_q.limit(6).all()
    
    # Attach parsed photo lists and user info for template consumption (non-persistent attribute)
    def attach_photos(items):
        for it in items:
            photos = []
            if it.photo_filenames:
                try:
                    data = json.loads(it.photo_filenames)
                    if isinstance(data, list):
                        photos = [p for p in data if isinstance(p, str)]
                except Exception:
                    photos = []
            elif it.photo_filename:
                photos = [it.photo_filename]
            it.photos = photos
            
            # Attach user information for report functionality and points/badges
            if it.reported_by:
                it.poster = db.session.get(User, it.reported_by)
                if it.poster:
                    it.poster.return_points = get_user_return_points(it.poster.id)
                    it.poster.badges = get_user_badges(it.poster.id)
            else:
                it.poster = None
        return items
    
    # --- Matching Suggestions (for the logged-in user's lost posts) ---
    suggestions = []
    try:
        current_user_id = session.get('user_id')
        if current_user_id:
            my_lost = [it for it in lost_items if it.reported_by == current_user_id]
            # Only compare against recent found items to keep it light
            recent_found = found_items[:50]

            def tokenize(text):
                text = (text or '').lower()
                text = re.sub(r"[^a-z0-9\s]", " ", text)
                return [t for t in text.split() if t]

            def score_match(a: LostItem, b: LostItem) -> float:
                a_tokens = set(tokenize(a.name) + tokenize(a.description) + tokenize(a.location))
                b_tokens = set(tokenize(b.name) + tokenize(b.description) + tokenize(b.location))
                if not a_tokens or not b_tokens:
                    return 0.0
                inter = len(a_tokens & b_tokens)
                union = len(a_tokens | b_tokens)
                jaccard = inter / union
                # Light weighting for value proximity when both provided
                value_bonus = 0.0
                if a.value is not None and b.value is not None:
                    try:
                        diff = abs(float(a.value) - float(b.value))
                        base = max(1.0, max(float(a.value), float(b.value)))
                        value_bonus = max(0.0, 0.2 - (diff / base))
                    except Exception:
                        value_bonus = 0.0
                # Location exact match small bump
                loc_bonus = 0.1 if (a.location and b.location and a.location.strip().lower() == b.location.strip().lower()) else 0.0
                return jaccard + value_bonus + loc_bonus

            def has_token_overlap(a: LostItem, b: LostItem) -> bool:
                a_tokens = set(tokenize(a.name) + tokenize(a.description) + tokenize(a.location))
                b_tokens = set(tokenize(b.name) + tokenize(b.description) + tokenize(b.location))
                return len(a_tokens & b_tokens) >= 1

            # Build scored pairs
            for my in my_lost:
                scored = [
                    (other, score_match(my, other))
                    for other in recent_found
                ]
                # Keep if score passes threshold OR there is at least one shared token
                scored = [s for s in scored if (s[1] >= 0.12) or has_token_overlap(my, s[0])]
                scored.sort(key=lambda x: x[1], reverse=True)
                top = [x[0] for x in scored[:5]]
                if top:
                    suggestions.append({
                        'lost': my,
                        'matches': top
                    })
    except Exception:
        suggestions = []

    return render_template("home.html", 
                         lost_items=attach_photos(lost_items), 
                         found_items=attach_photos(found_items), 
                         warehouse_items=attach_photos(warehouse_items),
                         match_suggestions=[
                             {
                                 'lost': {
                                     'id': s['lost'].id,
                                     'name': s['lost'].name,
                                     'description': s['lost'].description,
                                     'location': s['lost'].location,
                                     'photos': getattr(s['lost'], 'photos', [])
                                 },
                                 'matches': [
                                     {
                                         'id': m.id,
                                         'name': m.name,
                                         'description': m.description,
                                         'location': m.location,
                                         'photos': getattr(m, 'photos', [])
                                     } for m in s['matches']
                                 ]
                             } for s in suggestions
                         ],
                         q_item=item_name,
                         q_location=location,
                         q_keyword=keyword,
                         q_date_from=request.args.get('date_from', ''),
                         q_date_to=request.args.get('date_to', ''))

@app.route("/warehouse")
def warehouse():
    # Show only warehouse items in a dedicated tab/page
    items = LostItem.query.filter_by(status='warehouse').order_by(LostItem.created_at.desc()).all()

    def attach_photos_single(items_list):
        for it in items_list:
            photos = []
            if it.photo_filenames:
                try:
                    data = json.loads(it.photo_filenames)
                    if isinstance(data, list):
                        photos = [p for p in data if isinstance(p, str)]
                except Exception:
                    photos = []
            elif it.photo_filename:
                photos = [it.photo_filename]
            it.photos = photos
        return items_list

    return render_template('warehouse.html', warehouse_items=attach_photos_single(items))

# Create a Lost Item (POST)
@app.route("/add_product", methods=["POST"])
def add_lost_item():
    if 'user_id' not in session:
        flash('Please log in to report a lost item.', 'error')
        return redirect(url_for('login'))
    
    # Check if user is suspended from posting
    if not can_user_post(session['user_id']):
        flash('Your posting privileges have been suspended due to multiple reports. Please check your profile for details.', 'error')
        return redirect(url_for('home'))
    
    name = request.form.get("name")
    value = request.form.get("price")  # Keep 'price' for form compatibility
    description = request.form.get("description")
    
    # Handle optional multiple photo uploads
    photo_filenames_list = []
    files = []
    if 'item_photos' in request.files:
        files = request.files.getlist('item_photos')
    elif 'item_photo' in request.files:  # backward compat single input
        single = request.files.get('item_photo')
        files = [single] if single else []
    for file in files:
        if file and file.filename != '' and allowed_file(file.filename):
            original = secure_filename(file.filename)
            token = secrets.token_hex(8)
            reporter_id = session.get('user_id', 'anon')
            unique_name = f"user_{reporter_id}_{token}_{original}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
            file.save(file_path)
            photo_filenames_list.append(unique_name)

    new_item = LostItem(
        name=name, 
        value=value if value else None, 
        description=description,
        photo_filename=photo_filenames_list[0] if photo_filenames_list else None,
        photo_filenames=json.dumps(photo_filenames_list) if photo_filenames_list else None,
        reported_by=session.get('user_id') if 'user_id' in session else None,
        warehouse_deadline=calculate_warehouse_deadline()
    )
    db.session.add(new_item)
    db.session.commit()
    
    # Log item creation activity
    if 'user_id' in session and session.get('user_id'):
        log_activity(
            user_id=session['user_id'],
            action_type='create_lost_item',
            action_description=f'Created lost item: {new_item.name}',
            item_id=new_item.id,
            additional_data={
                'item_name': new_item.name,
                'item_value': new_item.value,
                'item_location': new_item.location,
                'photos_count': len(photo_filenames_list)
            }
        )
        
        reporter = db.session.get(User, session['user_id'])
        if reporter:
            send_item_submission_email(reporter, new_item, 'lost')
            # Create in-app notification
            create_notification(
                user_id=reporter.id,
                title="Lost item submitted",
                message=f"Your lost item '{new_item.name}' was submitted.",
                url=f"{url_for('home', _external=False)}#item-{new_item.id}"
            )
    
    # Notify potential finders whose found items may match this lost report
    try:
        recent_found = LostItem.query.filter_by(status='found').order_by(LostItem.created_at.desc()).limit(100).all()
        candidate_pairs = []
        for f in recent_found:
            score = _match_score(new_item, f)
            if (score >= 0.12) or _has_token_overlap(new_item, f):
                candidate_pairs.append((f, score))
        candidate_pairs.sort(key=lambda x: x[1], reverse=True)
        top_matches = [p[0] for p in candidate_pairs[:5]]
        for match in top_matches:
            if match.reported_by:
                try:
                    create_notification(
                        user_id=match.reported_by,
                        title='Potential match for your found item',
                        message=f"A new lost report '{new_item.name}' may match your found item '{match.name}'.",
                        url=f"{url_for('home', _external=False)}#item-{new_item.id}"
                    )
                except Exception:
                    pass
    except Exception:
        pass

    flash('Lost item reported successfully! Will be sent to warehouse in 150 hours if not claimed.')
    return redirect("/")

# Report Found Item (POST)
@app.route("/report_found_item", methods=["POST"])
def report_found_item():
    if 'user_id' not in session:
        flash('Please log in to report a found item.', 'error')
        return redirect(url_for('login'))
    
    # Check if user is suspended from posting
    if not can_user_post(session['user_id']):
        flash('Your posting privileges have been suspended due to multiple reports. Please check your profile for details.', 'error')
        return redirect(url_for('home'))
    
    name = request.form.get("name")
    value = request.form.get("value") or request.form.get("price")
    description = request.form.get("description")
    location = request.form.get("location")
    
    # Handle optional multiple photo uploads
    photo_filenames_list = []
    files = []
    if 'item_photos' in request.files:
        files = request.files.getlist('item_photos')
    elif 'item_photo' in request.files:  # backward compat single input
        single = request.files.get('item_photo')
        files = [single] if single else []
    for file in files:
        if file and file.filename != '' and allowed_file(file.filename):
            original = secure_filename(file.filename)
            token = secrets.token_hex(8)
            reporter_id = session.get('user_id', 'anon')
            unique_name = f"user_{reporter_id}_{token}_{original}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
            file.save(file_path)
            photo_filenames_list.append(unique_name)

    new_item = LostItem(
        name=name,
        value=value if value else None,
        description=description,
        location=location,
        photo_filename=photo_filenames_list[0] if photo_filenames_list else None,
        photo_filenames=json.dumps(photo_filenames_list) if photo_filenames_list else None,
        status='found',  # Mark as found immediately
        reported_by=session['user_id'],  # The person who found it
        warehouse_deadline=calculate_warehouse_deadline()
    )
    db.session.add(new_item)
    db.session.commit()
    
    # Log item creation activity
    log_activity(
        user_id=session['user_id'],
        action_type='create_found_item',
        action_description=f'Created found item: {new_item.name}',
        item_id=new_item.id,
        additional_data={
            'item_name': new_item.name,
            'item_value': new_item.value,
            'item_location': new_item.location,
            'photos_count': len(photo_filenames_list)
        }
    )
    
    # Notify owners of similar recent lost items
    try:
        recent_lost = LostItem.query.filter_by(status='lost').order_by(LostItem.created_at.desc()).limit(100).all()
        candidate_pairs = []
        for lost in recent_lost:
            score = _match_score(lost, new_item)
            if (score >= 0.12) or _has_token_overlap(lost, new_item):
                candidate_pairs.append((lost, score))
        candidate_pairs.sort(key=lambda x: x[1], reverse=True)
        top_matches = [p[0] for p in candidate_pairs[:5]]
        for match in top_matches:
            if match.reported_by:
                try:
                    create_notification(
                        user_id=match.reported_by,
                        title='Potential match for your lost item',
                        message=f"A new found item '{new_item.name}' may match your lost item '{match.name}'.",
                        url=f"{url_for('home', _external=False)}#item-{new_item.id}"
                    )
                except Exception:
                    pass
    except Exception:
        pass

    # Notify the reporter (finder)
    reporter = db.session.get(User, session['user_id'])
    if reporter:
        send_item_submission_email(reporter, new_item, 'found')
        # Create in-app notification
        create_notification(
            user_id=reporter.id,
            title="Found item submitted",
            message=f"Your found item '{new_item.name}' was submitted.",
            url=f"{url_for('home', _external=False)}#item-{new_item.id}"
        )
    
    flash('Found item reported successfully! The owner can now contact you. Will be sent to warehouse in 150 hours if not claimed.')
    return redirect("/")

# Read Lost Items (GET)
@app.route("/get_products", methods=["GET"])
def get_lost_items():
    items = db.session.execute(text("SELECT * FROM lost_item")).fetchall()
    return jsonify([dict(row._mapping) for row in items])

# Get Contact Information for Item (Lost or Found)
@app.route("/get_contact_info/<int:item_id>", methods=["GET"])
def get_contact_info(item_id):
    item = db.session.get(LostItem, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    # Get the owner's information (person who posted the item)
    owner = db.session.get(User, item.reported_by)
    if not owner:
        return jsonify({'error': 'Owner information not available'}), 404
    
    # Log contact info request activity
    if 'user_id' in session:
        log_activity(
            user_id=session['user_id'],
            action_type='request_contact_info',
            action_description=f'Requested contact info for item: {item.name}',
            item_id=item.id,
            additional_data={
                'item_name': item.name,
                'item_status': item.status,
                'owner_id': item.reported_by
            }
        )
    
    # Determine the type of contact information based on item status
    if item.status == 'found':
        # For found items, show finder's information
        contact_info = {
            'contact_name': f"{owner.first_name or 'Unknown'} {owner.last_name or ''}".strip() or owner.username,
            'phone': owner.phone or 'No phone number available',
            'email': owner.email,
            'item_name': item.name,
            'contact_type': 'finder',
            'message': 'This person found the item and can help you locate it.'
        }
    elif item.status == 'lost':
        # For lost items, show owner's information
        contact_info = {
            'contact_name': f"{owner.first_name or 'Unknown'} {owner.last_name or ''}".strip() or owner.username,
            'phone': owner.phone or 'No phone number available',
            'email': owner.email,
            'item_name': item.name,
            'contact_type': 'owner',
            'message': 'This person lost the item and is looking for it.'
        }
    else:
        return jsonify({'error': 'Item status not supported for contact information'}), 400
    
    return jsonify(contact_info), 200

# Get time remaining for warehouse deadline
@app.route("/get_time_remaining/<int:item_id>", methods=["GET"])
def get_time_remaining(item_id):
    item = db.session.get(LostItem, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    time_remaining = format_time_remaining(item.warehouse_deadline)
    created_at = item.created_at.strftime('%Y-%m-%d %H:%M:%S') if item.created_at else None
    
    return jsonify({
        'time_remaining': time_remaining,
        'created_at': created_at,
        'warehouse_deadline': item.warehouse_deadline.isoformat() if item.warehouse_deadline else None
    }), 200

# Generate a printable poster PDF for an item
@app.route('/poster/<int:item_id>', methods=['GET'])
def generate_poster(item_id):
    # Fresh import to ensure we're using the active interpreter's ReportLab
    try:
        from reportlab.pdfgen import canvas as _canvas
        from reportlab.lib.pagesizes import A4 as _A4
        from reportlab.lib.units import inch as _inch
    except Exception as import_err:
        try:
            import sys
            exe = sys.executable
        except Exception:
            exe = 'unknown'
        return jsonify({'error': f'PDF generation library not available. Please install reportlab. Details: {import_err}. Python: {exe}'}), 500

    item = db.session.get(LostItem, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    # Log PDF generation activity
    if 'user_id' in session:
        log_activity(
            user_id=session['user_id'],
            action_type='generate_poster',
            action_description=f'Generated PDF poster for item: {item.name}',
            item_id=item.id,
            additional_data={
                'item_name': item.name,
                'item_status': item.status
            }
        )

    buffer = BytesIO()
    page_width, page_height = _A4
    c = _canvas.Canvas(buffer, pagesize=_A4)

    margin = 50
    y = page_height - margin

    # Header
    c.setFillColorRGB(0, 0.2, 0.6)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(margin, y, "BRACU Lost & Found Poster")
    y -= 20
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 12)
    c.drawString(margin, y, datetime.now().strftime('%Y-%m-%d %H:%M'))
    y -= 30

    # Item title and status badge
    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, y, f"{item.name or 'Unnamed Item'}")
    status_text = item.status.capitalize() if item.status else 'Unknown'
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.8, 0.5, 0) if status_text == 'Lost' else c.setFillColorRGB(0.2, 0.6, 0.2)
    c.drawString(margin, y - 18, f"Status: {status_text}")
    c.setFillColorRGB(0, 0, 0)
    y -= 40

    # Details
    c.setFont("Helvetica", 12)
    if item.value:
        c.drawString(margin, y, f"Estimated Value: {item.value}")
        y -= 18
    if item.location:
        c.drawString(margin, y, f"Location: {item.location}")
        y -= 18
    if item.created_at:
        c.drawString(margin, y, f"Posted: {item.created_at.strftime('%Y-%m-%d %H:%M')}")
        y -= 18

    # Description block (wrap manually)
    c.setFont("Helvetica", 12)
    desc = item.description or ''
    max_width = page_width - margin * 2
    def wrap_text(text, font_name, font_size, max_w):
        c.setFont(font_name, font_size)
        words = text.split()
        lines = []
        line = ''
        for w in words:
            test = f"{line} {w}".strip()
            if c.stringWidth(test, font_name, font_size) <= max_w:
                line = test
            else:
                if line:
                    lines.append(line)
                line = w
        if line:
            lines.append(line)
        return lines

    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, "Description:")
    y -= 18
    c.setFont("Helvetica", 12)
    for line in wrap_text(desc, "Helvetica", 12, max_width):
        c.drawString(margin, y, line)
        y -= 16

    y -= 10

    # Photos section (embed up to 3 images, scaled to fit)
    try:
        photos = []
        if item.photo_filenames:
            try:
                data = json.loads(item.photo_filenames)
                if isinstance(data, list):
                    photos = [p for p in data if isinstance(p, str)]
            except Exception:
                photos = []
        elif item.photo_filename:
            photos = [item.photo_filename]

        if photos:
            c.setFont("Helvetica-Bold", 14)
            c.drawString(margin, y, "Photos:")
            y -= 18
            from reportlab.lib.utils import ImageReader
            max_image_width = page_width - 2 * margin
            max_image_height = 3 * _inch
            for idx, photo in enumerate(photos[:3]):
                absolute_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], photo)
                if not os.path.exists(absolute_path):
                    continue
                try:
                    img_reader = ImageReader(absolute_path)
                    img_w, img_h = img_reader.getSize()
                    scale = min(max_image_width / float(img_w), max_image_height / float(img_h))
                    draw_w = float(img_w) * scale
                    draw_h = float(img_h) * scale
                    # New page if not enough space
                    if y - draw_h < margin + 60:
                        c.showPage()
                        y = page_height - margin
                        c.setFont("Helvetica-Bold", 14)
                        c.drawString(margin, y, "Photos (cont.):")
                        y -= 18
                    x = margin + (max_image_width - draw_w) / 2.0
                    c.drawImage(img_reader, x, y - draw_h, width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
                    y -= draw_h + 12
                except Exception as ie:
                    print(f"Failed to embed image '{photo}': {ie}")
    except Exception as e:
        print(f"Photos section failed: {e}")

    # QR code linking back to the item anchor on the portal
    try:
        from reportlab.graphics.barcode import qr as rl_qr
        from reportlab.graphics import renderPDF as rl_renderPDF
        item_url = url_for('home', _external=True) + f"#item-{item.id}"
        code = rl_qr.QrCodeWidget(item_url)
        bounds = code.getBounds()
        size = 150
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        scale_x = float(size) / float(width)
        scale_y = float(size) / float(height)
        from reportlab.graphics.shapes import Drawing
        d = Drawing(size, size, transform=[scale_x, 0, 0, scale_y, 0, 0])
        d.add(code)
        rl_renderPDF.draw(d, c, page_width - margin - size, margin)
        c.setFont("Helvetica", 10)
        c.drawString(page_width - margin - size, margin + size + 6, "Scan to view online")
    except Exception as e:
        print(f"QR generation failed: {e}")

    # Footer
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(margin, margin, "Generated by BRACU Lost & Found Portal")

    c.showPage()
    c.save()
    pdf = buffer.getvalue()
    buffer.close()

    filename = f"poster_item_{item.id}.pdf"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(pdf, mimetype='application/pdf', headers=headers)

# ---------------- Notification APIs ----------------
@app.route('/notifications', methods=['GET'])
def get_notifications():
    if 'user_id' not in session:
        return jsonify({'notifications': [], 'unread_count': 0})
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(20).all()
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'url': n.url,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S') if n.created_at else None
            } for n in notifications
        ],
        'unread_count': unread_count
    })

@app.route('/notifications/mark_read', methods=['POST'])
def mark_notifications_read():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    user_id = session['user_id']
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@app.route('/notifications/all', methods=['GET'])
def view_all_notifications():
    if 'user_id' not in session:
        flash('Please log in to view notifications.')
        return redirect(url_for('login'))
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    return render_template('all_notifications.html', notifications=notifications)

# ---------------- Chat APIs ----------------
def require_login_json():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    return None

@app.route('/chat', methods=['GET'])
def chat_home():
    if 'user_id' not in session:
        flash('Please log in to access chats.')
        return redirect(url_for('login'))
    
    # Check if user is suspended from chatting
    me = session['user_id']
    if not can_user_chat(me):
        # Get specific suspension details for better error message
        chat_suspension = UserSuspension.query.filter_by(
            user_id=me,
            suspension_type='chat_ban',
            is_active=True
        ).filter(UserSuspension.end_date > datetime.now()).first()
        
        if chat_suspension:
            remaining_time = chat_suspension.end_date - datetime.now()
            days = remaining_time.days
            hours = remaining_time.seconds // 3600
            time_str = f"{days}d {hours}h" if days > 0 else f"{hours}h"
            
            flash(f'Your chat has been disabled for {time_str} due to multiple reports. You can still post items but cannot send messages.', 'warning')
        else:
            flash('Your chat privileges have been suspended. Please check your profile for details.', 'warning')
    
    return render_template('chat.html')

@app.route('/api/chat/start/<int:other_user_id>', methods=['POST'])
def start_conversation(other_user_id):
    auth = require_login_json()
    if auth:
        return auth
    me = session['user_id']
    if other_user_id == me:
        return jsonify({'error': 'Cannot start conversation with yourself'}), 400
    other = db.session.get(User, other_user_id)
    if not other:
        return jsonify({'error': 'User not found'}), 404
    convo = Conversation.get_or_create_between(me, other_user_id)
    return jsonify({'conversation_id': convo.id}), 200

@app.route('/api/chat/conversations', methods=['GET'])
def list_conversations():
    auth = require_login_json()
    if auth:
        return auth
    me = session['user_id']
    convos = Conversation.query.filter(
        (Conversation.user_a_id == me) | (Conversation.user_b_id == me)
    ).order_by(Conversation.created_at.desc()).all()

    def other_user_for(c: Conversation):
        other_id = c.user_b_id if c.user_a_id == me else c.user_a_id
        other = db.session.get(User, other_id)
        return {
            'id': other.id,
            'username': other.username,
            'first_name': other.first_name,
            'last_name': other.last_name,
            'profile_photo': other.profile_photo,
        } if other else None

    data = [
        {
            'id': c.id,
            'created_at': c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else None,
            'other_user': other_user_for(c)
        } for c in convos
    ]
    return jsonify({'conversations': data})

@app.route('/api/chat/<int:conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    auth = require_login_json()
    if auth:
        return auth
    me = session['user_id']
    convo = db.session.get(Conversation, conversation_id)
    if not convo or not convo.has_participant(me):
        return jsonify({'error': 'Conversation not found'}), 404

    since_id = request.args.get('since_id', type=int)
    limit = request.args.get('limit', default=50, type=int)
    q = Message.query.filter_by(conversation_id=conversation_id)
    if since_id:
        q = q.filter(Message.id > since_id)
    msgs = q.order_by(Message.id.asc()).limit(max(1, min(200, limit))).all()
    payload = []
    for m in msgs:
        item = {
            'id': m.id,
            'sender_id': m.sender_id,
            'content': m.content,
            'created_at': m.created_at.strftime('%Y-%m-%d %H:%M:%S') if m.created_at else None
        }
        if getattr(m, 'attachment', None):
            item['attachment'] = url_for('static', filename=f'uploads/{m.attachment}', _external=False)
        payload.append(item)
    return jsonify({'messages': payload})

@app.route('/api/chat/<int:conversation_id>/messages', methods=['POST'])
def send_message(conversation_id):
    auth = require_login_json()
    if auth:
        return auth
    me = session['user_id']
    
    # Check if user is suspended from chatting
    if not can_user_chat(me):
        # Get specific suspension details for better error message
        chat_suspension = UserSuspension.query.filter_by(
            user_id=me,
            suspension_type='chat_ban',
            is_active=True
        ).filter(UserSuspension.end_date > datetime.now()).first()
        
        if chat_suspension:
            remaining_time = chat_suspension.end_date - datetime.now()
            days = remaining_time.days
            hours = remaining_time.seconds // 3600
            time_str = f"{days}d {hours}h" if days > 0 else f"{hours}h"
            return jsonify({
                'error': f'Your chat has been disabled for {time_str} due to multiple reports. You can still post items but cannot send messages.',
                'suspension_type': 'chat_ban',
                'remaining_time': time_str
            }), 403
        else:
            return jsonify({'error': 'Your chat privileges have been suspended. Please check your profile for details.'}), 403
    
    convo = db.session.get(Conversation, conversation_id)
    if not convo or not convo.has_participant(me):
        return jsonify({'error': 'Conversation not found'}), 404
    # Accept JSON for text messages and multipart/form for attachments
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        content = (request.form.get('content') or '').strip()
        file = request.files.get('file')
        saved_filename = None
        if file and file.filename:
            if not allowed_file(file.filename):
                return jsonify({'error': 'File type not allowed'}), 400
            base = secure_filename(file.filename)
            unique = f"user_{session['user_id']}_{secrets.token_hex(8)}_{base}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique)
            file.save(save_path)
            saved_filename = unique
        if not content and not saved_filename:
            return jsonify({'error': 'Message content or file required'}), 400
        msg = Message(conversation_id=conversation_id, sender_id=me, content=content or '', attachment=saved_filename)
    else:
        data = request.get_json(silent=True) or {}
        content = (data.get('content') or '').strip()
        if not content:
            return jsonify({'error': 'Message content required'}), 400
        msg = Message(conversation_id=conversation_id, sender_id=me, content=content)
    db.session.add(msg)
    db.session.commit()

    # Log chat message activity
    log_activity(
        user_id=me,
        action_type='send_message',
        action_description=f'Sent message in conversation {conversation_id}',
        additional_data={
            'conversation_id': conversation_id,
            'message_length': len(content),
            'has_attachment': bool(saved_filename),
            'other_user_id': convo.user_b_id if convo.user_a_id == me else convo.user_a_id
        }
    )

    # Create a lightweight notification for the other participant
    other_id = convo.user_b_id if convo.user_a_id == me else convo.user_a_id
    try:
        create_notification(
            user_id=other_id,
            title='New message',
            message=content[:120] + ('…' if len(content) > 120 else ''),
            url=url_for('chat_home', _external=False)
        )
    except Exception:
        pass

    resp = {'id': msg.id}
    if getattr(msg, 'attachment', None):
        resp['attachment'] = url_for('static', filename=f'uploads/{msg.attachment}', _external=False)
    return jsonify(resp), 201

@app.route('/api/chat/start_from_item/<int:item_id>', methods=['POST'])
def start_chat_from_item(item_id):
    auth = require_login_json()
    if auth:
        return auth
    me = session['user_id']
    item = db.session.get(LostItem, item_id)
    if not item or not item.reported_by:
        return jsonify({'error': 'Item not found or has no reporter'}), 404
    other_user_id = item.reported_by
    if other_user_id == me:
        return jsonify({'error': 'Cannot start chat with yourself'}), 400
    convo = Conversation.get_or_create_between(me, other_user_id)
    return jsonify({'conversation_id': convo.id}), 200

@app.route('/api/chat/status', methods=['GET'])
def get_chat_status():
    """Check if user's chat is enabled or disabled"""
    auth = require_login_json()
    if auth:
        return auth
    me = session['user_id']
    
    # Check for active chat suspension
    chat_suspension = UserSuspension.query.filter_by(
        user_id=me,
        suspension_type='chat_ban',
        is_active=True
    ).filter(UserSuspension.end_date > datetime.now()).first()
    
    if chat_suspension:
        remaining_time = chat_suspension.end_date - datetime.now()
        days = remaining_time.days
        hours = remaining_time.seconds // 3600
        time_str = f"{days}d {hours}h" if days > 0 else f"{hours}h"
        
        return jsonify({
            'chat_enabled': False,
            'suspension_type': 'chat_ban',
            'reason': chat_suspension.reason,
            'remaining_time': time_str,
            'end_date': chat_suspension.end_date.isoformat(),
            'message': f'Your chat has been disabled for {time_str} due to multiple reports.'
        }), 200
    else:
        return jsonify({
            'chat_enabled': True,
            'message': 'Chat is enabled'
        }), 200

# Update a Lost/Found Item (edit by owner)
@app.route("/edit_item/<int:item_id>", methods=["POST"])
def edit_item(item_id):
    if 'user_id' not in session:
        flash('Please log in to edit items.')
        return redirect(url_for('login'))

    item = db.session.get(LostItem, item_id)
    if not item:
        flash('Item not found.')
        return redirect(url_for('home'))

    # Ownership check
    if item.reported_by != session['user_id']:
        flash('You can only edit items that you posted.')
        return redirect(url_for('home'))

    # Update editable fields
    item.name = request.form.get("name", item.name)
    # Keep supporting both 'price' and 'value' keys from form
    new_value = request.form.get("price", request.form.get("value"))
    if new_value is not None and new_value != "":
        item.value = new_value
    item.description = request.form.get("description", item.description)
    # Optional: update location only for found items (if provided)
    loc = request.form.get("location")
    if loc is not None and loc != "":
        item.location = loc

    # Handle optional photo uploads during edit (append to gallery)
    try:
        photo_filenames_list = []
        if 'item_photos' in request.files:
            files = request.files.getlist('item_photos')
            for file in files:
                if file and file.filename != '' and allowed_file(file.filename):
                    original = secure_filename(file.filename)
                    token = secrets.token_hex(8)
                    reporter_id = session.get('user_id', 'anon')
                    unique_name = f"user_{reporter_id}_{token}_{original}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
                    file.save(file_path)
                    photo_filenames_list.append(unique_name)
        # Merge newly uploaded photos with existing ones
        existing = []
        if item.photo_filenames:
            try:
                existing = json.loads(item.photo_filenames)
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        combined = existing + photo_filenames_list
        if combined:
            item.photo_filenames = json.dumps(combined)
            item.photo_filename = combined[0]
    except Exception as e:
        print(f"Photo update skipped on edit: {e}")

    db.session.commit()
    
    # Log item edit activity
    log_activity(
        user_id=session['user_id'],
        action_type='edit_item',
        action_description=f'Edited item: {item.name}',
        item_id=item.id,
        additional_data={
            'item_name': item.name,
            'item_value': item.value,
            'item_location': item.location,
            'item_status': item.status
        }
    )
    
    flash('Item updated successfully!')
    return redirect(url_for('home'))

# Mark Item as Found (API route - just changes status)
@app.route("/api/mark_found/<int:item_id>", methods=["POST"])
def mark_item_found(item_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    item = db.session.get(LostItem, item_id)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    # Check if the current user is the one who posted the item
    if item.reported_by != session['user_id']:
        return jsonify({'error': 'You can only mark items as found that you posted'}), 403
    
    # Update the item status to 'found'
    previous_status = item.status
    item.status = 'found'
    db.session.commit()
    
    # Log status change activity
    log_activity(
        user_id=session['user_id'],
        action_type='status_change',
        action_description=f'Changed item status: {item.name} from {previous_status} to found',
        item_id=item.id,
        additional_data={
            'item_name': item.name,
            'previous_status': previous_status,
            'new_status': 'found'
        }
    )
    
    # Notify the reporter
    if item.reported_by:
        reporter = db.session.get(User, item.reported_by)
        if reporter:
            send_item_status_update_email(reporter, item, previous_status, 'found')
            create_notification(
                user_id=reporter.id,
                title="Item status updated",
                message=f"Your item '{item.name}' status changed from {previous_status} to found.",
                url=f"{url_for('home', _external=False)}#item-{item.id}"
            )

    return jsonify({
        'message': 'Item marked as found successfully',
        'item_id': item_id,
        'status': 'found'
    }), 200

# Soft-delete a Lost Item (POST)
@app.route("/delete_product/<int:product_id>", methods=["POST"])
def delete_lost_item(product_id):
    if 'user_id' not in session:
        flash('Please log in to remove items.')
        return redirect(url_for('login'))

    item = db.session.get(LostItem, product_id)
    if not item:
        flash('Item not found.')
        return redirect("/")

    if item.reported_by != session['user_id']:
        flash('You can only remove items that you posted.')
        return redirect("/")

    previous_status = item.status
    item.status = 'deleted'
    db.session.commit()

    # Log item deletion activity
    log_activity(
        user_id=session['user_id'],
        action_type='delete_item',
        action_description=f'Deleted item: {item.name} (previous status: {previous_status})',
        item_id=item.id,
        additional_data={
            'item_name': item.name,
            'previous_status': previous_status,
            'new_status': 'deleted'
        }
    )

    # Build undo URLs (relative for in-app, absolute for email)
    undo_url_rel = url_for('undo_delete_item', item_id=item.id, _external=False)
    undo_url_abs = url_for('undo_delete_item', item_id=item.id, _external=True)

    # In-app notification
    create_notification(
        user_id=session['user_id'],
        title="Item removed",
        message=f"Your item '{item.name}' was removed. Click to undo.",
        url=undo_url_rel
    )

    # Email notification
    reporter = db.session.get(User, session['user_id'])
    if reporter:
        send_item_deleted_email(reporter, item, previous_status, undo_url=undo_url_abs)

    # Store pending undo prompt in session for banner
    session['pending_undo'] = {
        'item_id': item.id,
        'name': item.name
    }

    flash('Item removed. You can undo this action from the banner or notification.')
    return redirect("/")

@app.route('/undo_delete/<int:item_id>', methods=['GET'])
def undo_delete_item(item_id):
    if 'user_id' not in session:
        flash('Please log in to undo removal.')
        return redirect(url_for('login'))

    item = db.session.get(LostItem, item_id)
    if not item:
        flash('Item not found.')
        return redirect(url_for('home'))

    if item.reported_by != session['user_id']:
        flash('You can only undo items that you posted.')
        return redirect(url_for('home'))

    if item.status != 'deleted':
        flash('This item is not deleted or has already been restored.')
        return redirect(url_for('home'))

    # Restore to a sensible status based on its history: if it had a location it's likely found
    restored_status = 'found' if item.location else 'lost'
    item.status = restored_status
    db.session.commit()

    # Log item restoration activity
    log_activity(
        user_id=session['user_id'],
        action_type='restore_item',
        action_description=f'Restored item: {item.name} to status: {restored_status}',
        item_id=item.id,
        additional_data={
            'item_name': item.name,
            'restored_status': restored_status,
            'previous_status': 'deleted'
        }
    )

    # Clear pending undo if it matches
    if session.get('pending_undo') and session['pending_undo'].get('item_id') == item.id:
        session.pop('pending_undo', None)

    # Remove the prior "Item removed" notification tied to this undo link
    try:
        prior_undo_url = url_for('undo_delete_item', item_id=item.id, _external=False)
        stale_notifications = Notification.query.filter_by(
            user_id=session['user_id'],
            title='Item removed',
            url=prior_undo_url
        ).all()
        for n in stale_notifications:
            db.session.delete(n)
        if stale_notifications:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error removing stale removal notification: {e}")

    # Notify via in-app and email about restoration
    create_notification(
        user_id=session['user_id'],
        title="Item restored",
        message=f"Your item '{item.name}' has been restored to '{restored_status}'.",
        url=f"{url_for('home', _external=False)}#item-{item.id}"
    )

    reporter = db.session.get(User, session['user_id'])
    if reporter:
        send_item_status_update_email(reporter, item, 'deleted', restored_status)

    flash('Item restored successfully!')
    return redirect(url_for('home'))

@app.route('/dismiss_undo', methods=['GET'])
def dismiss_undo():
    try:
        pending = session.get('pending_undo')
        if pending and 'item_id' in pending:
            rel_url = url_for('undo_delete_item', item_id=pending['item_id'], _external=False)
            stale_notifications = Notification.query.filter_by(
                user_id=session.get('user_id'),
                title='Item removed',
                url=rel_url
            ).all()
            for n in stale_notifications:
                db.session.delete(n)
            if stale_notifications:
                db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error removing stale removal notification on dismiss: {e}")
    session.pop('pending_undo', None)
    return redirect(url_for('home'))

# ------------ Auth Routes ------------

@app.route('/verify_profile_update', methods=['GET', 'POST'])
def verify_profile_update():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('User not found.')
        return redirect(url_for('login'))

    if 'pending_profile_update' not in session:
        flash('No pending profile changes found.')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        code = request.form.get('verification_code', '')
        verification = EmailVerification.query.filter_by(
            email=user.email,
            verification_code=code,
            is_used=False
        ).first()
        if verification and verification.expires_at > datetime.now():
            verification.is_used = True
            pending = session.pop('pending_profile_update', {})
            # Apply staged changes
            user.first_name = pending.get('first_name', user.first_name)
            user.last_name = pending.get('last_name', user.last_name)
            user.phone = pending.get('phone', user.phone)
            user.address = pending.get('address', user.address)
            filename = pending.get('profile_photo_filename')
            if filename:
                user.profile_photo = filename
            db.session.commit()
            
            # Log profile update activity
            log_activity(
                user_id=user.id,
                action_type='profile_update',
                action_description=f'Updated profile information',
                additional_data={
                    'updated_fields': list(pending.keys()),
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'has_phone': bool(user.phone),
                    'has_address': bool(user.address),
                    'has_profile_photo': bool(user.profile_photo)
                }
            )
            
            # Update session
            session['first_name'] = user.first_name
            session['last_name'] = user.last_name
            session['profile_photo'] = user.profile_photo
            flash('Profile updated successfully!')
            return redirect(url_for('profile'))
        else:
            flash('Invalid or expired verification code!')

    return render_template('verify_profile_update.html')

@app.route('/resend_profile_update_verification', methods=['POST'])
def resend_profile_update_verification():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('login'))
    if 'pending_profile_update' not in session:
        flash('No pending profile changes to verify.')
        return redirect(url_for('profile'))
    clean_expired_codes()
    code = generate_verification_code()
    print(f"=== GENERATED PROFILE UPDATE VERIFY CODE (RESEND): {code} for {user.email} ===")
    expires_at = datetime.now() + timedelta(minutes=10)
    verification = EmailVerification(
        email=user.email,
        verification_code=code,
        expires_at=expires_at
    )
    db.session.add(verification)
    db.session.commit()
    send_profile_update_verification_email(user.email, code)
    flash('Verification code re-sent to your email.')
    return redirect(url_for('verify_profile_update'))
 
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        student_faculty_id = request.form['student_faculty_id']
        
        # Validate student/faculty ID (8 digits)
        if not student_faculty_id.isdigit() or len(student_faculty_id) != 8:
            flash('Student/Faculty ID must be exactly 8 digits!')
            return redirect(url_for('signup'))
        
        # Check if username, email, or student/faculty ID already exists
        if db.session.query(User).filter_by(username=username).first():
            flash('Username already exists!')
            return redirect(url_for('signup'))
        
        if db.session.query(User).filter_by(email=email).first():
            flash('Email already exists!')
            return redirect(url_for('signup'))
        
        if db.session.query(User).filter_by(student_faculty_id=student_faculty_id).first():
            flash('Student/Faculty ID already exists!')
            return redirect(url_for('signup'))
        
        # Start email verification flow instead of creating user immediately
        clean_expired_codes()
        verification_code = generate_verification_code()
        print(f"=== GENERATED VERIFICATION CODE: {verification_code} for {email} ===")
        expires_at = datetime.now() + timedelta(minutes=10)
        verification = EmailVerification(
            email=email,
            verification_code=verification_code,
            expires_at=expires_at
        )
        db.session.add(verification)
        db.session.commit()

        if send_verification_email(email, verification_code):
            session['pending_signup'] = {
                'username': username,
                'email': email,
                'password': password,
                'student_faculty_id': student_faculty_id
            }
            flash('Verification code sent to your email! Please check your inbox.')
            return redirect(url_for('verify_signup'))
        else:
            flash('Failed to send verification email. Please try again.')
            return redirect(url_for('signup'))
    
    return render_template('signup.html')

@app.route('/verify_signup', methods=['GET', 'POST'])
def verify_signup():
    if 'pending_signup' not in session:
        flash('No pending signup found. Please sign up again.')
        return redirect(url_for('signup'))
    
    if request.method == 'POST':
        verification_code = request.form['verification_code']
        email = session['pending_signup']['email']
        
        verification = EmailVerification.query.filter_by(
            email=email,
            verification_code=verification_code,
            is_used=False
        ).first()
        
        if verification and verification.expires_at > datetime.now():
            verification.is_used = True
            signup_data = session['pending_signup']
            hashed_password = generate_password_hash(signup_data['password'])
            new_user = User(
                username=signup_data['username'],
                email=signup_data['email'],
                password=hashed_password,
                student_faculty_id=signup_data['student_faculty_id'],
                email_verified=True
            )
            db.session.add(new_user)
            db.session.commit()
            
            # Log user registration activity
            log_activity(
                user_id=new_user.id,
                action_type='user_registration',
                action_description=f'New user registered: {new_user.username} ({new_user.email})',
                additional_data={
                    'username': new_user.username,
                    'email': new_user.email,
                    'student_faculty_id': new_user.student_faculty_id
                }
            )
            
            session.pop('pending_signup', None)
            flash('Account created successfully! Please log in.')
            return redirect(url_for('login'))
        else:
            flash('Invalid or expired verification code!')
    
    return render_template('verify_signup.html')

@app.route('/resend_verification', methods=['POST'])
def resend_verification():
    if 'pending_signup' not in session:
        flash('No pending signup found.')
        return redirect(url_for('signup'))
    
    email = session['pending_signup']['email']
    clean_expired_codes()
    verification_code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=10)
    verification = EmailVerification(
        email=email,
        verification_code=verification_code,
        expires_at=expires_at
    )
    db.session.add(verification)
    db.session.commit()
    
    if send_verification_email(email, verification_code):
        flash('New verification code sent to your email!')
    else:
        flash('Failed to send verification email. Please try again.')
    
    return redirect(url_for('verify_signup'))

@app.route('/resend_password_reset_verification', methods=['POST'])
def resend_password_reset_verification():
    if 'pending_password_reset' not in session:
        flash('No pending password reset found.')
        return redirect(url_for('forgot_password'))
    
    email = session['pending_password_reset']['email']
    clean_expired_codes()
    verification_code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=10)
    verification = EmailVerification(
        email=email,
        verification_code=verification_code,
        expires_at=expires_at
    )
    db.session.add(verification)
    db.session.commit()
    
    if send_password_reset_verification_email(email, verification_code):
        flash('New verification code sent to your email!')
    else:
        flash('Failed to send verification email. Please try again.')
    
    return redirect(url_for('verify_password_reset'))

@app.route('/change_email', methods=['GET', 'POST'])
def change_email():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('User not found.')
        return redirect(url_for('login'))

    # Send code both for initial GET (when clicking Change) and POST (resend)
    should_send = request.method in ('GET', 'POST')

    # Basic throttle: 60 seconds between sends
    try:
        last_ts = float(session.get('identity_code_sent_ts', '0'))
    except Exception:
        last_ts = 0.0
    now_ts = datetime.now().timestamp()
    if should_send and now_ts - last_ts < 60:
        flash('Please wait a moment before requesting another code.')
        return redirect(url_for('verify_change_email'))

    if should_send:
        clean_expired_codes()
        verification_code = generate_verification_code()
        print(f"=== GENERATED IDENTITY VERIFY CODE: {verification_code} for {user.email} ===")
        expires_at = datetime.now() + timedelta(minutes=10)
        verification = EmailVerification(
            email=user.email,
            verification_code=verification_code,
            expires_at=expires_at
        )
        db.session.add(verification)
        db.session.commit()
        session['identity_code_sent_ts'] = str(now_ts)
        if send_identity_verification_email(user.email, verification_code):
            flash('Verification code sent to your current email.')
        else:
            flash('Failed to send verification code.')
        return redirect(url_for('verify_change_email'))

    return render_template('verify_email_change.html')

@app.route('/verify_change_email', methods=['GET', 'POST'])
def verify_change_email():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('User not found.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        code = request.form.get('verification_code', '')
        verification = EmailVerification.query.filter_by(
            email=user.email,
            verification_code=code,
            is_used=False
        ).first()
        if verification and verification.expires_at > datetime.now():
            verification.is_used = True
            db.session.commit()
            session['identity_verified_at'] = datetime.now().isoformat()
            return redirect(url_for('enter_new_email'))
        else:
            flash('Invalid or expired code!')

    return render_template('verify_email_change.html')

@app.route('/enter_new_email', methods=['GET', 'POST'])
def enter_new_email():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('User not found.')
        return redirect(url_for('login'))
    # Require prior identity verification in the session
    if not session.get('identity_verified_at'):
        flash('Please verify your identity first.')
        return redirect(url_for('change_email'))

    if request.method == 'POST':
        new_email = request.form.get('email', '').strip().lower()
        if not new_email:
            flash('Please enter your new email.')
            return redirect(url_for('enter_new_email'))
        if db.session.query(User).filter(User.email == new_email, User.id != user.id).first():
            flash('Email already in use by another account.')
            return redirect(url_for('enter_new_email'))
        # Send code to new email
        clean_expired_codes()
        verification_code = generate_verification_code()
        print(f"=== GENERATED NEW EMAIL VERIFY CODE: {verification_code} for {new_email} ===")
        expires_at = datetime.now() + timedelta(minutes=10)
        verification = EmailVerification(
            email=new_email,
            verification_code=verification_code,
            expires_at=expires_at
        )
        db.session.add(verification)
        db.session.commit()
        if send_new_email_verification(new_email, verification_code):
            session['pending_email_change'] = {'new_email': new_email}
            flash('Verification code sent to your new email.')
            return redirect(url_for('confirm_new_email'))
        else:
            flash('Failed to send verification to new email.')

    return render_template('enter_new_email.html')

@app.route('/confirm_new_email', methods=['GET', 'POST'])
def confirm_new_email():
    if 'user_id' not in session:
        flash('Please log in to continue.')
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('User not found.')
        return redirect(url_for('login'))
    if 'pending_email_change' not in session:
        flash('No pending email change found.')
        return redirect(url_for('enter_new_email'))

    pending = session['pending_email_change']
    new_email = pending.get('new_email')

    if request.method == 'POST':
        code = request.form.get('verification_code', '')
        verification = EmailVerification.query.filter_by(
            email=new_email,
            verification_code=code,
            is_used=False
        ).first()
        if verification and verification.expires_at > datetime.now():
            verification.is_used = True
            user.email = new_email
            user.email_verified = True
            db.session.commit()
            
            # Log email change activity
            log_activity(
                user_id=user.id,
                action_type='email_change',
                action_description=f'Email changed to: {new_email}',
                additional_data={
                    'username': user.username,
                    'old_email': user.email,  # This will be the new email since we already updated it
                    'new_email': new_email
                }
            )
            
            session.pop('pending_email_change', None)
            session.pop('identity_verified_at', None)
            flash('Email updated successfully!')
            return redirect(url_for('profile'))
        else:
            flash('Invalid or expired code!')

    return render_template('confirm_new_email.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to home
    if 'user_id' in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = db.session.query(User).filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            # Clear any existing session data
            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['first_name'] = user.first_name
            session['last_name'] = user.last_name
            session['profile_photo'] = user.profile_photo
            
            # Log successful login
            log_activity(
                user_id=user.id,
                action_type='login',
                action_description=f'User {user.username} logged in successfully'
            )
            
            flash('Logged in successfully!')
            return redirect(url_for('home'))
        else:
            # Log failed login attempt
            log_activity(
                user_id=None,
                action_type='login_failed',
                action_description=f'Failed login attempt for email: {email}'
            )
            flash('Invalid email or password!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Log logout activity before clearing session
    if 'user_id' in session:
        log_activity(
            user_id=session['user_id'],
            action_type='logout',
            action_description=f'User {session.get("username", "Unknown")} logged out'
        )
    
    session.clear()
    flash('Logged out successfully!')
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = db.session.query(User).filter_by(email=email).first()
        if user:
            # Start password reset verification flow
            clean_expired_codes()
            verification_code = generate_verification_code()
            print(f"=== GENERATED PASSWORD RESET VERIFICATION CODE: {verification_code} for {email} ===")
            expires_at = datetime.now() + timedelta(minutes=10)
            verification = EmailVerification(
                email=email,
                verification_code=verification_code,
                expires_at=expires_at
            )
            db.session.add(verification)
            db.session.commit()

            if send_password_reset_verification_email(email, verification_code):
                session['pending_password_reset'] = {
                    'email': email
                }
                flash('Verification code sent to your email! Please check your inbox.')
                return redirect(url_for('verify_password_reset'))
            else:
                flash('Failed to send verification email. Please try again.')
                return redirect(url_for('forgot_password'))
        else:
            flash('Email not found!')
    return render_template('forgot_password.html')

@app.route('/verify_password_reset', methods=['GET', 'POST'])
def verify_password_reset():
    if 'pending_password_reset' not in session:
        flash('No pending password reset found. Please request a new one.')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        verification_code = request.form['verification_code']
        email = session['pending_password_reset']['email']
        
        verification = EmailVerification.query.filter_by(
            email=email,
            verification_code=verification_code,
            is_used=False
        ).first()
        
        if verification and verification.expires_at > datetime.now():
            verification.is_used = True
            # Store email for final password reset step
            session['verified_reset_email'] = session['pending_password_reset']['email']
            session.pop('pending_password_reset', None)
            flash('Verification code verified. Please enter your new password.')
            return redirect(url_for('reset_password_with_code'))
        else:
            flash('Invalid or expired verification code!')
    
    return render_template('verify_password_reset.html')

@app.route('/reset_password_with_code', methods=['GET', 'POST'])
def reset_password_with_code():
    if 'verified_reset_email' not in session:
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            flash('Passwords do not match!')
            return redirect(url_for('reset_password_with_code'))
        user = db.session.query(User).filter_by(email=session['verified_reset_email']).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            
            # Log password reset activity
            log_activity(
                user_id=user.id,
                action_type='password_reset',
                action_description=f'Password reset completed for user: {user.username}',
                additional_data={
                    'username': user.username,
                    'email': user.email
                }
            )
            
            session.pop('verified_reset_email', None)
            flash('Password reset successful! Please log in.')
            return redirect(url_for('login'))
    return render_template('reset_password_with_code.html')

# ---------------- Activity Log Routes ----------------
@app.route('/activity_log', methods=['GET'])
def view_activity_log():
    if 'user_id' not in session:
        flash('Please log in to view activity logs.')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get user's activities with pagination
    activities = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(ActivityLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    # Get activity summary
    summary = get_user_activity_summary(user_id)
    
    return render_template('activity_log.html', 
                         activities=activities.items,
                         pagination=activities,
                         summary=summary)

@app.route('/api/activity_log', methods=['GET'])
def get_activity_log_api():
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    activities = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(ActivityLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'activities': [
            {
                'id': a.id,
                'action_type': a.action_type,
                'action_description': a.action_description,
                'item_id': a.item_id,
                'ip_address': a.ip_address,
                'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S') if a.created_at else None,
                'additional_data': json.loads(a.additional_data) if a.additional_data else None
            } for a in activities.items
        ],
        'pagination': {
            'page': activities.page,
            'pages': activities.pages,
            'per_page': activities.per_page,
            'total': activities.total,
            'has_next': activities.has_next,
            'has_prev': activities.has_prev
        }
    })

@app.route('/export_activity_log', methods=['GET'])
def export_activity_log():
    """Export user's activity log as JSON"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_id = session['user_id']
    
    # Get all user activities
    activities = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(ActivityLog.created_at.desc()).all()
    
    # Format activities for export
    export_data = {
        'user_id': user_id,
        'export_date': datetime.now().isoformat(),
        'total_activities': len(activities),
        'activities': [
            {
                'id': a.id,
                'action_type': a.action_type,
                'action_description': a.action_description,
                'item_id': a.item_id,
                'ip_address': a.ip_address,
                'user_agent': a.user_agent,
                'created_at': a.created_at.isoformat() if a.created_at else None,
                'additional_data': json.loads(a.additional_data) if a.additional_data else None
            } for a in activities
        ]
    }
    
    # Log the export activity
    log_activity(
        user_id=user_id,
        action_type='export_activity_log',
        action_description='Exported activity log data',
        additional_data={
            'export_format': 'json',
            'activities_count': len(activities)
        }
    )
    
    return jsonify(export_data), 200

# ------------ Report Routes ------------
@app.route('/report_user/<int:user_id>', methods=['GET', 'POST'])
def report_user(user_id):
    """Report a user for scam or harassment"""
    if 'user_id' not in session:
        flash('Please login to report users', 'error')
        return redirect(url_for('login'))
    
    if session['user_id'] == user_id:
        flash('You cannot report yourself', 'error')
        return redirect(url_for('home'))
    
    reported_user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        report_type = request.form.get('report_type')
        reason = request.form.get('reason')
        evidence = request.form.get('evidence')
        item_id = request.form.get('item_id')
        
        if not report_type or not reason:
            flash('Please fill in all required fields', 'error')
            return render_template('report_user.html', reported_user=reported_user)
        
        # Check if user already reported this person for the same item
        existing_report = Report.query.filter_by(
            reporter_id=session['user_id'],
            reported_user_id=user_id,
            item_id=item_id if item_id else None
        ).first()
        
        if existing_report:
            flash('You have already reported this user for this item', 'error')
            return render_template('report_user.html', reported_user=reported_user)
        
        # Create new report
        new_report = Report(
            reporter_id=session['user_id'],
            reported_user_id=user_id,
            item_id=item_id if item_id else None,
            report_type=report_type,
            reason=reason,
            evidence=evidence
        )
        
        db.session.add(new_report)
        
        # Check report count and apply suspensions if needed
        active_reports = Report.query.filter_by(
            reported_user_id=user_id,
            status='pending'
        ).count()
        
        if active_reports >= 5:
            # Full suspension for 30 days
            suspension = UserSuspension(
                user_id=user_id,
                suspension_type='full_suspension',
                reason=f'Multiple reports filed against user (Total: {active_reports})',
                report_count=active_reports,
                end_date=datetime.now() + timedelta(days=30),
                is_active=True  # Explicitly set to True
            )
            db.session.add(suspension)
            
            # Create notification for reported user
            notification = Notification(
                user_id=user_id,
                title='Account Suspended',
                message=f'Your account has been suspended for 30 days due to multiple reports. You cannot post or chat during this period.',
                url='/profile'
            )
            db.session.add(notification)
            
        elif active_reports >= 2:
            # Chat ban for 7 days when user gets reported 2 times
            chat_suspension = UserSuspension(
                user_id=user_id,
                suspension_type='chat_ban',
                reason=f'Chat disabled due to multiple reports (Total: {active_reports})',
                report_count=active_reports,
                end_date=datetime.now() + timedelta(days=7),
                is_active=True  # Explicitly set to True
            )
            db.session.add(chat_suspension)
            
            # Create notification for reported user
            notification = Notification(
                user_id=user_id,
                title='Chat Disabled',
                message=f'Your chat has been disabled for 7 days due to multiple reports. You can still post items but cannot send messages.',
                url='/profile'
            )
            db.session.add(notification)
        
        # Create notification for reported user about the report
        report_notification = Notification(
            user_id=user_id,
            title='New Report Filed',
            message=f'A report has been filed against your account. Please review your behavior.',
            url='/profile'
        )
        db.session.add(report_notification)
        
        try:
            db.session.commit()
            flash('Report submitted successfully. Our team will review it.', 'success')
            
            # Log the activity
            log_activity(
                user_id=session['user_id'],
                action_type='report_user',
                action_description=f'Reported user {reported_user.username} for {report_type}',
                additional_data={
                    'reported_user_id': user_id,
                    'report_type': report_type,
                    'item_id': item_id
                }
            )
            
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            flash('Error submitting report. Please try again.', 'error')
    
    return render_template('report_user.html', reported_user=reported_user)



# ------------ Points and Badge Routes ------------
@app.route('/claim_item/<int:item_id>', methods=['GET', 'POST'])
def claim_item(item_id):
    """Owner claims a found item"""
    print(f"DEBUG: Claim item - Route accessed with item_id: {item_id}")
    print(f"DEBUG: Claim item - Session user_id: {session.get('user_id')}")
    print(f"DEBUG: Claim item - Request method: {request.method}")
    
    if 'user_id' not in session:
        print(f"DEBUG: Claim item - No user_id in session, redirecting to login")
        flash('Please login to claim items', 'error')
        return redirect(url_for('login'))
    
    item = LostItem.query.get_or_404(item_id)
    print(f"DEBUG: Claim item - Found item ID: {item_id}, Status: {item.status}, Reported by: {item.reported_by}")
    
    # Check if user is the owner of the lost item
    if item.status != 'found' or not item.reported_by:
        flash('This item cannot be claimed', 'error')
        return redirect(url_for('home'))
    
    # Find the corresponding lost item
    lost_item = LostItem.query.filter_by(
        name=item.name,
        description=item.description,
        status='lost',
        reported_by=session['user_id']
    ).first()
    
    print(f"DEBUG: Claim item - Looking for lost item with name: {item.name}, description: {item.description}")
    print(f"DEBUG: Claim item - Current user ID: {session['user_id']}")
    print(f"DEBUG: Claim item - Found lost item: {lost_item.id if lost_item else 'None'}")
    
    if not lost_item:
        flash('No matching lost item found for your account', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        print(f"DEBUG: Claim item - Processing POST request")
        print(f"DEBUG: Claim item - Awarding points to finder ID: {item.reported_by}")
        
        # Store item information before deletion
        item_name = item.name
        item_id = item.id
        finder_id = item.reported_by
        
        # Award points to the finder first (without committing)
        award_return_points(finder_id, 1, commit=False)
        
        # Remove both items
        db.session.delete(lost_item)
        db.session.delete(item)
        
        try:
            print(f"DEBUG: Claim item - About to commit transaction")
            db.session.commit()
            print(f"DEBUG: Claim item - Successfully committed transaction")
            
            # Verify the items were actually deleted
            deleted_found_item = LostItem.query.get(item.id)
            deleted_lost_item = LostItem.query.get(lost_item.id)
            print(f"DEBUG: Claim item - After commit - Found item exists: {deleted_found_item is not None}, Lost item exists: {deleted_lost_item is not None}")
            
            if deleted_found_item is None and deleted_lost_item is None:
                print(f"DEBUG: Claim item - Items successfully deleted, redirecting to home")
                flash('Item claimed successfully! The finder has been awarded 1 return point.', 'success')
                
                # Log the activity
                log_activity(
                    user_id=session['user_id'],
                    action_type='claim_item',
                    action_description=f'Claimed found item: {item_name}',
                    additional_data={
                        'item_id': item_id,
                        'finder_id': finder_id,
                        'points_awarded': 1
                    }
                )
                
                return redirect(url_for('home'))
            else:
                print(f"DEBUG: Claim item - Items not deleted properly, rolling back")
                db.session.rollback()
                flash('Error: Items were not properly deleted. Please try again.', 'error')
        except Exception as e:
            print(f"DEBUG: Claim item - Error during commit: {e}")
            print(f"DEBUG: Claim item - Full error details: {type(e).__name__}: {str(e)}")
            db.session.rollback()
            flash(f'Error claiming item: {str(e)}. Please try again.', 'error')
    
    return render_template('claim_item.html', item=item, lost_item=lost_item)

@app.route('/mark_found/<int:item_id>', methods=['GET', 'POST'])
def mark_found(item_id):
    """Owner marks a lost item as found"""
    print(f"DEBUG: Mark found - Route accessed with item_id: {item_id}")
    print(f"DEBUG: Mark found - Session user_id: {session.get('user_id')}")
    print(f"DEBUG: Mark found - Request method: {request.method}")
    
    if 'user_id' not in session:
        print(f"DEBUG: Mark found - No user_id in session, redirecting to login")
        flash('Please login to mark items as found', 'error')
        return redirect(url_for('login'))
    
    item = LostItem.query.get_or_404(item_id)
    
    # Check if user is the owner
    if item.reported_by != session['user_id']:
        flash('You can only mark your own items as found', 'error')
        return redirect(url_for('home'))
    
    if item.status != 'lost':
        flash('This item is not marked as lost', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        helper_type = request.form.get('helper_type')
        helper_identifier = request.form.get('helper_identifier')
        
        if not helper_type:
            flash('Please select who helped you recover the item', 'error')
            return render_template('mark_found.html', item=item)
        
        if helper_type == 'user' and not helper_identifier:
            flash('Please provide the user ID or email of who helped you', 'error')
            return render_template('mark_found.html', item=item)
        
        # Store item information before deletion
        item_name = item.name
        item_id = item.id
        helper_user = None
        
        # Award points if it was a user who helped
        if helper_type == 'user':
            # Try to find user by ID or email
            try:
                helper_id = int(helper_identifier)
                helper_user = User.query.get(helper_id)
            except ValueError:
                helper_user = User.query.filter_by(email=helper_identifier).first()
            
            if helper_user:
                print(f"DEBUG: Mark found - Awarding 1 point to user {helper_user.id} ({helper_user.username})")
                # Award points and commit them immediately to ensure they persist
                award_return_points(helper_user.id, 1, commit=True)
                success_message = f'Item marked as found! {helper_user.username} has been awarded 1 return point.'
            else:
                success_message = 'User not found. Item marked as found without awarding points.'
                print(f"DEBUG: Mark found - User not found for identifier: {helper_identifier}")
        else:
            success_message = 'Item marked as found! Thank you for updating the status.'
            print(f"DEBUG: Mark found - Non-user helper, no points awarded")
        
        try:
            print(f"DEBUG: Mark found - About to delete item and commit transaction")
            
            # Remove the item completely from the system
            db.session.delete(item)
            
            # Commit the deletion
            db.session.commit()
            print(f"DEBUG: Mark found - Successfully committed item deletion")
            
            # Log the activity AFTER successful deletion
            print(f"DEBUG: Mark found - Logging activity")
            log_activity(
                user_id=session['user_id'],
                action_type='mark_found',
                action_description=f'Marked lost item as found: {item_name}',
                additional_data={
                    'item_id': item_id,
                    'helper_type': helper_type,
                    'helper_identifier': helper_identifier,
                    'helper_user_id': helper_user.id if helper_user else None
                }
            )
            
            # Create notification for the finder if it was a user
            if helper_user:
                print(f"DEBUG: Mark found - Creating notification for finder")
                notification = Notification(
                    user_id=helper_user.id,
                    title='Item Marked as Found',
                    message=f'Your help in finding "{item_name}" has been acknowledged! You earned 1 return point.',
                    url='/profile'
                )
                db.session.add(notification)
                db.session.commit()
                print(f"DEBUG: Mark found - Successfully created notification for finder")
            
            print(f"DEBUG: Mark found - Item successfully deleted, redirecting to home")
            
            # Show success message and redirect to home
            flash(success_message, 'success')
            print(f"DEBUG: Mark found - Redirecting to home with message: {success_message}")
            return redirect(url_for('home'))
        except Exception as e:
            print(f"DEBUG: Mark found - Error during commit: {e}")
            db.session.rollback()
            print(f"Error in mark_found: {e}")
            flash('Error marking item as found. Please try again.', 'error')
    
    return render_template('mark_found.html', item=item)

@app.route('/api/activity_stats', methods=['GET'])
def get_activity_stats():
    """Get detailed activity statistics for the user"""
    if 'user_id' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    user_id = session['user_id']
    
    # Get all user activities
    all_activities = ActivityLog.query.filter_by(user_id=user_id).all()
    
    # Calculate time periods
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    year_ago = now - timedelta(days=365)
    
    # Filter activities by time period
    this_week = [a for a in all_activities if a.created_at and a.created_at >= week_ago]
    this_month = [a for a in all_activities if a.created_at and a.created_at >= month_ago]
    this_year = [a for a in all_activities if a.created_at and a.created_at >= year_ago]
    
    # Activity type breakdown
    activity_types = {}
    for activity in all_activities:
        activity_type = activity.action_type
        activity_types[activity_type] = activity_types.get(activity_type, 0) + 1
    
    # Most active days
    daily_activity = {}
    for activity in all_activities:
        if activity.created_at:
            date_str = activity.created_at.strftime('%Y-%m-%d')
            daily_activity[date_str] = daily_activity.get(date_str, 0) + 1
    
    most_active_days = sorted(daily_activity.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Items created
    items_created = [a for a in all_activities if a.action_type in ['create_lost_item', 'create_found_item']]
    
    stats = {
        'total_activities': len(all_activities),
        'this_week': len(this_week),
        'this_month': len(this_month),
        'this_year': len(this_year),
        'activity_types': activity_types,
        'most_active_days': [{'date': date, 'count': count} for date, count in most_active_days],
        'items_created': len(items_created),
        'last_activity': all_activities[0].created_at.isoformat() if all_activities else None
    }
    
    return jsonify(stats), 200

# Run the App
if __name__ == "__main__":
    app.run(host = '0.0.0.0', debug=True)
