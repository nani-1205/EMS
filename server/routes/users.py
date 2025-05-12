# /root/EMS/server/routes/users.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.db import get_db
from routes.auth import login_required # Import login_required if needed for user routes
from bson import ObjectId
import datetime

# --- DEFINE THE BLUEPRINT HERE ---
users_bp = Blueprint('users', __name__, template_folder='../templates') # Adjust template_folder if it's elsewhere

# --- Example User Route (Build this out) ---
@users_bp.route('/')
@login_required # Make sure users page requires login
def list_users():
    db = get_db()
    # Fetch users who need renaming or all users
    pending_users = list(db.employees.find({"status": "pending_rename"}))
    active_users = list(db.employees.find({"status": {"$ne": "pending_rename"}}).sort("display_name", 1)) # Example sort

    # You'll likely want a dedicated template for this
    # return render_template('users.html', pending=pending_users, active=active_users, active_page='users')
    return f"User Management Page - Pending: {len(pending_users)}, Active: {len(active_users)}" # Placeholder

@users_bp.route('/rename/<employee_id>', methods=['GET', 'POST'])
@login_required
def rename_user(employee_id):
    db = get_db()
    employee = db.employees.find_one({"employee_id": employee_id})

    if not employee:
        flash(f"Employee {employee_id} not found.", "danger")
        return redirect(url_for('users.list_users')) # Redirect back to user list

    if request.method == 'POST':
        new_name = request.form.get('display_name')
        if not new_name or len(new_name) < 2:
             flash("Please provide a valid display name (at least 2 characters).", "warning")
        else:
            try:
                db.employees.update_one(
                    {"employee_id": employee_id},
                    {"$set": {"display_name": new_name, "status": "active"}} # Update name and status
                )
                flash(f"Employee '{employee_id}' updated to '{new_name}'.", "success")
                return redirect(url_for('dashboard.view_dashboard')) # Redirect to dashboard or user list
            except Exception as e:
                 flash(f"Error updating employee: {e}", "danger")

    # Pass the employee object to the template for the GET request form
    # return render_template('rename_user.html', employee=employee) # Need to create this template
    return f"""
        <h1>Rename User: {employee.get('employee_id')}</h1>
        <p>Current Name: {employee.get('display_name')}</p>
        <form method="POST">
            <label for="display_name">New Display Name:</label>
            <input type="text" id="display_name" name="display_name" required minlength="2">
            <button type="submit">Update Name</button>
        </form>
        <a href="{url_for('users.list_users')}">Cancel</a>
    """ # Basic placeholder form


# Add other user management routes here (edit, delete, view details, etc.)