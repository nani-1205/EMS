from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from models.db import get_db
import bcrypt
from functools import wraps

auth_bp = Blueprint('auth', __name__)

# Decorator to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login', next=request.url))
        # You might want to add role checks here too
        user = get_db().users.find_one({"_id": session['user_id']})
        if not user or user.get('role') != 'admin': # Example: Only allow admins
             flash("You do not have permission to access this page.", "danger")
             return redirect(url_for('dashboard.view_dashboard')) # Or an unauthorized page
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.view_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        user = db.users.find_one({'username': username})

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            # Password matches
            session.clear()
            session['user_id'] = user['_id'] # Store MongoDB ObjectId directly (it's serializable)
            session['username'] = user['username']
            session['role'] = user.get('role', 'user') # Default role if not set
            flash(f"Welcome back, {user['username']}!", "success")

            # Check if user needs renaming (simple example)
            employee = db.employees.find_one({"employee_id": user['username']}) # Assuming username maps to employee_id for now
            if employee and employee.get("status") == "pending_rename":
                 flash(f"Employee '{employee['employee_id']}' needs to be assigned a proper name.", "info")
                 # Redirect to user management or show notification on dashboard

            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.view_dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))