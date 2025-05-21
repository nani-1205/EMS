# /root/EMS/server/routes/api.py
from flask import Blueprint, request, jsonify, current_app, abort, send_from_directory, session, flash # <-- Added flash
from models.db import get_db, create_employee
from routes.auth import login_required
import datetime
import os
import uuid
import logging

api_bp = Blueprint('api', __name__)

def verify_api_key():
    provided_key = request.headers.get('X-API-KEY')
    if not provided_key or provided_key != current_app.config['AGENT_API_KEY']:
        current_app.logger.warning(f"Unauthorized API access. Endpoint: {request.endpoint}. Key: '{provided_key}'. Expected end: '...{current_app.config.get('AGENT_API_KEY', '')[-5:]}'")
        abort(401, description="Unauthorized: Invalid or missing API key.")

@api_bp.before_request
def before_api_request():
    agent_endpoints_requiring_key = ['api.heartbeat', 'api.log_activity', 'api.upload_screenshot']
    if request.endpoint in agent_endpoints_requiring_key:
         verify_api_key()

@api_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    current_app.logger.debug(f"Heartbeat request. Headers: {request.headers}")
    try:
        data = request.get_json()
        if data is None: return jsonify({"status": "error", "message": "Invalid JSON"}), 400
    except Exception as e:
        current_app.logger.error(f"Heartbeat JSON decode error: {e}")
        return jsonify({"status": "error", "message": "Malformed JSON"}), 400

    employee_id = data.get('employee_id')
    hostname = data.get('hostname', employee_id)
    if not employee_id: return jsonify({"status": "error", "message": "Missing employee_id"}), 400

    db = get_db()
    create_employee(db, employee_id, initial_name=hostname if hostname != employee_id else None)
    current_app.logger.info(f"Heartbeat processed for: {employee_id} (Host: {hostname})")
    return jsonify({"status": "ok", "message": "Heartbeat received"}), 200

@api_bp.route('/log/activity', methods=['POST'])
def log_activity():
    current_app.logger.info(f"Activity log request. X-API-KEY present: {'X-API-KEY' in request.headers}")
    try:
        data = request.get_json()
        if data is None:
            current_app.logger.error(f"ActivityLog: Non-JSON or empty payload. Type: {request.content_type}")
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
        current_app.logger.debug(f"ActivityLog Raw: {str(data)[:1000]}")
    except Exception as e:
        current_app.logger.error(f"ActivityLog JSON error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Malformed JSON"}), 400

    employee_id = data.get('employee_id')
    activities_payload = data.get('activities')

    if not employee_id: return jsonify({"status": "error", "message": "Missing employee_id"}), 400
    if not isinstance(activities_payload, list): return jsonify({"status": "error", "message": "'activities' must be a list"}), 400
    if not activities_payload: return jsonify({"status": "ok", "message": "Empty 'activities' list"}), 200

    db = get_db()
    server_batch_timestamp = datetime.datetime.now(datetime.timezone.utc)
    activity_docs_to_insert, malformed_count, processed_count = [], 0, 0

    for i, act_data in enumerate(activities_payload):
        if not isinstance(act_data, dict):
            malformed_count += 1; continue
        try:
            start_time_str, end_time_str, duration_s = act_data.get("start_time"), act_data.get("end_time"), act_data.get("duration_seconds")
            if not all([start_time_str, end_time_str, duration_s is not None]):
                malformed_count += 1; continue
            start_time, end_time = datetime.datetime.fromisoformat(start_time_str), datetime.datetime.fromisoformat(end_time_str)
            if not isinstance(duration_s, (int, float)) or duration_s < 0:
                duration_s = int(max(0, (end_time - start_time).total_seconds()))

            activity_docs_to_insert.append({
                "employee_id": employee_id, "timestamp": server_batch_timestamp,
                "window_title": act_data.get("window_title", "N/A"), "process_name": act_data.get("process_name", "N/A"),
                "start_time": start_time, "end_time": end_time, "duration_seconds": int(duration_s),
                "is_active": act_data.get("is_active", True), "log_type": "activity"
            })
            processed_count += 1
        except ValueError: malformed_count += 1
        except Exception as e: malformed_count += 1; current_app.logger.error(f"Error processing activity item {i} for {employee_id}: {e}", exc_info=True)

    if activity_docs_to_insert:
        try:
            result = db.activity_logs.insert_many(activity_docs_to_insert, ordered=False)
            db.employees.update_one({"employee_id": employee_id}, {"$set": {"last_seen": server_batch_timestamp}})
            msg = f"Logged {len(result.inserted_ids)} of {processed_count} activities for {employee_id}." + (f" Skipped {malformed_count}." if malformed_count else "")
            current_app.logger.info(msg)
            return jsonify({"status": "ok", "message": msg, "inserted": len(result.inserted_ids), "malformed": malformed_count}), 201
        except Exception as e:
             current_app.logger.error(f"DB error inserting activity_logs for {employee_id}: {e}", exc_info=True)
             return jsonify({"status": "error", "message": "DB bulk insert error"}), 500
    elif malformed_count > 0:
        return jsonify({"status": "error", "message": f"All {malformed_count} activities malformed."}), 400
    else:
         return jsonify({"status": "ok", "message": "No valid activities processed"}), 200

@api_bp.route('/upload/screenshot', methods=['POST'])
def upload_screenshot():
    if 'screenshot' not in request.files: return jsonify({"status": "error", "message": "No screenshot file part"}), 400
    file, employee_id, timestamp_str = request.files['screenshot'], request.form.get('employee_id'), request.form.get('timestamp')

    if not all([employee_id, timestamp_str, file.filename]):
         return jsonify({"status": "error", "message": "Missing form data or filename"}), 400
    try:
        timestamp = datetime.datetime.fromisoformat(timestamp_str)
    except ValueError: return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400

    db = get_db()
    safe_employee_id = "".join(c if c.isalnum() else "_" for c in employee_id)
    filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{safe_employee_id}_{uuid.uuid4().hex[:8]}.png"
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

    try:
        file.save(save_path)
        current_app.logger.info(f"Screenshot saved: {filename} for {employee_id}")
        db.activity_logs.insert_one({
            "employee_id": employee_id, "timestamp": timestamp,
            "log_type": "screenshot", "screenshot_path": filename,
        })
        db.employees.update_one({"employee_id": employee_id}, {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}})
        return jsonify({"status": "ok", "message": "Screenshot uploaded", "filename": filename}), 201
    except Exception as e:
        current_app.logger.error(f"Error saving screenshot/DB record for {employee_id}: {e}", exc_info=True)
        if os.path.exists(save_path): try: os.remove(save_path) except: pass
        return jsonify({"status": "error", "message": f"Could not save/log file: {e}"}), 500
    return jsonify({"status": "error", "message": "Unknown file processing error"}), 500


@api_bp.route('/download/agent')
@login_required
def download_agent_exe():
    agent_path = current_app.config.get('AGENT_EXE_PATH', '') # Use .get for safety
    if not agent_path or not os.path.exists(agent_path):
        current_app.logger.error(f"Agent executable not found at '{agent_path}' for download by admin '{session.get('username')}'")
        flash("Agent executable not found on server. Please ensure it's built and AGENT_EXE_PATH in config.py is correct.", "danger")
        return redirect(request.referrer or url_for('settings.index')) # Redirect to settings or previous page
    
    current_app.logger.info(f"Admin '{session.get('username')}' downloading agent: {os.path.basename(agent_path)}")
    return send_from_directory(directory=os.path.dirname(agent_path),
                               path=os.path.basename(agent_path),
                               as_attachment=True,
                               download_name="monitoring_agent.exe")

@api_bp.route('/active_employees', methods=['GET'])
@login_required
def get_active_employees():
    db = get_db()
    active_threshold_minutes = current_app.config.get('ACTIVE_EMPLOYEE_THRESHOLD_MINUTES', 5)
    active_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=active_threshold_minutes)
    try:
        active_emps_cursor = db.employees.find(
            {"last_seen": {"$gte": active_threshold}, "status": {"$in": ["active", "pending_rename"]}},
            {"_id": 1, "display_name": 1, "employee_id": 1} # Project only needed fields
        ).sort("display_name", 1).limit(15) # Limit results for sidebar
        
        active_emps_list = []
        for emp in active_emps_cursor:
            emp['_id'] = str(emp['_id']) # Convert ObjectId for JSON
            active_emps_list.append(emp)
        
        current_app.logger.debug(f"Returning {len(active_emps_list)} active employees for sidebar.")
        return jsonify(active_emps_list)
    except Exception as e:
        current_app.logger.error(f"Error fetching active_employees: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve active employees list"}), 500