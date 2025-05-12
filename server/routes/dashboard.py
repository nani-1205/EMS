# /root/EMS/server/routes/dashboard.py

from flask import Blueprint, render_template, session, redirect, url_for, current_app, request, g
from routes.auth import login_required # Make sure login_required imports g
from models.db import get_db
from bson import ObjectId
import datetime
from dateutil.relativedelta import relativedelta # For date calculations (pip install python-dateutil)

dashboard_bp = Blueprint('dashboard', __name__)

# --- Helper Function for Date Ranges (Example) ---
def get_date_range(period='day'):
    now = datetime.datetime.now(datetime.timezone.utc)
    if period == 'week':
        start_date = now - relativedelta(days=now.weekday()) # Start of current week (Monday)
        end_date = start_date + relativedelta(days=6)
    elif period == 'month':
        start_date = now.replace(day=1)
        end_date = (start_date + relativedelta(months=1)) - relativedelta(days=1)
    else: # Default to 'day'
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + relativedelta(days=1) - relativedelta(microseconds=1)

    # Ensure start/end are timezone-aware if 'now' is
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_date, end_date

# --- Helper Function for Time Formatting ---
def format_seconds(total_seconds):
    if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
        return "00:00:00"
    hours, remainder = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

@dashboard_bp.route('/dashboard')
@login_required
def view_dashboard():
    db = get_db()
    # user_id = session['user_id'] # Already available via g.user from login_required
    # user = db.users.find_one({"_id": ObjectId(user_id)}) # Or use g.user if set

    # --- Date Range (Get from query param, default to 'day') ---
    selected_period = request.args.get('period', 'day')
    start_date, end_date = get_date_range(selected_period)
    current_app.logger.info(f"Dashboard period: {selected_period}, Range: {start_date} to {end_date}")

    # --- Fetch Base Data ---
    employees = list(db.employees.find().sort("display_name", 1))
    pending_rename_count = db.employees.count_documents({"status": "pending_rename"})

    # --- CALCULATE STATS (Replace Placeholders) ---

    # 1. Member Counts
    team_members_count = db.employees.count_documents({})
    # Adjust tracked members based on your definition (e.g., not 'inactive' or seen within range)
    tracked_members_count = db.employees.count_documents({
        "status": {"$nin": ["inactive", "disabled"]}, # Example: exclude inactive/disabled
        # Optionally filter by last_seen within the date range?
        # "last_seen": {"$gte": start_date, "$lte": end_date}
    })

    # 2. Average Start Time (More Complex - requires aggregation)
    # Find the earliest 'start_time' for each employee within the date range
    avg_start_pipeline = [
        {"$match": {"timestamp": {"$gte": start_date, "$lte": end_date}}},
        {"$sort": {"employee_id": 1, "start_time": 1}},
        {"$group": {
            "_id": "$employee_id",
            "first_activity": {"$first": "$start_time"}
        }},
        {"$project": {
            "start_hour": {"$hour": "$first_activity"},
            "start_minute": {"$minute": "$first_activity"}
        }},
        {"$group": {
            "_id": None,
            "avg_hour": {"$avg": "$start_hour"},
            "avg_minute": {"$avg": "$start_minute"}
        }}
    ]
    avg_start_result = list(db.activity_logs.aggregate(avg_start_pipeline))
    avg_start_time_str = "N/A"
    if avg_start_result and avg_start_result[0]['avg_hour'] is not None:
        avg_h = int(avg_start_result[0]['avg_hour'])
        avg_m = int(avg_start_result[0]['avg_minute'])
        avg_start_time_str = f"{avg_h:02d}:{avg_m:02d}"
    else:
         current_app.logger.warning("Could not calculate average start time.")


    # 3. Team Working Time (Sum of durations within range)
    work_time_pipeline = [
        {"$match": {
            "timestamp": {"$gte": start_date, "$lte": end_date},
            "duration_seconds": {"$exists": True, "$gt": 0},
            # Optional: Add filter for "is_active": True if you track idle time
        }},
        {"$group": {
            "_id": None, # Group all results together
            "total_duration": {"$sum": "$duration_seconds"}
        }}
    ]
    work_time_result = list(db.activity_logs.aggregate(work_time_pipeline))
    team_working_time_str = "00:00:00"
    if work_time_result:
        team_working_time_str = format_seconds(work_time_result[0].get('total_duration', 0))

    # 4. Average Last Seen (From employees collection, potentially filtered)
    # Simple average of all 'last_seen' timestamps (might not be meaningful)
    # More useful: Show *latest* last_seen or count active in last X minutes
    latest_seen_pipeline = [
        {"$match": {"last_seen": {"$exists": True}}}, # Only employees ever seen
        {"$sort": {"last_seen": -1}},
        {"$limit": 1}
    ]
    latest_employee = list(db.employees.aggregate(latest_seen_pipeline))
    latest_seen_time_str = "N/A"
    if latest_employee and latest_employee[0].get('last_seen'):
        # Format the latest seen time (e.g., HH:MM or relative time)
        latest_seen_dt = latest_employee[0]['last_seen']
        latest_seen_time_str = latest_seen_dt.strftime("%H:%M") # Just example H:M format
    avg_last_seen_str = latest_seen_time_str # Rename variable for clarity


    # 5. Top 5 Websites/Applications
    top_sites_pipeline = [
        {"$match": {
            "timestamp": {"$gte": start_date, "$lte": end_date},
            "duration_seconds": {"$exists": True, "$gt": 0},
            "$or": [ # Ensure we have a title or process name
                 {"window_title": {"$exists": True, "$ne": "", "$ne": None}},
                 {"process_name": {"$exists": True, "$ne": "", "$ne": None}}
            ]
        }},
        {"$project": { # Prioritize window_title, fallback to process_name
            "activity_name": {
                "$cond": {
                   "if": { "$and": [{"$ne": ["$window_title", None]}, {"$ne": ["$window_title", ""]}]},
                   "then": "$window_title",
                   "else": "$process_name"
                }
            },
            "duration_seconds": 1
        }},
        {"$group": {
            "_id": "$activity_name",
            "total_duration": {"$sum": "$duration_seconds"}
        }},
        {"$sort": {"total_duration": -1}},
        {"$limit": 5}
    ]
    top_sites_result = list(db.activity_logs.aggregate(top_sites_pipeline))
    top_websites_data = []
    if top_sites_result:
        for item in top_sites_result:
            top_websites_data.append({
                "name": item['_id'],
                "duration": item['total_duration'] # Keep as seconds for JS chart
            })
    else:
        current_app.logger.info("No activity found for Top 5 Websites/Apps.")


    # 6. Work Hours (Avg) Table
    # Calculate total work hours per employee in the range
    work_hours_pipeline = [
         {"$match": {
            "timestamp": {"$gte": start_date, "$lte": end_date},
            "duration_seconds": {"$exists": True, "$gt": 0},
        }},
        {"$group": {
            "_id": "$employee_id",
            "total_seconds": {"$sum": "$duration_seconds"},
            # Calculate unique days worked within the range if needed (more complex)
            "unique_days": {"$addToSet": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "UTC"}}}
        }},
        {"$lookup": { # Join with employees collection to get display name
            "from": "employees",
            "localField": "_id",
            "foreignField": "employee_id",
            "as": "employee_info"
        }},
        {"$unwind": {"path": "$employee_info", "preserveNullAndEmptyArrays": True}}, # Deconstruct the array
        {"$project": {
            "_id": 0,
            "employee_id": "$_id",
            "display_name": "$employee_info.display_name",
            "total_seconds": 1,
            "man_days": {"$size": "$unique_days"}
        }},
        {"$sort": {"display_name": 1}}
    ]
    work_hours_result = list(db.activity_logs.aggregate(work_hours_pipeline))
    work_hours_data_list = []
    if work_hours_result:
        for item in work_hours_result:
             # Calculate average if needed, otherwise just total
             avg_hours_str = format_seconds(item['total_seconds'])
             # avg_daily_seconds = item['total_seconds'] / item['man_days'] if item['man_days'] > 0 else 0
             # avg_hours_str = format_seconds(avg_daily_seconds)
             work_hours_data_list.append({
                "name": item.get("display_name", item["employee_id"]), # Fallback to ID
                "employee_id": item["employee_id"],
                "man_days": item.get("man_days", 0),
                "work_hours": avg_hours_str # Display total hours for the period
            })


    return render_template('dashboard.html',
                           username=session.get('username'),
                           # Pass calculated data
                           avg_start_time=avg_start_time_str,
                           team_working_time=team_working_time_str,
                           avg_last_seen=avg_last_seen_str, # Changed meaning to Latest Seen
                           team_members_count=team_members_count,
                           tracked_members_count=tracked_members_count,
                           top_websites=top_websites_data, # Pass dynamic data
                           work_hours_data=work_hours_data_list, # Pass dynamic data
                           # Pass base data
                           employees=employees, # For sidebar maybe? Limit this list.
                           pending_rename_count=pending_rename_count,
                           active_page='dashboard',
                           # Pass filter info
                           selected_period=selected_period,
                           start_date_str=start_date.strftime("%Y-%m-%d"),
                           end_date_str=end_date.strftime("%Y-%m-%d"))