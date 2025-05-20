# /root/EMS/server/routes/api.py
from flask import Blueprint, request, jsonify, current_app, abort, send_from_directory, session
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
    if not provided_key or provided_key != current_app.config['AGENT_API_KEY']:
        current_app.logger.warning(f"Unauthorized API access attempt. Endpoint: {request.endpoint}. Provided key: '{provided_key}'. Expected part: '...{current_app.config['AGENT_API_KEY'][-5:] if current_app.config.get('AGENT_API_KEY') else 'N/A'}'")
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
    current_app.logger.debug(f"Heartbeat request received. Headers: {request.headers}")
    try:
        data = request.get_json()
        if data is None:
            current_app.logger.warning("Heartbeat: Empty or non-JSON payload.")
            # Still proceed if basic info can be gleaned or just acknowledge if needed for some agents
            # For now, require employee_id from payload
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
    except Exception as e:
        current_app.logger.error(f"Heartbeat: Error decoding JSON: {e}")
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
    current_app.logger.info(f"Received request for /api/log/activity. Headers X-API-KEY present: {'X-API-KEY' in request.headers}")
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

            if not all([start_time_str, end_time_str, duration_s is not None]):
                current_app.logger.warning(f"/api/log/activity: Missing time/duration fields in item {i} for {employee_id}: {act_data}")
                malformed_count += 1
                continue
            
            start_time = datetime.datetime.fromisoformat(start_time_str)
            end_time = datetime.datetime.fromisoformat(end_time_str)

            # Validate duration (optional, can trust agent or recalculate)
            if not isinstance(duration_s, (int, float)) or duration_s < 0:
                calculated_duration = (end_time - start_time).total_seconds()
                if calculated_duration < 0:
                    current_app.logger.warning(f"Negative calculated duration for item {i}, {employee_id}. Start: {start_time}, End: {end_time}. Skipping.")
                    malformed_count += 1
                    continue
                duration_s = int(calculated_duration)
                current_app.logger.debug(f"Used recalculated duration {duration_s}s for activity from {employee_id}")

            doc = {
                "employee_id": employee_id,
                "timestamp": server_batch_timestamp, # Server timestamp for when batch was received
                "window_title": act_data.get("window_title", "N/A"),
                "process_name": act_data.get("process_name", "N/A"),
                "start_time": start_time,       # Agent-provided activity start
                "end_time": end_time,         # Agent-provided activity end
                "duration_seconds": int(duration_s),
                "is_active": act_data.get("is_active", True),
                "log_type": "activity" # Explicitly mark type
            }
            activity_docs_to_insert.append(doc)
            processed_count += 1
            current_app.logger.debug(f"Prepared doc for insertion: P='{doc['process_name']}', T='{doc['window_title'][:30]}', Emp={employee_id}")

        except ValueError as ve: # For fromisoformat errors
            current_app.logger.warning(f"/api/log/activity: Invalid ISO time format in item {i} for {employee_id}. Error: {ve}. Data: {act_data}")
            malformed_count += 1
        except Exception as e_item:
            current_app.logger.error(f"/api/log/activity: Error processing item {i} for {employee_id}. Error: {e_item}. Data: {act_data}", exc_info=True)
            malformed_count += 1

    if activity_docs_to_insert:
        try:
            # ordered=False allows valid docs to be inserted even if some in the batch fail MongoDB validation (if any)
            result = db.activity_logs.insert_many(activity_docs_to_insert, ordered=False)
            db.employees.update_one(
                {"employee_id": employee_id},
                {"$set": {"last_seen": server_batch_timestamp}}
            )
            msg = f"Successfully logged {len(result.inserted_ids)} of {processed_count} processed activities for {employee_id}."
            if malformed_count > 0: msg += f" Skipped {malformed_count} malformed activities."
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
    # ... (This function should be mostly fine, ensure it uses current_app.logger) ...
    # Add current_app.logger.info/debug/error where you had print()
    if 'screenshot' not in request.files:
        current_app.logger.warning("/api/upload/screenshot: 'screenshot' file part missing.")
        return jsonify({"status": "error", "message": "No screenshot file part"}), 400
    # ... (rest of the robust screenshot upload logic) ...
    file = request.files['screenshot']
    employee_id = request.form.get('employee_id')
    timestamp_str = request.form.get('timestamp')

    if not employee_id or not timestamp_str:
         current_app.logger.warning(f"/api/upload/screenshot: Missing employee_id or timestamp. Emp: {employee_id}, TS: {timestamp_str}")
         return jsonify({"status": "error", "message": "Missing employee_id or timestamp"}), 400
    if file.filename == '':
        current_app.logger.warning("/api/upload/screenshot: No selected file (empty filename).")
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file: # Add more robust file validation (type, size) here eventually
        db = get_db()
        try:
            timestamp = datetime.datetime.fromisoformat(timestamp_str)
        except ValueError:
             current_app.logger.warning(f"/api/upload/screenshot: Invalid timestamp format: {timestamp_str}")
             return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400

        filename_timestamp = timestamp.strftime("%Y%m%d_%H%M%S_%f") # Added microseconds for more uniqueness
        unique_id = uuid.uuid4().hex[:8]
        # Sanitize employee_id for filename if it can contain special characters
        safe_employee_id = "".join(c if c.isalnum() else "_" for c in employee_id)
        filename = f"{filename_timestamp}_{safe_employee_id}_{unique_id}.png"
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

        try:
            file.save(save_path)
            current_app.logger.info(f"Screenshot saved for {employee_id} at {timestamp_str} to {filename}")
            db.activity_logs.insert_one({
                "employee_id": employee_id,
                "timestamp": timestamp, # Timestamp of when screenshot was taken
                "log_type": "screenshot",
                "screenshot_path": filename, # Store relative path
            })
            db.employees.update_one(
                {"employee_id": employee_id},
                {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}} # Update last_seen for this activity
            )
            return jsonify({"status": "ok", "message": "Screenshot uploaded successfully", "filename": filename}), 201
        except Exception as e:
            current_app.logger.error(f"Error saving screenshot file or DB record for {employee_id}: {e}", exc_info=True)
            # Clean up partially saved file?
            if os.path.exists(save_path):
                try: os.remove(save_path)
                except: pass
            return jsonify({"status": "error", "message": f"Could not save file or log to DB: {e}"}), 500

    current_app.logger.warning("/api/upload/screenshot: Reached end of function without processing file, likely an issue.")
    return jsonify({"status": "error", "message": "File processing error (unknown)"}), 500


@api_bp.route('/download/agent')
@login_required
def download_agent_exe():
    # ... (This function should be mostly fine, ensure it uses current_app.logger) ...
    agent_path = current_app.config['AGENT_EXE_PATH']
    # ... (rest of download logic)
    if not os.path.exists(agent_path):
        current_app.logger.error(f"Agent executable not found at {agent_path} for download by admin {session.get('username')}")
        flash("Agent executable not found on server. Please ensure it's built and path is correct in config.", "danger")
        return redirect(request.referrer or url_for('dashboard.view_dashboard')) # Go back or to dashboard
    
    current_app.logger.info(f"Admin {session.get('username')} initiated download of agent: {os.path.basename(agent_path)}")
    return send_from_directory(directory=os.path.dirname(agent_path),
                               path=os.path.basename(agent_path),
                               as_attachment=True,
                               download_name="monitoring_agent.exe") # Suggest a clean download name

@api_bp.route('/active_employees', methods=['GET'])
@login_required
def get_active_employees():
    # ... (This function should be mostly fine, ensure it uses current_app.logger) ...
    db = get_db()
    active_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=current_app.config.get('ACTIVE_EMPLOYEE_THRESHOLD_MINUTES', 5))
    try:
        active_emps_cursor = db.employees.find(
            {"last_seen": {"$gte": active_threshold}, "status": {"$in": ["active", "pending_rename"]}},
            {"_id": 1, "display_name": 1, "employee_id": 1}
        ).sort("display_name", 1).limit(15)
        
        active_emps_list = []
        for emp in active_emps_cursor:
            emp['_id'] = str(emp['_id']) # Convert ObjectId for JSON
            active_emps_list.append(emp)
        
        current_app.logger.debug(f"Returning {len(active_emps_list)} active employees.")
        return jsonify(active_emps_list)
    except Exception as e:
        current_app.logger.error(f"Error fetching active employees: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve active employees list"}), 500