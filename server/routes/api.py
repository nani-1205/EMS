# /root/EMS/server/routes/api.py
from flask import Blueprint, request, jsonify, current_app, abort, send_from_directory, session # Added session
from models.db import get_db, create_employee
from routes.auth import login_required # For potential securing of new endpoint
import datetime
import os
import uuid

api_bp = Blueprint('api', __name__)

def verify_api_key():
    """Checks if the request has a valid API key."""
    provided_key = request.headers.get('X-API-KEY')
    if not provided_key or provided_key != current_app.config['AGENT_API_KEY']:
        current_app.logger.warning(f"Unauthorized API access attempt. Provided key: {provided_key}")
        abort(401, description="Unauthorized: Invalid or missing API key.")

@api_bp.before_request
def before_api_request():
    """Verify API key for all API routes, except for specific public/admin endpoints."""
    # List of endpoints that do NOT require an agent API key (e.g., admin-facing or public)
    endpoints_without_agent_key = ['api.get_active_employees', 'api.download_agent_exe']

    if request.endpoint not in endpoints_without_agent_key:
         verify_api_key()
    # For 'api.get_active_employees', we might want admin login instead, handled by @login_required
    # For 'api.download_agent_exe', ensure it's properly secured via @login_required

@api_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Agent checks in, reports status, potentially gets commands."""
    data = request.json
    employee_id = data.get('employee_id')
    hostname = data.get('hostname')

    if not employee_id:
        return jsonify({"status": "error", "message": "Missing employee_id"}), 400

    db = get_db()
    employee_doc_id = create_employee(db, employee_id, initial_name=hostname) # Pass hostname as initial name

    current_app.logger.info(f"Heartbeat received from: {employee_id} ({hostname})")
    return jsonify({"status": "ok", "message": "Heartbeat received"}), 200

@api_bp.route('/log/activity', methods=['POST'])
def log_activity():
    """Agent sends activity data (window title, duration, etc.)."""
    data = request.json
    employee_id = data.get('employee_id')
    activities = data.get('activities')

    if not employee_id or not activities:
        return jsonify({"status": "error", "message": "Missing employee_id or activities"}), 400

    db = get_db()
    now = datetime.datetime.now(datetime.timezone.utc)
    activity_docs = []
    for act in activities:
        try:
            start_time = datetime.datetime.fromisoformat(act.get("start_time"))
            end_time = datetime.datetime.fromisoformat(act.get("end_time"))
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid ISO format for activity times from {employee_id}. Skipping activity.")
            continue

        activity_docs.append({
            "employee_id": employee_id,
            "timestamp": now,
            "window_title": act.get("window_title"),
            "process_name": act.get("process_name"),
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": act.get("duration_seconds"),
            "is_active": act.get("is_active", True),
        })

    if activity_docs:
        try:
            result = db.activity_logs.insert_many(activity_docs)
            db.employees.update_one(
                {"employee_id": employee_id},
                {"$set": {"last_seen": now}}
            )
            current_app.logger.info(f"Logged {len(result.inserted_ids)} activities for {employee_id}")
            return jsonify({"status": "ok", "message": f"Logged {len(result.inserted_ids)} activities"}), 201
        except Exception as e:
             current_app.logger.error(f"Error inserting activity logs for {employee_id}: {e}")
             return jsonify({"status": "error", "message": "Database error logging activity"}), 500
    else:
         return jsonify({"status": "ok", "message": "No valid activities to log"}), 200


@api_bp.route('/upload/screenshot', methods=['POST'])
def upload_screenshot():
    """Agent uploads a captured screenshot."""
    if 'screenshot' not in request.files:
        return jsonify({"status": "error", "message": "No screenshot file part"}), 400

    file = request.files['screenshot']
    employee_id = request.form.get('employee_id')
    timestamp_str = request.form.get('timestamp')

    if not employee_id or not timestamp_str:
         return jsonify({"status": "error", "message": "Missing employee_id or timestamp"}), 400
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file:
        db = get_db()
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
        except ValueError:
             return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400

        filename_timestamp = timestamp.strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{filename_timestamp}_{employee_id}_{unique_id}.png"
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

        try:
            file.save(save_path)
            current_app.logger.info(f"Screenshot saved for {employee_id} at {timestamp_str} to {filename}")
            db.activity_logs.insert_one({
                "employee_id": employee_id,
                "timestamp": timestamp,
                "log_type": "screenshot",
                "screenshot_path": filename,
            })
            db.employees.update_one(
                {"employee_id": employee_id},
                {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}}
            )
            return jsonify({"status": "ok", "message": "Screenshot uploaded successfully"}), 201
        except Exception as e:
            current_app.logger.error(f"Error saving screenshot for {employee_id}: {e}")
            return jsonify({"status": "error", "message": f"Could not save file: {e}"}), 500
    return jsonify({"status": "error", "message": "File processing error"}), 500

@api_bp.route('/download/agent')
@login_required # Requires admin to be logged in to download
def download_agent_exe():
    """Provides the agent executable for download by admin."""
    agent_path = current_app.config['AGENT_EXE_PATH']
    agent_dir = os.path.dirname(agent_path)
    agent_filename = os.path.basename(agent_path)

    if os.path.exists(agent_path):
        current_app.logger.info(f"Admin '{session.get('username', 'unknown')}' downloading agent: {agent_filename}")
        return send_from_directory(directory=agent_dir, path=agent_filename, as_attachment=True, download_name="monitoring_agent.exe")
    else:
        current_app.logger.error(f"Agent file not found at: {agent_path} for download request.")
        flash("Agent executable not found on server. Please build it first.", "danger")
        # Redirect to a relevant page, e.g., dashboard or a settings page
        return redirect(request.referrer or url_for('dashboard.view_dashboard'))


# --- New Endpoint for Active Employees (Polling) ---
@api_bp.route('/active_employees', methods=['GET'])
@login_required # Only logged-in admins can access this
def get_active_employees():
    """Returns a list of recently active employees for the sidebar."""
    db = get_db()
    # Define "active" as seen in the last 5 minutes (adjust as needed)
    active_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)

    try:
        active_emps = list(db.employees.find(
            {
                "last_seen": {"$gte": active_threshold},
                "status": {"$in": ["active", "pending_rename"]} # Consider which statuses mean "online"
            },
            {"_id": 1, "display_name": 1, "employee_id": 1} # Fetch _id for potential links
        ).sort("display_name", 1).limit(15)) # Limit the number for the sidebar

        # Convert ObjectId to string for JSON serialization
        for emp in active_emps:
            emp['_id'] = str(emp['_id'])

        return jsonify(active_emps)
    except Exception as e:
        current_app.logger.error(f"Error fetching active employees: {e}")
        return jsonify({"error": "Could not retrieve active employees"}), 500