from flask import Blueprint, request, jsonify, current_app, abort, send_from_directory
from models.db import get_db, create_employee
import datetime
import os
import uuid

api_bp = Blueprint('api', __name__)

def verify_api_key():
    """Checks if the request has a valid API key."""
    provided_key = request.headers.get('X-API-KEY')
    if not provided_key or provided_key != current_app.config['AGENT_API_KEY']:
        abort(401, description="Unauthorized: Invalid or missing API key.")

@api_bp.before_request
def before_api_request():
    """Verify API key for all API routes."""
    # Skip key verification for agent download if you want it public/login-based
    if request.endpoint != 'api.download_agent_exe':
         verify_api_key()

@api_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Agent checks in, reports status, potentially gets commands."""
    data = request.json
    employee_id = data.get('employee_id')
    hostname = data.get('hostname') # Good to log which machine

    if not employee_id:
        return jsonify({"status": "error", "message": "Missing employee_id"}), 400

    db = get_db()
    # Ensure employee exists, create if not (handle potential race conditions if needed)
    employee_doc_id = create_employee(db, employee_id) # This also updates last_seen

    print(f"Heartbeat received from: {employee_id} ({hostname})")
    # Optionally log heartbeat time in a separate collection or update employee doc

    return jsonify({"status": "ok", "message": "Heartbeat received"}), 200

@api_bp.route('/log/activity', methods=['POST'])
def log_activity():
    """Agent sends activity data (window title, duration, etc.)."""
    data = request.json
    employee_id = data.get('employee_id')
    activities = data.get('activities') # Expecting a list of activities

    if not employee_id or not activities:
        return jsonify({"status": "error", "message": "Missing employee_id or activities"}), 400

    db = get_db()
    now = datetime.datetime.now(datetime.timezone.utc)

    activity_docs = []
    for act in activities:
        activity_docs.append({
            "employee_id": employee_id,
            "timestamp": now, # Or use timestamp from agent if reliable
            "window_title": act.get("window_title"),
            "process_name": act.get("process_name"),
            "start_time": datetime.datetime.fromisoformat(act.get("start_time")), # Ensure agent sends ISO format
            "end_time": datetime.datetime.fromisoformat(act.get("end_time")),
            "duration_seconds": act.get("duration_seconds"),
            "is_active": act.get("is_active", True), # Track idle time
            # "screenshot_ref": None # Link to screenshot if taken during this period
        })

    if activity_docs:
        try:
            result = db.activity_logs.insert_many(activity_docs)
            # Update employee's last_seen status
            db.employees.update_one(
                {"employee_id": employee_id},
                {"$set": {"last_seen": now}}
            )
            print(f"Logged {len(result.inserted_ids)} activities for {employee_id}")
            return jsonify({"status": "ok", "message": f"Logged {len(result.inserted_ids)} activities"}), 201
        except Exception as e:
             print(f"Error inserting activity logs for {employee_id}: {e}")
             return jsonify({"status": "error", "message": "Database error logging activity"}), 500
    else:
         return jsonify({"status": "ok", "message": "No activities to log"}), 200


@api_bp.route('/upload/screenshot', methods=['POST'])
def upload_screenshot():
    """Agent uploads a captured screenshot."""
    if 'screenshot' not in request.files:
        return jsonify({"status": "error", "message": "No screenshot file part"}), 400

    file = request.files['screenshot']
    employee_id = request.form.get('employee_id')
    timestamp_str = request.form.get('timestamp') # Agent should send timestamp when screenshot was taken

    if not employee_id or not timestamp_str:
         return jsonify({"status": "error", "message": "Missing employee_id or timestamp"}), 400

    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file: # Add more robust file validation (type, size) here
        db = get_db()
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
        except ValueError:
             return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400

        # Create a unique filename to avoid collisions
        # Format: YYYYMMDD_HHMMSS_employeeID_random.png
        filename_timestamp = timestamp.strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{filename_timestamp}_{employee_id}_{unique_id}.png" # Assuming PNG format
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

        try:
            file.save(save_path)
            print(f"Screenshot saved for {employee_id} at {timestamp_str} to {filename}")

            # Optionally, log the screenshot path in the activity_logs or a separate collection
            db.activity_logs.insert_one({
                "employee_id": employee_id,
                "timestamp": timestamp,
                "log_type": "screenshot",
                "screenshot_path": filename, # Store relative path
                # Add other relevant info like active window at time of screenshot
            })
             # Update employee's last_seen status
            db.employees.update_one(
                {"employee_id": employee_id},
                {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}}
            )

            return jsonify({"status": "ok", "message": "Screenshot uploaded successfully"}), 201
        except Exception as e:
            print(f"Error saving screenshot for {employee_id}: {e}")
            # Clean up potentially partially saved file?
            return jsonify({"status": "error", "message": f"Could not save file: {e}"}), 500

    return jsonify({"status": "error", "message": "File processing error"}), 500

# --- Agent Download Route ---
# This needs proper security (login required) and ensure the EXE exists
# @api_bp.route('/download/agent') # Maybe move this out of /api if login needed
# @login_required # Add authentication here
# def download_agent_exe():
#     """Provides the agent executable for download."""
#     agent_path = current_app.config['AGENT_EXE_PATH']
#     agent_dir = os.path.dirname(agent_path)
#     agent_filename = os.path.basename(agent_path)

#     if os.path.exists(agent_path):
#         print(f"Serving agent file: {agent_filename}")
#         return send_from_directory(directory=agent_dir, path=agent_filename, as_attachment=True)
#     else:
#         print(f"Agent file not found at: {agent_path}")
#         abort(404, description="Agent executable not found.")