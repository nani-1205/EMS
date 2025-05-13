# /root/EMS/server/routes/reports.py
from flask import (
    Blueprint, render_template, request, current_app, session,
    send_from_directory, abort, flash, redirect, url_for
)
from routes.auth import login_required
from models.db import get_db
from bson import ObjectId
import datetime
from dateutil.relativedelta import relativedelta
import os

reports_bp = Blueprint('reports', __name__)

REPORTS_PER_PAGE = 20
SCREENSHOTS_PER_PAGE = 12

def get_report_date_range(start_str=None, end_str=None):
    end_date = datetime.datetime.now(datetime.timezone.utc)
    start_date = end_date - relativedelta(days=6)
    if start_str and end_str:
        try:
            parsed_start_date = datetime.datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            parsed_end_date = datetime.datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            if parsed_end_date >= parsed_start_date:
                start_date = parsed_start_date
                end_date = parsed_end_date
            else:
                flash("End date cannot be before start date. Using default range.", "warning")
        except ValueError:
            flash("Invalid date format for report. Using default range.", "warning")
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start_date, end_date

@reports_bp.route('/')
@login_required
def index():
    """Main reports landing page that lists available reports."""
    db = get_db()
    pending_rename_count = 0
    try:
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching pending_rename_count for reports index: {e}")
        # Continue, pending_rename_count will be 0

    return render_template('reports/index.html',
                           active_page='reports',
                           pending_rename_count=pending_rename_count)


@reports_bp.route('/activity_log', methods=['GET'])
@login_required
def activity_log_report():
    db = get_db()
    employees = []
    pending_rename_count = 0
    try:
        employees = list(db.employees.find({}, {"employee_id": 1, "display_name": 1}).sort("display_name", 1))
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching employee data for activity log report: {e}")
        flash("Could not load employee data.", "danger")

    selected_employee_id = request.args.get('employee_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    skip_count = (page - 1) * REPORTS_PER_PAGE

    start_date, end_date = get_report_date_range(start_date_str, end_date_str)
    filter_criteria = {"timestamp": {"$gte": start_date, "$lte": end_date}}

    if selected_employee_id:
        filter_criteria["employee_id"] = selected_employee_id
    else: # If no employee selected, don't show 'all' unless explicitly desired and handled
        filter_criteria["employee_id"] = None # Effectively no results if not selected

    activity_logs = []
    total_logs = 0
    if selected_employee_id:
        try:
            # Ensure log_type is not screenshot for activity logs
            filter_criteria["log_type"] = {"$ne": "screenshot"}
            total_logs = db.activity_logs.count_documents(filter_criteria)
            activity_logs = list(db.activity_logs.find(filter_criteria)
                                 .sort("timestamp", -1)
                                 .skip(skip_count)
                                 .limit(REPORTS_PER_PAGE))
        except Exception as e:
            current_app.logger.error(f"Error fetching activity logs for report: {e}")
            flash("Error retrieving activity logs.", "danger")
    elif not selected_employee_id and (start_date_str or end_date_str):
        flash("Please select an employee to view their activity log.", "info")


    total_pages = (total_logs + REPORTS_PER_PAGE - 1) // REPORTS_PER_PAGE

    return render_template('reports/activity_log.html',
                           employees=employees,
                           selected_employee_id=selected_employee_id,
                           activity_logs=activity_logs,
                           start_date_str=start_date.strftime('%Y-%m-%d'),
                           end_date_str=end_date.strftime('%Y-%m-%d'),
                           current_page=page,
                           total_pages=total_pages,
                           active_page='reports',
                           pending_rename_count=pending_rename_count)


@reports_bp.route('/screenshots', methods=['GET'])
@login_required
def screenshot_report():
    db = get_db()
    employees = []
    pending_rename_count = 0
    try:
        employees = list(db.employees.find({}, {"employee_id": 1, "display_name": 1}).sort("display_name", 1))
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching employee data for screenshot report: {e}")
        flash("Could not load employee data.", "danger")

    selected_employee_id = request.args.get('employee_id')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    skip_count = (page - 1) * SCREENSHOTS_PER_PAGE

    start_date, end_date = get_report_date_range(start_date_str, end_date_str)
    filter_criteria = {
        "timestamp": {"$gte": start_date, "$lte": end_date},
        "log_type": "screenshot",
        "screenshot_path": {"$exists": True}
    }

    if selected_employee_id:
        filter_criteria["employee_id"] = selected_employee_id
    else: # If no employee selected, don't show 'all' unless explicitly desired and handled
        filter_criteria["employee_id"] = None # Effectively no results if not selected

    screenshots = []
    total_screenshots = 0
    if selected_employee_id:
        try:
            total_screenshots = db.activity_logs.count_documents(filter_criteria)
            screenshots = list(db.activity_logs.find(filter_criteria)
                               .sort("timestamp", -1)
                               .skip(skip_count)
                               .limit(SCREENSHOTS_PER_PAGE))
        except Exception as e:
            current_app.logger.error(f"Error fetching screenshots for report: {e}")
            flash("Error retrieving screenshots.", "danger")
    elif not selected_employee_id and (start_date_str or end_date_str):
        flash("Please select an employee to view their screenshots.", "info")

    total_pages = (total_screenshots + SCREENSHOTS_PER_PAGE - 1) // SCREENSHOTS_PER_PAGE

    return render_template('reports/screenshots.html',
                           employees=employees,
                           selected_employee_id=selected_employee_id,
                           screenshots=screenshots,
                           start_date_str=start_date.strftime('%Y-%m-%d'),
                           end_date_str=end_date.strftime('%Y-%m-%d'),
                           current_page=page,
                           total_pages=total_pages,
                           active_page='reports',
                           pending_rename_count=pending_rename_count)


@reports_bp.route('/view_screenshot/<path:filename>')
@login_required
def view_screenshot(filename):
    if '..' in filename or filename.startswith('/') or filename.startswith('\\') or '\0' in filename:
        current_app.logger.warning(f"Attempted invalid path for screenshot: {filename} by user {session.get('username')}")
        abort(404)
    screenshot_dir = current_app.config['UPLOAD_FOLDER']
    db = get_db()
    log_entry = db.activity_logs.find_one({"screenshot_path": filename, "log_type": "screenshot"})
    if not log_entry:
        current_app.logger.warning(f"Screenshot not found in logs or access denied for filename: {filename} (User: {session.get('username')})")
        abort(404)
    full_file_path = os.path.join(screenshot_dir, filename)
    if not os.path.isfile(full_file_path):
        current_app.logger.error(f"Screenshot file missing on disk but present in logs: {full_file_path} (User: {session.get('username')})")
        abort(404)
    try:
        current_app.logger.info(f"Serving screenshot: {filename} to user {session.get('username')}")
        return send_from_directory(screenshot_dir, filename)
    except FileNotFoundError:
        current_app.logger.error(f"send_from_directory could not find screenshot: {filename} in {screenshot_dir}")
        abort(404)
    except Exception as e:
        current_app.logger.error(f"Unexpected error serving screenshot {filename}: {e}")
        abort(500)