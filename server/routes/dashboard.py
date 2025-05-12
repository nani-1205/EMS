from flask import Blueprint, render_template, session, redirect, url_for, current_app
from routes.auth import login_required
from models.db import get_db
from bson import ObjectId # To query by ObjectId if needed
import datetime

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def view_dashboard():
    db = get_db()
    user_id = session['user_id']
    user = db.users.find_one({"_id": ObjectId(user_id)}) # Fetch current user details if needed

    # --- Fetch Data for Dashboard Widgets ---
    # This needs more complex aggregation queries in MongoDB

    # Example: Get employee list (replace with actual data fetching)
    employees = list(db.employees.find().sort("employee_id", 1))

    # Calculate stats (These are placeholders - requires real aggregation)
    # You'd use MongoDB aggregation pipeline for efficiency
    avg_start_time = "11:59" # Placeholder
    team_working_time = "00:23" # Placeholder
    avg_last_seen = "13:29" # Placeholder
    team_members_count = db.employees.count_documents({})
    tracked_members_count = db.employees.count_documents({"status": {"$ne": "inactive"}}) # Example: count active

    # Top websites (Placeholder - Requires aggregation on activity_logs)
    top_websites = [
        {"name": "www.youtube.com", "duration": 12},
        {"name": "SearchHost.exe", "duration": 4},
        {"name": "Microsoft Edge", "duration": 2},
        # ... more data
    ]

    # Work Hours (Placeholder - Requires aggregation on activity_logs)
    work_hours_data = []
    for emp in employees:
        work_hours_data.append({
            "name": emp.get("display_name", emp["employee_id"]),
            "employee_id": emp["employee_id"],
            "man_days": 1, # Placeholder calculation
            "work_hours": "00:00" # Placeholder calculation
        })

    # Check for users needing rename
    pending_rename_count = db.employees.count_documents({"status": "pending_rename"})

    return render_template('dashboard.html',
                           username=session.get('username'),
                           avg_start_time=avg_start_time,
                           team_working_time=team_working_time,
                           avg_last_seen=avg_last_seen,
                           team_members_count=team_members_count,
                           tracked_members_count=tracked_members_count,
                           top_websites=top_websites,
                           work_hours_data=work_hours_data,
                           employees=employees, # Pass full employee list for sidebar
                           pending_rename_count=pending_rename_count, # For notification
                           active_page='dashboard') # For sidebar highlighting