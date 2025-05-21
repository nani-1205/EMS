# /opt/employee/v-2/EMS/server/routes/auth.py

from flask import (
    Blueprint, render_template, request, redirect, url_for, session,
    flash, current_app, g
)
from models.db import get_db # Assuming get_db provides access to your MongoDB database
import bcrypt
from functools import wraps # For the @wraps decorator
from bson import ObjectId   # For handling MongoDB ObjectIds
from urllib.parse import urlsplit # For safe redirect validation

auth_bp = Blueprint('auth', __name__)

# --- Login Required Decorator (Admin Role Specific) ---
def login_required(f):
    """
    Decorator to ensure a user is logged in and has an 'admin' role.
    Redirects to login page if not authenticated or authorized.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check if user_id is in session (basic login check)
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            # Store the originally requested URL to redirect back after login
            return redirect(url_for('auth.login', next=request.url))

        # 2. Validate session user_id and fetch user
        user_id_str = session.get('user_id')
        user = None
        if user_id_str:
            try:
                user_obj_id = ObjectId(user_id_str)
                db = get_db()
                user = db.users.find_one({"_id": user_obj_id})
            except Exception as e: # Invalid ObjectId format or DB error
                current_app.logger.error(f"Error fetching user by session ID '{user_id_str}': {e}", exc_info=True)
                flash("Session error. Please log in again.", "danger")
                session.clear()
                return redirect(url_for('auth.login'))
        
        if not user:
            flash("Your session is invalid or has expired. Please log in again.", "warning")
            session.clear() # Clear invalid session
            return redirect(url_for('auth.login'))

        # 3. Check if the user has the 'admin' role
        if user.get('role') != 'admin':
            flash("You do not have permission to access this page.", "danger")
            # Redirect non-admins to a different page (e.g., dashboard if they have limited access, or login)
            # For this app, assuming only admins should access backend, so redirect to login or a generic error.
            current_app.logger.warning(f"Unauthorized access attempt by user '{user.get('username')}' (role: {user.get('role')}) to admin page: {request.path}")
            return redirect(url_for('auth.login')) # Or perhaps a dedicated 'unauthorized' page

        # 4. Make user object available globally for the request context (optional)
        g.user = user
        
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session and 'role' in session and session['role'] == 'admin':
        # If already logged in as admin, redirect to dashboard
        return redirect(url_for('dashboard.view_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'warning')
            return render_template('login.html') # Re-render login form

        db = get_db()
        user = db.users.find_one({'username': username})

        if user and user.get('password_hash') and \
           bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            
            # User authenticated successfully
            session.clear() # Prevent session fixation
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user.get('role', 'user') # Default to 'user' if role not set

            # Security: Regenerate session ID if your session interface supports it
            # session.regenerate() # Example, depends on session interface

            current_app.logger.info(f"User '{username}' (Role: {session['role']}) logged in successfully.")
            flash(f"Welcome back, {user['username']}!", "success")

            # Redirect to the originally requested page, or dashboard if none
            next_page = request.args.get('next')
            if next_page and urlsplit(next_page).netloc == '': # Basic open redirect protection
                return redirect(next_page)
            return redirect(url_for('dashboard.view_dashboard'))
        else:
            current_app.logger.warning(f"Failed login attempt for username: '{username}'.")
            flash('Invalid username or password. Please try again.', 'danger')
            # Do not reveal whether username exists or password was wrong specifically

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required # Ensures only logged-in users can access logout, then clears session
def logout():
    username = session.get('username', 'User') # Get username for logging before clearing
    session.clear()
    current_app.logger.info(f"User '{username}' logged out successfully.")
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('auth.login'))