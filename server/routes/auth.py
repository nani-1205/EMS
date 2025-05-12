# /root/EMS/server/routes/auth.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, g
from models.db import get_db
import bcrypt
from functools import wraps
from bson import ObjectId
# === REMOVE OLD IMPORT ===
# from werkzeug.urls import url_parse # <-- REMOVE THIS LINE
# === ADD NEW IMPORT ===
from urllib.parse import urlsplit # <-- IMPORT from standard library

auth_bp = Blueprint('auth', __name__)

# Decorator to require login and admin role
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login', next=request.url))

        try:
            user_id_str = session['user_id']
            user_obj_id = ObjectId(user_id_str)
        except Exception as e:
            current_app.logger.error(f"Invalid ObjectId in session: {session.get('user_id')}, Error: {e}")
            flash("Invalid session data. Please log in again.", "danger")
            session.clear()
            return redirect(url_for('auth.login'))

        user = get_db().users.find_one({"_id": user_obj_id})

        if not user:
            flash("User session not found. Please log in again.", "warning")
            session.clear()
            return redirect(url_for('auth.login'))

        if user.get('role') != 'admin':
            flash("You do not have permission to access this page.", "danger")
            # Redirect non-admins - adjust target if needed
            return redirect(url_for('auth.login')) # Or maybe dashboard if they have *some* access

        g.user = user
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.view_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
             flash('Username and password are required.', 'warning')
             return render_template('login.html')

        db = get_db()
        user = db.users.find_one({'username': username})

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            session.clear()
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user.get('role', 'user')

            current_app.logger.info(f"User '{username}' logged in successfully.")
            flash(f"Welcome back, {user['username']}!", "success")

            try:
                # Check for pending rename notification (adjust logic if needed)
                employee = db.employees.find_one({"employee_id": user['username']})
                if employee and employee.get("status") == "pending_rename":
                     flash(f"Notification: Employee record '{employee['employee_id']}' needs configuration.", "info")
            except Exception as e:
                current_app.logger.error(f"Error checking employee status during login for {username}: {e}")

            next_page = request.args.get('next')

            # === UPDATE REDIRECT CHECK ===
            # Use urlsplit from urllib.parse here
            if next_page and urlsplit(next_page).netloc == '':
            # === END UPDATE ===
                current_app.logger.debug(f"Redirecting logged-in user to requested internal page: {next_page}")
                return redirect(next_page)
            else:
                current_app.logger.debug(f"Redirecting logged-in user to default dashboard.")
                return redirect(url_for('dashboard.view_dashboard'))
        else:
            current_app.logger.warning(f"Failed login attempt for username: '{username}'")
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    username = session.get('username', 'unknown user')
    session.clear()
    current_app.logger.info(f"User '{username}' logged out.")
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('auth.login'))