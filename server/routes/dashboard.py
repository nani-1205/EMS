# /root/EMS/server/routes/dashboard.py
from flask import Blueprint, render_template, session, request, current_app
from routes.auth import login_required # g might be implicitly used by this decorator
from models.db import get_db
import datetime
from dateutil.relativedelta import relativedelta

dashboard_bp = Blueprint('dashboard', __name__)

def get_date_range(period='day', start_str=None, end_str=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date, end_date = None, None

    if period == 'custom' and start_str and end_str:
        try:
            start_date = datetime.datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            end_date = datetime.datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            if end_date < start_date: # Ensure end_date is not before start_date
                current_app.logger.warning(f"Custom date range error: end_date before start_date. Reverting to 'day'.")
                period = 'day' # Fallback
        except ValueError:
            current_app.logger.warning(f"Invalid custom date format: start={start_str}, end={end_str}. Falling back to 'day'.")
            period = 'day'

    if period == 'week':
        start_date = now - relativedelta(days=now.weekday()) # Monday of current week
        end_date = start_date + relativedelta(days=6)      # Sunday of current week
    elif period == 'month':
        start_date = now.replace(day=1)
        end_date = (start_date + relativedelta(months=1)) - relativedelta(days=1) # Last day of current month
    elif period == 'day': # Default or fallback
        start_date = now # Today
        end_date = now   # Today, time will be adjusted below

    # Ensure start_date and end_date are set if the above logic somehow missed a case
    if start_date is None: start_date = now
    if end_date is None: end_date = now

    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start_date, end_date

def format_seconds(total_seconds):
    if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
        return "00:00:00"
    total_seconds = int(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

@dashboard_bp.route('/dashboard')
@login_required
def view_dashboard():
    db = get_db()

    selected_period = request.args.get('period', 'day')
    custom_start_str = request.args.get('start')
    custom_end_str = request.args.get('end')
    selected_employee_id = request.args.get('employee_id')
    if selected_employee_id == 'all' or not selected_employee_id: # Treat empty or 'all' as no filter
        selected_employee_id = None

    start_date, end_date = get_date_range(selected_period, custom_start_str, custom_end_str)
    current_app.logger.info(f"Dashboard: Period='{selected_period}', Employee='{selected_employee_id or 'All'}', Range: {start_date} to {end_date}")

    filter_employees_list = []
    pending_rename_count = 0
    try:
        filter_employees_list = list(db.employees.find({}, {"employee_id": 1, "display_name": 1, "_id": 0}).sort("display_name", 1))
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching base employee data for dashboard: {e}")
        # Continue with empty list / 0 count

    base_match_criteria = {"timestamp": {"$gte": start_date, "$lte": end_date}}
    if selected_employee_id:
        base_match_criteria["employee_id"] = selected_employee_id

    # 1. Member Counts (Overall, not filtered by selected_employee_id for these specific cards)
    team_members_count = db.employees.count_documents({})
    tracked_members_count = db.employees.count_documents({"status": {"$nin": ["inactive", "disabled"]}})

    # 2. Average Start Time (Filtered by selected_employee_id if provided)
    avg_start_match = {"start_time": {"$gte": start_date, "$lte": end_date}} # Filter by activity start time
    if selected_employee_id:
        avg_start_match["employee_id"] = selected_employee_id

    avg_start_pipeline = [
        {"$match": avg_start_match},
        {"$group": {"_id": {"employee_id": "$employee_id", "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$start_time", "timezone": "UTC"}}}, "first_activity_time": {"$min": "$start_time"}}},
        {"$project": {"_id": 0, "start_hour": {"$hour": {"date": "$first_activity_time", "timezone": "UTC"}}, "start_minute": {"$minute": {"date": "$first_activity_time", "timezone": "UTC"}}}},
        {"$group": {"_id": None, "avg_hour": {"$avg": "$start_hour"}, "avg_minute": {"$avg": "$start_minute"}}}
    ]
    avg_start_time_str = "N/A"
    try:
        avg_start_result = list(db.activity_logs.aggregate(avg_start_pipeline))
        if avg_start_result and avg_start_result[0].get('avg_hour') is not None:
            avg_h = int(avg_start_result[0]['avg_hour'])
            avg_m = int(avg_start_result[0]['avg_minute'])
            avg_start_time_str = f"{avg_h:02d}:{avg_m:02d}"
        else:
             current_app.logger.info(f"Could not calculate average start time for selection (Employee: {selected_employee_id or 'All'}).")
    except Exception as e:
        current_app.logger.error(f"Error in Avg Start Time aggregation: {e}")


    # 3. Working Time (Filtered by selected_employee_id if provided)
    working_time_match = {**base_match_criteria, "duration_seconds": {"$exists": True, "$gt": 0}}
    work_time_pipeline = [
        {"$match": working_time_match},
        {"$group": {"_id": None, "total_duration": {"$sum": "$duration_seconds"}}}
    ]
    working_time_str = "00:00:00"
    team_working_time_label = "Team Working Time" if not selected_employee_id else "Selected User Working Time"
    try:
        work_time_result = list(db.activity_logs.aggregate(work_time_pipeline))
        if work_time_result and work_time_result[0].get('total_duration'):
            working_time_str = format_seconds(work_time_result[0].get('total_duration', 0))
    except Exception as e:
        current_app.logger.error(f"Error in Working Time aggregation: {e}")


    # 4. Latest Activity Seen (Filtered by selected_employee_id if provided)
    latest_seen_filter = {"last_seen": {"$exists": True}}
    if selected_employee_id:
        latest_seen_filter["employee_id"] = selected_employee_id
    
    latest_activity_seen_str = "N/A"
    try:
        latest_seen_employee = db.employees.find_one(latest_seen_filter, sort=[("last_seen", -1)])
        if latest_seen_employee and latest_seen_employee.get('last_seen'):
            # Check if the latest activity is within the currently viewed date range for relevance
            if start_date <= latest_seen_employee['last_seen'] <= end_date:
                 latest_activity_seen_str = latest_seen_employee['last_seen'].strftime("%H:%M")
    except Exception as e:
        current_app.logger.error(f"Error fetching Latest Activity Seen: {e}")


    # 5. Top 5 Websites/Applications (Filtered by selected_employee_id if provided)
    top_sites_match = {**base_match_criteria, "duration_seconds": {"$exists": True, "$gt": 0}, "$or": [{"window_title": {"$exists": True, "$ne": ""}}, {"process_name": {"$exists": True, "$ne": ""}}]}
    top_sites_pipeline = [
        {"$match": top_sites_match},
        {"$project": {"activity_name": {"$ifNull": ["$window_title", "$process_name"]}, "duration_seconds": 1}},
        {"$group": {"_id": "$activity_name", "total_duration": {"$sum": "$duration_seconds"}}},
        {"$sort": {"total_duration": -1}}, {"$limit": 5}
    ]
    top_websites_data = []
    try:
        top_sites_result = list(db.activity_logs.aggregate(top_sites_pipeline))
        top_websites_data = [{"name": item['_id'] if item['_id'] else "Unknown", "duration": item.get('total_duration',0)} for item in top_sites_result]
        if not top_websites_data:
            current_app.logger.info(f"No activity found for Top 5 Websites/Apps for selection (Employee: {selected_employee_id or 'All'}).")
    except Exception as e:
        current_app.logger.error(f"Error in Top Websites aggregation: {e}")

    # 6. Work Hours (Total) Table (Filtered by selected_employee_id if provided)
    work_hours_match = {**base_match_criteria, "duration_seconds": {"$exists": True, "$gt": 0}}
    work_hours_pipeline = [
        {"$match": work_hours_match},
        {"$group": {"_id": "$employee_id", "total_seconds": {"$sum": "$duration_seconds"}, "unique_days": {"$addToSet": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp", "timezone": "UTC"}}}}},
        {"$lookup": {"from": "employees", "localField": "_id", "foreignField": "employee_id", "as": "employee_info"}},
        {"$unwind": {"path": "$employee_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {"_id": 0, "employee_id": "$_id", "display_name": "$employee_info.display_name", "total_seconds": 1, "man_days": {"$size": "$unique_days"}}},
        {"$sort": {"display_name": 1}}
    ]
    work_hours_data_list = []
    try:
        work_hours_result = list(db.activity_logs.aggregate(work_hours_pipeline))
        for item in work_hours_result:
             work_hours_data_list.append({
                "name": item.get("display_name", item.get("employee_id", "Unknown")),
                "employee_id": item.get("employee_id", "Unknown"),
                "man_days": item.get("man_days", 0),
                "work_hours": format_seconds(item.get('total_seconds',0))
            })
    except Exception as e:
        current_app.logger.error(f"Error in Work Hours aggregation: {e}")


    return render_template('dashboard.html',
                           username=session.get('username'),
                           avg_start_time=avg_start_time_str,
                           team_working_time=working_time_str,
                           team_working_time_label=team_working_time_label,
                           avg_last_seen=latest_activity_seen_str,
                           team_members_count=team_members_count,
                           tracked_members_count=tracked_members_count,
                           top_websites=top_websites_data,
                           work_hours_data=work_hours_data_list,
                           filter_employees_list=filter_employees_list,
                           pending_rename_count=pending_rename_count,
                           active_page='dashboard',
                           selected_period=selected_period,
                           selected_employee_id=selected_employee_id, # Pass this back to pre-select dropdown
                           start_date_str=start_date.strftime("%Y-%m-%d"),
                           end_date_str=end_date.strftime("%Y-%m-%d"))