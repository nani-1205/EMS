# /root/EMS/server/routes/auth.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, g
from models.db import get_db
import bcrypt
from functools import wraps
from bson import ObjectId  # <-- IMPORT ObjectId from bson
from werkzeug.urls import url_parse # <-- IMPORT for redirect validation

auth_bp = Blueprint('auth', __name__)

# Decorator to require login and admin role
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            # Store the intended destination page
            return redirect(url_for('auth.login', next=request.url))

        # --- Convert string from session back to ObjectId for query ---
        try:
            # Retrieve the user ID string from the session
            user_id_str = session['user_id']
            # Convert the string back to a BSON ObjectId
            user_obj_id = ObjectId(user_id_str)
        except Exception as e:
            # Handle cases where the session ID is missing, malformed, or invalid
            current_app.logger.error(f"Invalid ObjectId in session: {session.get('user_id')}, Error: {e}")
            flash("Invalid session data. Please log in again.", "danger")
            session.clear() # Clear the potentially corrupted session
            return redirect(url_for('auth.login'))
        # --- End ObjectId conversion ---

        # Fetch the user from the database using the ObjectId
        user = get_db().users.find_one({"_id": user_obj_id})

        if not user:
            # If the user_id from the session doesn't correspond to a user in the DB
            flash("User session not found. Please log in again.", "warning")
            session.clear() # Clear the invalid session
            return redirect(url_for('auth.login'))

        # --- Role Check (Example: require 'admin' role) ---
        if user.get('role') != 'admin':
            flash("You do not have permission to access this page.", "danger")
            # Redirect non-admins to a different page or show an error
            # For now, redirecting back to login, but a dedicated 'unauthorized' page or user dashboard might be better
            return redirect(url_for('auth.login'))
        # --- End Role Check ---

        # Make user object available globally within the request context (optional)
        g.user = user # Store the fetched user object in Flask's 'g'

        # If all checks pass, proceed to the original view function
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in (session exists), redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard.view_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Basic input validation
        if not username or not password:
             flash('Username and password are required.', 'warning')
             return render_template('login.html')

        db = get_db()
        user = db.users.find_one({'username': username})

        # Check if user exists and password is correct
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            # User authenticated successfully
            session.clear() # Clear any old session data

            # --- FIX: Store the string representation of ObjectId in the session ---
            session['user_id'] = str(user['_id'])
            # ---------------------------------------------------------------------
            session['username'] = user['username']
            session['role'] = user.get('role', 'user') # Store role for convenience

            current_app.logger.info(f"User '{username}' logged in successfully.")
            flash(f"Welcome back, {user['username']}!", "success")

            # Check for pending rename (this logic might need refinement based on your user/employee mapping)
            employee = db.employees.find_one({"employee_id": user['username']})
            if employee and employee.get("status") == "pending_rename":
                 flash(f"Notification: Employee '{employee['employee_id']}' needs configuration.", "info")

            # Handle redirection after login
            next_page = request.args.get('next')
            # Security: Prevent open redirect attacks - only redirect to internal paths
            if next_page and url_parse(next_page).netloc == '':
                current_app.logger.debug(f"Redirecting to requested next page: {next_page}")
                return redirect(next_page)
            else:
                # Default redirect to the main dashboard
                current_app.logger.debug("Redirecting to default dashboard.")
                return redirect(url_for('dashboard.view_dashboard'))
        else:
            # Authentication failed
            current_app.logger.warning(f"Failed login attempt for username: '{username}'")
            flash('Invalid username or password.', 'danger')

    # Render the login page for GET requests or failed POST attempts
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    # Get username before clearing session for logging purposes
    username = session.get('username', 'unknown user')
    session.clear() # Remove all data from the session
    current_app.logger.info(f"User '{username}' logged out.")
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('auth.login')) # Redirect to the login page