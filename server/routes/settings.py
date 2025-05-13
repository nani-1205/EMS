# /root/EMS/server/routes/settings.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash, current_app
)
from models.db import get_db
from routes.auth import login_required
import bcrypt
from bson import ObjectId

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/')
@login_required
def index():
    """
    Main settings page.
    Currently embeds the change password form.
    """
    db = get_db()
    try:
        # Fetch pending_rename_count for the layout, even on the settings page
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching pending_rename_count for settings page: {e}")
        pending_rename_count = 0 # Default if DB error

    return render_template('settings/index.html',
                           active_page='settings',
                           pending_rename_count=pending_rename_count)


@settings_bp.route('/change_password', methods=['POST']) # Changed to only accept POST
@login_required
def change_password():
    db = get_db()
    # This route is now dedicated to handling the form submission from settings/index.html

    # if request.method == 'POST': # This check is redundant due to methods=['POST']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    user_id_str = session.get('user_id')
    if not user_id_str: # Should be caught by @login_required, but good for robustness
        flash("Session error. Please log in again.", "danger")
        return redirect(url_for('auth.login'))

    try:
        user_obj_id = ObjectId(user_id_str)
        user = db.users.find_one({"_id": user_obj_id})
    except Exception as e: # Invalid ObjectId or DB error
        current_app.logger.error(f"Error fetching user for password change (ID: {user_id_str}): {e}")
        flash("Error accessing user data. Please try again.", "danger")
        return redirect(url_for('settings.index')) # Redirect back to settings page

    if not user:
        flash("User not found. Please log in again.", "danger")
        session.clear() # Clear potentially invalid session
        return redirect(url_for('auth.login'))

    form_errors = False # Flag to track if any validation error occurred
    if not current_password or not bcrypt.checkpw(current_password.encode('utf-8'), user.get('password_hash', b'')):
        flash("Current password is incorrect.", "danger")
        form_errors = True
    if not new_password or len(new_password) < 8:
        flash("New password must be at least 8 characters long.", "warning")
        form_errors = True
    if new_password != confirm_password:
        flash("New passwords do not match.", "warning")
        form_errors = True

    if not form_errors:
        hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        try:
            db.users.update_one(
                {"_id": user_obj_id},
                {"$set": {"password_hash": hashed_new_password}}
            )
            flash("Password changed successfully. Please log in again with your new password.", "success")
            current_app.logger.info(f"User '{user.get('username')}' changed their password.")
            session.clear() # Log out user after password change
            return redirect(url_for('auth.login'))
        except Exception as e:
            current_app.logger.error(f"Error updating password for user '{user.get('username')}': {e}")
            flash("An error occurred while changing the password. Please try again.", "danger")
    
    # If there were errors, or if it wasn't a POST (though route restricts to POST),
    # redirect back to the settings page to display flashed messages.
    # The form values will be lost on redirect, which is acceptable for password forms.
    # If you wanted to repopulate (not recommended for passwords), you'd re-render.
    return redirect(url_for('settings.index'))

# Example of another settings route you might add later:
# @settings_bp.route('/agent_config', methods=['GET', 'POST'])
# @login_required
# def agent_config():
#     # Logic for viewing/modifying agent configuration stored in DB
#     pending_rename_count = get_db().employees.count_documents({"status": "pending_rename"})
#     return render_template('settings/agent_config.html', active_page='settings', pending_rename_count=pending_rename_count)