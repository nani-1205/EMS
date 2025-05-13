# /root/EMS/server/routes/settings.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from models.db import get_db
from routes.auth import login_required
import bcrypt
from bson import ObjectId

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/')
@login_required
def index():
    # Main settings page, could list various settings options
    # For now, just show the change password form
    db = get_db()
    pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    return render_template('settings/index.html',
                           active_page='settings',
                           pending_rename_count=pending_rename_count)


@settings_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    db = get_db()
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        user_id_str = session.get('user_id')
        if not user_id_str:
            flash("Session error. Please log in again.", "danger")
            return redirect(url_for('auth.login'))

        user = db.users.find_one({"_id": ObjectId(user_id_str)})
        if not user:
            flash("User not found. Please log in again.", "danger")
            return redirect(url_for('auth.login'))

        errors = False
        if not bcrypt.checkpw(current_password.encode('utf-8'), user['password_hash']):
            flash("Current password is incorrect.", "danger")
            errors = True
        if not new_password or len(new_password) < 8: # Basic length check
            flash("New password must be at least 8 characters long.", "warning")
            errors = True
        if new_password != confirm_password:
            flash("New passwords do not match.", "warning")
            errors = True

        if not errors:
            hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            try:
                db.users.update_one(
                    {"_id": ObjectId(user_id_str)},
                    {"$set": {"password_hash": hashed_new_password}}
                )
                flash("Password changed successfully. Please log in again with your new password.", "success")
                current_app.logger.info(f"User '{user['username']}' changed their password.")
                session.clear() # Log out user after password change
                return redirect(url_for('auth.login'))
            except Exception as e:
                current_app.logger.error(f"Error changing password for user {user['username']}: {e}")
                flash("An error occurred while changing the password.", "danger")
        
        # If there were errors, fall through to re-render the form
        # (or redirect back to settings index if preferred, with flashed messages)

    pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    return render_template('settings/change_password.html', # A dedicated template or part of settings/index.html
                            active_page='settings',
                            pending_rename_count=pending_rename_count)


# Add other settings routes here (e.g., managing API keys, data retention)