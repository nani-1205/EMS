# /root/EMS/server/routes/api.py
from flask import (
    Blueprint, request, jsonify, current_app, abort,
    send_from_directory, session, flash, url_for, redirect # Added url_for, redirect
)
from models.db import get_db, create_employee
from routes.auth import login_required # For securing admin-only API endpoints
import datetime
import os
import uuid
import logging # Explicitly import for direct use if needed, though current_app.logger is preferred

api_bp = Blueprint('api', __name__)

def verify_api_key():
    """Checks if the request has a valid API key for agent communication."""
    provided_key = request.headers.get('X-API-KEY')
    agent_api_key = current_app.config.get('AGENT_API_KEY')

    if not agent_api_key: # Safety check in case AGENT_API_KEY is not set in config
        current_app.logger.critical("CRITICAL: AGENT_API_KEY is not configured on the server!")
        abort(500, description="Server configuration error: API key not set.")


    if not provided_key or provided_key != agent_api_key:
        current_app.logger.warning(
            f"Unauthorized API access attempt. Endpoint: {request.endpoint}. "
            f"Provided key: '{provided_key}'. Expected end: '...{agent_api_key[-5:] if agent_api_key else 'N/A'}'"
        )
        abort(401, description="Unauthorized: Invalid or missing API key.")

@api_bp.before_request
def before_api_request():
    """Verify API key for agent routes; ensure login for admin/internal API routes."""
    agent_endpoints_requiring_key = ['api.heartbeat', 'api.log_activity', 'api.upload_screenshot']
    
    if request.endpoint in agent_endpoints_requiring_key:
         verify_api_key()
    # Other endpoints like /api/active_employees and /api/download/agent are secured by @login_required

@api_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Agent checks in, reports status."""
    current_app.logger.debug(f"Heartbeat request received. Headers: {dict(request.headers)}")
    try:
        data = request.get_json()
        if data is None: # get_json() returns None if not JSON or parsing fails
            current_app.logger.warning("Heartbeat: Empty or non-JSON payload.")
            return jsonify({"status": "error", "message": "Invalid or empty JSON payload"}), 400
    except Exception as e:
        current_app.logger.error(f"Heartbeat: Error decoding JSON: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Malformed JSON payload"}), 400

    employee_id = data.get('employee_id')
    hostname = data.get('hostname', employee_id) # Use employee_id as fallback for hostname

    if not employee_id:
        current_app.logger.warning(f"Heartbeat: Missing employee_id in payload: {data}")
        return jsonify({"status": "error", "message": "Missing employee_id"}), 400

    db = get_db()
    # create_employee will also update last_seen if employee exists
    # Pass hostname from agent as the initial_name if creating new employee
    create_employee(db, employee_id, initial_name=hostname if hostname != employee_id else None)

    current_app.logger.info(f"Heartbeat received and processed for: {employee_id} (Hostname: {hostname})")
    return jsonify({"status": "ok", "message": "Heartbeat received"}), 200

@api_bp.route('/log/activity', methods=['POST'])
def log_activity():
    """Agent sends activity data (window title, duration, etc.)."""
    current_app.logger.info(f"Received request for /api/log/activity. X-API-KEY present: {'X-API-KEY' in request.headers}")
    try:
        data = request.get_json()
        if data is None:
            current_app.logger.error(f"/api/log/activity: Failed to decode JSON or empty payload. Content-Type: {request.content_type}")
            return jsonify({"status": "error", "message": "Invalid or empty JSON payload"}), 400
        current_app.logger.debug(f"/api/log/activity: Raw data received (first 1000 chars): {str(data)[:1000]}")
    except Exception as e_json:
        current_app.logger.error(f"/api/log/activity: Error accessing/decoding JSON: {e_json}", exc_info=True)
        return jsonify({"status": "error", "message": "Malformed JSON payload"}), 400

    employee_id = data.get('employee_id')
    activities_payload = data.get('activities')

    if not employee_id:
        current_app.logger.warning(f"/api/log/activity: Missing employee_id. Payload keys: {list(data.keys())}")
        return jsonify({"status": "error", "message": "Missing employee_id"}), 400
    if not isinstance(activities_payload, list):
        current_app.logger.warning(f"/api/log/activity: 'activities' is not a list or missing for {employee_id}. Type: {type(activities_payload)}")
        return jsonify({"status": "error", "message": "'activities' field must be a list or is missing"}), 400
    if not activities_payload:
        current_app.logger.info(f"/api/log/activity: Received empty 'activities' list for {employee_id}.")
        return jsonify({"status": "ok", "message": "No activities to log (empty list)"}), 200

    db = get_db()
    server_batch_timestamp = datetime.datetime.now(datetime.timezone.utc)
    
    activity_docs_to_insert = []
    malformed_count = 0
    processed_count = 0

    for i, act_data in enumerate(activities_payload):
        if not isinstance(act_data, dict):
            current_app.logger.warning(f"/api/log/activity: Item {i} for {employee_id} is not a dict: {act_data}")
            malformed_count += 1
            continue

        try:
            start_time_str = act_data.get("start_time")
            end_time_str = act_data.get("end_time")
            duration_s = act_data.get("duration_seconds")

            if not all([start_time_str, end_time_str, duration_s is not None]): # Ensure all three are present
                current_app.logger.warning(f"/api/log/activity: Missing time/duration fields in item {i} for {employee_id}: {act_data}")
                malformed_count += 1
                continue
            
            start_time = datetime.datetime.fromisoformat(start_time_str)
            end_time = datetime.datetime.fromisoformat(end_time_str)

            if not isinstance(duration_s, (int, float)) or duration_s < 0:
                calculated_duration = (end_time - start_time).total_seconds()
                if calculated_duration < 0:
                    current_app.logger.warning(f"Negative calculated duration for item {i}, {employee_id}. Start: {start_time}, End: {end_time}. Skipping.")
                    malformed_count += 1
                    continue
                duration_s = int(calculated_duration)
                current_app.logger.debug(f"Used recalculated duration {duration_s}s for activity from {employee_id}")

            doc = {
                "employee_id": employee_id, "timestamp": server_batch_timestamp,
                "window_title": act_data.get("window_title", "N/A"), "process_name": act_data.get("process_name", "N/A"),
                "start_time": start_time, "end_time": end_time, "duration_seconds": int(duration_s),
                "is_active": act_data.get("is_active", True), "log_type": "activity"
            }
            activity_docs_to_insert.append(doc)
            processed_count += 1
            current_app.logger.debug(f"Prepared doc for insertion: P='{doc['process_name']}', T='{doc['window_title'][:30]}', Emp={employee_id}")

        except ValueError as ve: 
            current_app.logger.warning(f"/api/log/activity: Invalid ISO time format in item {i} for {employee_id}. Error: {ve}. Data: {act_data}")
            malformed_count += 1
        except Exception as e_item:
            current_app.logger.error(f"/api/log/activity: Error processing item {i} for {employee_id}. Error: {e_item}. Data: {act_data}", exc_info=True)
            malformed_count += 1

    if activity_docs_to_insert:
        try:
            result = db.activity_logs.insert_many(activity_docs_to_insert, ordered=False)
            db.employees.update_one({"employee_id": employee_id}, {"$set": {"last_seen": server_batch_timestamp}})
            msg = f"Successfully logged {len(result.inserted_ids)} of {processed_count} activities for {employee_id}." + (f" Skipped {malformed_count} malformed activities." if malformed_count > 0 else "")
            current_app.logger.info(msg)
            return jsonify({"status": "ok", "message": msg, "inserted_count": len(result.inserted_ids), "malformed_count": malformed_count}), 201
        except Exception as e_db_insert:
             current_app.logger.error(f"Database error inserting activity_logs batch for {employee_id}: {e_db_insert}", exc_info=True)
             return jsonify({"status": "error", "message": "Database error during bulk insert of activity logs"}), 500
    elif malformed_count > 0:
        current_app.logger.warning(f"/api/log/activity: All {malformed_count} activities for {employee_id} were malformed. Nothing logged.")
        return jsonify({"status": "error", "message": f"All {malformed_count} received activities were malformed or invalid."}), 400
    else:
         current_app.logger.info(f"/api/log/activity: No activities were processed for insertion for {employee_id} (e.g., all skipped or list was effectively empty).")
         return jsonify({"status": "ok", "message": "No valid activities processed for insertion"}), 200

@api_bp.route('/upload/screenshot', methods=['POST'])
def upload_screenshot():
    if 'screenshot' not in request.files:
        current_app.logger.warning("/api/upload/screenshot: 'screenshot' file part missing.")
        return jsonify({"status": "error", "message": "No screenshot file part"}), 400
    
    file = request.files['screenshot']
    employee_id = request.form.get('employee_id')
    timestamp_str = request.form.get('timestamp')

    if not all([employee_id, timestamp_str]) or not file or file.filename == '':
         current_app.logger.warning(f"/api/upload/screenshot: Missing form data or filename. Emp: {employee_id}, TS: {timestamp_str}, File: {file.filename if file else 'No file object'}")
         return jsonify({"status": "error", "message": "Missing form data (employee_id, timestamp) or file"}), 400
    
    try:
        timestamp = datetime.datetime.fromisoformat(timestamp_str)
    except ValueError:
         current_app.logger.warning(f"/api/upload/screenshot: Invalid timestamp format: {timestamp_str}")
         return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400

    db = get_db()
    # Sanitize employee_id for filename to prevent path traversal or invalid characters
    safe_employee_id = "".join(c if c.isalnum() or c in ['-', '_'] else "_" for c in employee_id)
    if not safe_employee_id: safe_employee_id = "unknown_emp" # Fallback if sanitization results in empty

    filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{safe_employee_id}_{uuid.uuid4().hex[:8]}.png"
    
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder:
        current_app.logger.critical("/api/upload/screenshot: UPLOAD_FOLDER not configured in Flask app.")
        return jsonify({"status": "error", "message": "Server configuration error (upload path missing)"}), 500
    
    save_path = os.path.join(upload_folder, filename)

    try:
        file.save(save_path)
        current_app.logger.info(f"Screenshot saved to disk: {save_path} for {employee_id}")
        db.activity_logs.insert_one({
            "employee_id": employee_id, "timestamp": timestamp,
            "log_type": "screenshot", "screenshot_path": filename,
        })
        db.employees.update_one({"employee_id": employee_id}, {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}})
        current_app.logger.info(f"Screenshot log created in DB for {filename}")
        return jsonify({"status": "ok", "message": "Screenshot uploaded successfully", "filename": filename}), 201
    except Exception as e:
        current_app.logger.error(f"Error saving screenshot file or DB record for {employee_id} (Path: {save_path}): {e}", exc_info=True)
        # Corrected try-except block for cleanup
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
                current_app.logger.info(f"Cleaned up partially saved screenshot: {save_path}")
            except Exception as e_remove:
                current_app.logger.error(f"Error removing partially saved screenshot {save_path}: {e_remove}")
        return jsonify({"status": "error", "message": f"Could not save/log screenshot file: {str(e)}"}), 500
    
    current_app.logger.error("/api/upload/screenshot: Reached end of function unexpectedly without explicit return.")
    return jsonify({"status": "error", "message": "Unknown file processing error"}), 500


@api_bp.route('/download/agent')
@login_required
def download_agent_exe():
    agent_path = current_app.config.get('AGENT_EXE_PATH', '')
    if not agent_path or not os.path.exists(agent_path):
        current_app.logger.error(f"Agent executable not found at '{agent_path}' for download by admin '{session.get('username', 'unknown')}'")
        flash("Agent executable not found on server. Please ensure it's built and AGENT_EXE_PATH in config.py is correct.", "danger")
        return redirect(request.referrer or url_for('settings.index'))
    
    current_app.logger.info(f"Admin '{session.get('username', 'unknown')}' initiated download of agent: {os.path.basename(agent_path)}")
    try:
        return send_from_directory(directory=os.path.dirname(agent_path),
                                   path=os.path.basename(agent_path),
                                   as_attachment=True,
                                   download_name="monitoring_agent.exe")
    except Exception as e:
        current_app.logger.error(f"Error sending agent file for download: {e}", exc_info=True)
        flash("Error occurred while trying to send the agent file.", "danger")
        return redirect(request.referrer or url_for('settings.index'))

@api_bp.route('/active_employees', methods=['GET'])
@login_required
def get_active_employees():
    db = get_db()
    active_threshold_minutes = current_app.config.get('ACTIVE_EMPLOYEE_THRESHOLD_MINUTES', 5)
    active_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=active_threshold_minutes)
    try:
        active_emps_cursor = db.employees.find(
            {"last_seen": {"$gte": active_threshold}, "status": {"$in": ["active", "pending_rename"]}},
            {"_id": 1, "display_name": 1, "employee_id": 1}
        ).sort("display_name", 1).limit(15)
        
        active_emps_list = []
        for emp in active_emps_cursor:
            emp['_id'] = str(emp['_id'])
            active_emps_list.append(emp)
        
        current_app.logger.debug(f"Returning {len(active_emps_list)} active employees for sidebar.")
        return jsonify(active_emps_list)
    except Exception as e:
        current_app.logger.error(f"Error fetching active_employees: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve active employees list"}), 500