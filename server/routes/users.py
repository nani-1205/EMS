# /root/EMS/server/routes/users.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models.db import get_db
from routes.auth import login_required
from bson import ObjectId
import datetime

users_bp = Blueprint('users', __name__)

@users_bp.route('/')
@login_required
def list_users():
    db = get_db()
    # Fetch all employees, maybe sort by status or name
    employees = list(db.employees.find().sort([("status", 1), ("display_name", 1)]))
    pending_rename_count = db.employees.count_documents({"status": "pending_rename"}) # Get count for sidebar consistency

    return render_template('users.html',
                           employees=employees,
                           pending_rename_count=pending_rename_count, # Pass count for potential header info
                           active_page='users') # For sidebar highlighting

@users_bp.route('/edit/<employee_doc_id>', methods=['GET', 'POST'])
@login_required
def edit_user(employee_doc_id):
    db = get_db()
    try:
        obj_id = ObjectId(employee_doc_id)
    except Exception:
        flash("Invalid employee ID.", "danger")
        return redirect(url_for('users.list_users'))

    employee = db.employees.find_one({"_id": obj_id})

    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for('users.list_users'))

    if request.method == 'POST':
        new_display_name = request.form.get('display_name', '').strip()
        new_status = request.form.get('status', 'active') # Default to active if changed

        if not new_display_name:
             flash("Display name cannot be empty.", "warning")
             # Re-render the form with the current data
             return render_template('user_edit.html', # You need to create this template
                                   employee=employee,
                                   active_page='users')

        update_data = {
            "display_name": new_display_name,
            "status": new_status
            # Add other fields to update here if needed (e.g., team, notes)
        }

        try:
            db.employees.update_one({"_id": obj_id}, {"$set": update_data})
            flash(f"Employee '{new_display_name}' updated successfully.", "success")
            current_app.logger.info(f"Admin '{session.get('username')}' updated employee {employee_doc_id} to name '{new_display_name}' and status '{new_status}'")
            return redirect(url_for('users.list_users'))
        except Exception as e:
             flash(f"Error updating employee: {e}", "danger")
             current_app.logger.error(f"Error updating employee {employee_doc_id}: {e}")

    # For GET request, show the edit form
    # You NEED to create 'user_edit.html' template for this form
    flash("Editing user: " + employee.get('display_name', employee['employee_id']), "info") # Temp message
    # return render_template('user_edit.html', employee=employee, active_page='users')
    # Since user_edit.html isn't created, redirect back for now
    return redirect(url_for('users.list_users'))

# Add routes for deleting users, assigning teams etc. as needed