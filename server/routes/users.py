# /root/EMS/server/routes/users.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app, session
)
from models.db import get_db
from routes.auth import login_required # g might be implicitly used here
from bson import ObjectId # For converting string ID back to ObjectId
import datetime # Not strictly used in this version but good to have for future features

users_bp = Blueprint('users', __name__)

USERS_PER_PAGE = 15 # Configuration for pagination, can be moved to Flask app config

@users_bp.route('/')
@login_required # Ensures only logged-in admins can access
def list_users():
    """Displays a list of all employees with search and pagination."""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    skip_count = (page - 1) * USERS_PER_PAGE
    
    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status_filter', '').strip() # For direct status filtering

    filter_criteria = {}

    if search_query:
        # Case-insensitive search on display_name or employee_id
        # If status_filter is also a search term, it will be part of $or
        regex_query = {"$regex": search_query, "$options": "i"}
        search_or_conditions = [
            {"display_name": regex_query},
            {"employee_id": regex_query}
        ]
        # Allow searching for status text as well
        if search_query.lower() in ["active", "inactive", "pending_rename", "disabled", "pending"]:
            search_or_conditions.append({"status": {"$regex": f"^{search_query}$", "$options": "i"}}) # Exact match for status search
        
        filter_criteria["$or"] = search_or_conditions

    if status_filter: # If a specific status filter is applied (e.g., from sidebar link)
        filter_criteria["status"] = status_filter


    employees = []
    total_users = 0
    pending_rename_count = 0 # For sidebar consistency

    try:
        total_users = db.employees.count_documents(filter_criteria)
        employees_cursor = db.employees.find(filter_criteria).sort([
            ("status", 1), # Sort by status first (e.g., pending on top)
            ("display_name", 1)
        ]).skip(skip_count).limit(USERS_PER_PAGE)
        employees = list(employees_cursor)
        
        # Get pending rename count for the sidebar (independent of current page filter)
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})

    except Exception as e:
        current_app.logger.error(f"Error fetching user list: {e}", exc_info=True)
        flash("Could not retrieve user list from the database.", "danger")
        # Ensure variables are initialized even on error
        total_users, employees, pending_rename_count = 0, [], 0


    total_pages = (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE if USERS_PER_PAGE > 0 else 0

    return render_template('users.html',
                           employees=employees,
                           pending_rename_count=pending_rename_count,
                           active_page='users', # For sidebar highlighting
                           current_page=page,
                           total_pages=total_pages,
                           search_query=search_query,
                           status_filter=status_filter)


@users_bp.route('/edit/<employee_doc_id>', methods=['GET', 'POST'])
@login_required
def edit_user(employee_doc_id):
    """Handles editing of an employee's details (name, status)."""
    db = get_db()
    try:
        obj_id = ObjectId(employee_doc_id)
    except Exception: # Handles InvalidId from bson.ObjectId
        flash("Invalid employee ID format provided.", "danger")
        return redirect(url_for('users.list_users'))

    employee = db.employees.find_one({"_id": obj_id})
    if not employee:
        flash("Employee not found with the given ID.", "danger")
        return redirect(url_for('users.list_users'))

    # For repopulating form on error or for GET request
    # On GET, submitted_data will be the current employee data
    # On POST error, it will be request.form
    submitted_data = request.form if request.method == 'POST' else employee
    form_errors = {} # To pass specific field errors to template

    if request.method == 'POST':
        new_display_name = request.form.get('display_name', '').strip()
        new_status = request.form.get('status', employee.get('status', 'active'))

        if not new_display_name:
            form_errors['display_name'] = "Display name cannot be empty."
        
        valid_statuses = ["active", "pending_rename", "inactive", "disabled"]
        if new_status not in valid_statuses:
            form_errors['status'] = "Invalid status selected."
            new_status = employee.get('status', 'active') # Revert on error

        if form_errors:
            flash("Please correct the errors in the form.", "warning")
            # Re-render the edit form with errors and submitted data
            pending_rename_count = db.employees.count_documents({"status": "pending_rename"}) # For layout
            return render_template('users_edit.html', # Assuming template is users_edit.html
                                   employee=employee, # Original employee for context
                                   form_errors=form_errors,
                                   submitted_data=request.form,
                                   active_page='users',
                                   pending_rename_count=pending_rename_count)

        update_data = {
            "display_name": new_display_name,
            "status": new_status,
            "updated_at": datetime.datetime.now(datetime.timezone.utc) # Track updates
        }
        try:
            result = db.employees.update_one({"_id": obj_id}, {"$set": update_data})
            if result.modified_count > 0:
                flash(f"Employee '{new_display_name}' updated successfully.", "success")
                current_app.logger.info(
                    f"Admin '{session.get('username', 'unknown')}' updated employee {employee_doc_id} "
                    f"(ID: {employee.get('employee_id')}) to name '{new_display_name}' and status '{new_status}'"
                )
            elif employee.get('display_name') == new_display_name and employee.get('status') == new_status:
                flash(f"No changes detected for employee '{new_display_name}'.", "info")
            else: # Data was different but modified_count is 0 (should be rare)
                flash(f"Update for '{new_display_name}' reported no changes, though data submitted was different. Please verify.", "warning")
            return redirect(url_for('users.list_users'))

        except Exception as e:
             flash(f"Database error updating employee: {str(e)}", "danger")
             current_app.logger.error(f"Error updating employee {employee_doc_id}: {e}", exc_info=True)
             # Re-render form, keeping submitted data
             pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
             return render_template('users_edit.html',
                                   employee=employee,
                                   submitted_data=request.form, # Show their attempted changes
                                   form_errors={"general": "A database error occurred."}, # Generic error
                                   active_page='users',
                                   pending_rename_count=pending_rename_count)

    # For GET request, prepare data to pass to template
    pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    return render_template('users_edit.html', # Changed from user_edit.html to users_edit.html
                           employee=employee,
                           submitted_data=employee, # For initial form population
                           form_errors=form_errors, # Will be empty on GET
                           active_page='users',
                           pending_rename_count=pending_rename_count)