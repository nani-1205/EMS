# /root/EMS/server/routes/auth.py
# *** PASTE THE FULL CODE FROM THE USER'S LAST MESSAGE HERE ***
# (Starting with 'from flask import Blueprint...' and ending with 'return redirect(url_for('auth.login')) # Redirect to the login page')

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
        # Ensure only users with the 'admin' role can proceed
        if user.get('role') != 'admin':
            flash("You do not have permission to access this page.", "danger")
            # Redirect non-admins away from protected pages
            # Redirecting to login might be confusing; a user dashboard or a specific 'unauthorized' page is better in a real app.
            # For now, redirecting to dashboard might be slightly better if non-admin users have some view there.
            # If non-admins should NEVER log in here, redirecting to login is okay. Let's assume only admins use this portal.
            return redirect(url_for('auth.login')) # Or url_for('dashboard.view_dashboard') if non-admins have limited view
        # --- End Role Check ---

        # Make user object available globally within the request context (optional, but can be useful)
        g.user = user # Store the fetched user object in Flask's 'g'

        # If all checks pass, proceed to the original view function
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in (valid session exists), redirect to dashboard
    if 'user_id' in session:
        # Optional: Add a quick verification here? Maybe not necessary if login_required does it robustly.
        return redirect(url_for('dashboard.view_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Basic input validation
        if not username or not password:
             flash('Username and password are required.', 'warning')
             return render_template('login.html')

        db = get_db()
        user = db.users.find_one({'username': username}) # Case-sensitive username check

        # Check if user exists and password is correct using bcrypt
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            # User authenticated successfully
            session.clear() # Prevent session fixation: clear old session before creating new one

            # --- Store the string representation of ObjectId in the session ---
            # MongoDB ObjectIds are not directly JSON serializable for Flask's default session handler
            session['user_id'] = str(user['_id'])
            # ---------------------------------------------------------------------
            session['username'] = user['username']
            session['role'] = user.get('role', 'user') # Store role for convenience in templates/checks

            current_app.logger.info(f"User '{username}' logged in successfully.")
            flash(f"Welcome back, {user['username']}!", "success")

            # --- Notification Check for Pending Rename ---
            # This assumes the 'employee_id' in the 'employees' collection might match the admin 'username'.
            # This mapping might need adjustment based on your actual structure.
            # Maybe the check should happen on the dashboard load instead?
            try:
                employee = db.employees.find_one({"employee_id": user['username']}) # Check if an employee record matches this username
                if employee and employee.get("status") == "pending_rename":
                     flash(f"Notification: Employee record '{employee['employee_id']}' needs configuration.", "info")
            except Exception as e:
                current_app.logger.error(f"Error checking employee status during login for {username}: {e}")
            # --- End Notification Check ---

            # Handle redirection after successful login
            next_page = request.args.get('next')
            # Security: Prevent open redirect attacks - only redirect to relative paths within the application
            if next_page and url_parse(next_page).netloc == '':
                current_app.logger.debug(f"Redirecting logged-in user to requested internal page: {next_page}")
                return redirect(next_page)
            else:
                # Default redirect to the main dashboard if 'next' is missing or invalid
                current_app.logger.debug(f"Redirecting logged-in user to default dashboard.")
                return redirect(url_for('dashboard.view_dashboard'))
        else:
            # Authentication failed (user not found or password mismatch)
            current_app.logger.warning(f"Failed login attempt for username: '{username}'")
            flash('Invalid username or password.', 'danger')
            # Do NOT reveal whether the username exists or not

    # Render the login page for GET requests or failed POST attempts
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    # Get username before clearing session for logging purposes
    username = session.get('username', 'unknown user') # Get username if available
    session.clear() # Remove all data from the session
    current_app.logger.info(f"User '{username}' logged out.")
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('auth.login')) # Redirect to the login page