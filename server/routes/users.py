# /root/EMS/server/routes/users.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from models.db import get_db
from routes.auth import login_required
from bson import ObjectId
import datetime

users_bp = Blueprint('users', __name__)
USERS_PER_PAGE = 10 # Configuration for pagination

@users_bp.route('/')
@login_required
def list_users():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    skip_count = (page - 1) * USERS_PER_PAGE
    search_query = request.args.get('q', '').strip()
    filter_criteria = {}

    if search_query:
        regex_query = {"$regex": search_query, "$options": "i"}
        filter_criteria["$or"] = [
            {"display_name": regex_query},
            {"employee_id": regex_query},
            {"status": regex_query} # Allow searching by status too
        ]

    try:
        total_users = db.employees.count_documents(filter_criteria)
        employees = list(db.employees.find(filter_criteria)
                         .sort([("status", 1), ("display_name", 1)]) # Sort by status, then name
                         .skip(skip_count)
                         .limit(USERS_PER_PAGE))
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"}) # For sidebar consistency
    except Exception as e:
        current_app.logger.error(f"Error fetching user list: {e}")
        flash("Could not retrieve user list.", "danger")
        total_users, employees, pending_rename_count = 0, [], 0

    total_pages = (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE

    return render_template('users.html',
                           employees=employees,
                           pending_rename_count=pending_rename_count,
                           active_page='users',
                           current_page=page,
                           total_pages=total_pages,
                           search_query=search_query)


@users_bp.route('/edit/<employee_doc_id>', methods=['GET', 'POST'])
@login_required
def edit_user(employee_doc_id):
    db = get_db()
    try:
        obj_id = ObjectId(employee_doc_id)
    except Exception:
        flash("Invalid employee ID format.", "danger")
        return redirect(url_for('users.list_users'))

    employee = db.employees.find_one({"_id": obj_id})
    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for('users.list_users'))

    # submitted_data is used to repopulate form on validation error or GET
    submitted_data = request.form if request.method == 'POST' else employee

    if request.method == 'POST':
        new_display_name = request.form.get('display_name', '').strip()
        new_status = request.form.get('status', employee.get('status', 'active'))
        errors = {}
        if not new_display_name: errors['display_name'] = "Display name cannot be empty."
        valid_statuses = ["active", "pending_rename", "inactive", "disabled"]
        if new_status not in valid_statuses:
            errors['status'] = "Invalid status selected."
            new_status = employee.get('status', 'active') # Revert to original if invalid

        if errors:
            flash("Please correct the errors below.", "warning")
            return render_template('user_edit.html',
                                   employee=employee, # Original employee data for context
                                   form_errors=errors,
                                   submitted_data=request.form, # Show user's attempted changes
                                   active_page='users')

        update_data = {"display_name": new_display_name, "status": new_status}
        try:
            result = db.employees.update_one({"_id": obj_id}, {"$set": update_data})
            if result.modified_count > 0:
                flash(f"Employee '{new_display_name}' updated successfully.", "success")
            elif employee.get('display_name') == new_display_name and employee.get('status') == new_status:
                flash(f"No changes detected for employee '{new_display_name}'.", "info")
            else:
                flash(f"Employee '{new_display_name}' update reported no changes, please check.", "warning")
            return redirect(url_for('users.list_users'))
        except Exception as e:
             flash(f"Database error updating employee: {e}", "danger")
             return render_template('user_edit.html',
                                   employee=employee, submitted_data=request.form, active_page='users')

    # For GET request
    return render_template('user_edit.html',
                           employee=employee, # Pass current employee data
                           submitted_data=employee, # For initial form population
                           active_page='users')