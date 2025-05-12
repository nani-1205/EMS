# /root/EMS/server/routes/users.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from models.db import get_db
from routes.auth import login_required # Imports decorator (and g indirectly if used)
from bson import ObjectId # For converting string ID back to ObjectId
import datetime

users_bp = Blueprint('users', __name__)

@users_bp.route('/')
@login_required # Ensures only logged-in admins can access
def list_users():
    """Displays a list of all employees."""
    db = get_db()
    try:
        # Fetch all employees, sort by status (pending first), then name
        employees = list(db.employees.find().sort([
            ("status", 1), # 'active', 'disabled', 'inactive', 'pending_rename' - alphabetical might work
            ("display_name", 1)
        ]))
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching employees: {e}")
        flash("Error retrieving employee list from database.", "danger")
        employees = []
        pending_rename_count = 0

    return render_template('users.html',
                           employees=employees,
                           pending_rename_count=pending_rename_count, # Pass count for potential header info/sidebar
                           active_page='users') # For sidebar highlighting

@users_bp.route('/edit/<employee_doc_id>', methods=['GET', 'POST'])
@login_required # Ensures only logged-in admins can access
def edit_user(employee_doc_id):
    """Handles editing of an employee's details (name, status)."""
    db = get_db()
    try:
        # Validate and convert the document ID string to ObjectId
        obj_id = ObjectId(employee_doc_id)
    except Exception:
        flash("Invalid employee ID format.", "danger")
        return redirect(url_for('users.list_users'))

    # Fetch the specific employee document
    employee = db.employees.find_one({"_id": obj_id})

    # Handle case where employee with that ID doesn't exist
    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for('users.list_users'))

    # --- Handle POST request (Form Submission) ---
    if request.method == 'POST':
        # Get data from form
        new_display_name = request.form.get('display_name', '').strip()
        new_status = request.form.get('status', 'active') # Default to 'active' if missing

        # Basic Server-side Validation
        errors = {}
        if not new_display_name:
            errors['display_name'] = "Display name cannot be empty."

        valid_statuses = ["active", "pending_rename", "inactive", "disabled"]
        if new_status not in valid_statuses:
             errors['status'] = "Invalid status selected."
             new_status = employee.get('status', 'active') # Keep original status if invalid submitted

        if errors:
            # If validation errors, flash message and re-render form with errors
            flash("Please correct the errors below.", "warning")
            # Note: We are not using Flask-WTF here, so passing errors requires custom handling
            # For simplicity, we flash a general message and rely on HTML5 'required' for display_name.
            # We pass 'request.form' to repopulate fields correctly.
            return render_template('user_edit.html',
                                   employee=employee,
                                   form_errors=errors, # Pass errors dict (template needs to handle it)
                                   submitted_data=request.form, # Pass submitted data for repopulation
                                   active_page='users')

        # Prepare data for update
        update_data = {
            "display_name": new_display_name,
            "status": new_status
            # Add other fields here if the form is extended (e.g., team, notes)
            # "team": request.form.get('team')
        }

        # Attempt to update the database
        try:
            result = db.employees.update_one({"_id": obj_id}, {"$set": update_data})

            if result.modified_count > 0:
                flash(f"Employee '{new_display_name}' updated successfully.", "success")
                current_app.logger.info(f"Admin '{session.get('username', 'unknown')}' updated employee {employee_doc_id} (ID: {employee.get('employee_id')}) to name '{new_display_name}' and status '{new_status}'")
            else:
                 # Check if data submitted was actually different from stored data
                 if employee.get('display_name') == new_display_name and employee.get('status') == new_status:
                     flash(f"No changes detected for employee '{new_display_name}'.", "info")
                 else:
                     # This case might indicate a DB issue if update_one reported no modification despite changes
                     flash(f"Employee '{new_display_name}' update reported no changes, please check.", "warning")
                     current_app.logger.warning(f"Update reported no changes for employee {employee_doc_id} despite potentially different data.")

            return redirect(url_for('users.list_users'))

        except Exception as e:
             flash(f"Database error updating employee: {e}", "danger")
             current_app.logger.error(f"Error updating employee {employee_doc_id}: {e}")
             # Re-render form on DB error, preserving submitted data
             return render_template('user_edit.html',
                                   employee=employee,
                                   submitted_data=request.form,
                                   active_page='users')

    # --- Handle GET request ---
    # Render the edit form, passing the current employee data
    return render_template('user_edit.html',
                           employee=employee,
                           active_page='users')

# Potential future routes:
# @users_bp.route('/delete/<employee_doc_id>', methods=['POST'])
# @login_required
# def delete_user(employee_doc_id):
#    # Add logic to delete user (with confirmation)
#    pass