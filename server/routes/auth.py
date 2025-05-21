# /root/EMS/server/routes/api.py
from flask import (
    Blueprint, request, jsonify, current_app, abort,
    send_from_directory, session, flash, url_for, redirect
)
from models.db import get_db, create_employee # Assuming get_db is correctly set up
from routes.auth import login_required
import datetime
import os
import uuid
import re # For regex matching in categorization if needed
# No need to import logging explicitly if using current_app.logger

api_bp = Blueprint('api', __name__)

# --- Helper: API Key Verification ---
def verify_api_key():
    provided_key = request.headers.get('X-API-KEY')
    agent_api_key = current_app.config.get('AGENT_API_KEY')
    if not agent_api_key:
        current_app.logger.critical("CRITICAL: AGENT_API_KEY is not configured on the server!")
        abort(500, description="Server configuration error.")
    if not provided_key or provided_key != agent_api_key:
        current_app.logger.warning(f"Unauthorized API access. Endpoint: {request.endpoint}. Provided key: '{provided_key}'.")
        abort(401, description="Unauthorized: Invalid or missing API key.")

# --- Blueprint Before Request Hook ---
@api_bp.before_request
def before_api_request_hook(): # Renamed for clarity
    agent_endpoints_requiring_key = ['api.heartbeat', 'api.log_activity', 'api.upload_screenshot']
    if request.endpoint in agent_endpoints_requiring_key:
         verify_api_key()

# --- Helper: Categorization Logic ---
# This cache will be simple in-memory. For production, consider Redis or a TTL cache.
categorization_cache = {
    "rules": [],
    "categories_map": {}, # Map category_id (str) to category document
    "default_category_id": None,
    "last_updated": None
}
CACHE_TTL_SECONDS = 300 # 5 minutes

def get_categorization_data(db):
    """Fetches and caches categorization rules and categories."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if categorization_cache["last_updated"] and \
       (now - categorization_cache["last_updated"]).total_seconds() < CACHE_TTL_SECONDS:
        # current_app.logger.debug("Using cached categorization data.")
        return (categorization_cache["rules"], 
                categorization_cache["categories_map"], 
                categorization_cache["default_category_id"])

    current_app.logger.info("Refreshing categorization data cache...")
    try:
        rules = list(db.categorization_rules.find().sort([("priority", 1), ("pattern", 1)])) # Sort by priority then pattern
        categories_map = {str(cat["_id"]): cat for cat in db.categories.find()}
        default_category_id = None
        for cat_id, cat_doc in categories_map.items():
            if cat_doc.get("is_fallback") or cat_doc.get("name") == "Neutral/Undefined":
                default_category_id = ObjectId(cat_id) # Store as ObjectId
                break
        
        categorization_cache["rules"] = rules
        categorization_cache["categories_map"] = categories_map
        categorization_cache["default_category_id"] = default_category_id
        categorization_cache["last_updated"] = now
        current_app.logger.info(f"Categorization cache updated: {len(rules)} rules, {len(categories_map)} categories.")
    except Exception as e:
        current_app.logger.error(f"Failed to refresh categorization cache: {e}", exc_info=True)
        # Return stale cache or empty if first time
    
    return (categorization_cache["rules"], 
            categorization_cache["categories_map"], 
            categorization_cache["default_category_id"])


def get_activity_category_id_from_rules(activity_data, rules, categories_map, default_category_id):
    process_name = activity_data.get("process_name", "").lower()
    window_title = activity_data.get("window_title", "").lower()

    for rule in rules: # Rules are pre-sorted by priority (if implemented)
        pattern = rule.get("pattern", "").lower() # Patterns stored/matched in lowercase
        rule_type = rule.get("type")
        match_mode = rule.get("match_mode", "exact") # Default to exact match
        
        target_text = None
        if rule_type == "process_name":
            target_text = process_name
        elif rule_type == "window_title_keyword":
            target_text = window_title
        elif rule_type == "website_domain":
            # Basic domain extraction (you might need a more robust parser)
            try:
                if "http://" in window_title or "https://" in window_title:
                    from urllib.parse import urlparse
                    parsed_url = urlparse(window_title)
                    target_text = parsed_url.netloc.replace("www.", "") # Simple domain
            except ImportError: # urllib.parse might not be available if agent sends non-URL
                pass
            except Exception: # Catch any parsing error
                pass
        
        if target_text is None: continue

        match_found = False
        if match_mode == "exact" and target_text == pattern:
            match_found = True
        elif match_mode == "contains" and pattern in target_text:
            match_found = True
        elif match_mode == "startswith" and target_text.startswith(pattern):
            match_found = True
        elif match_mode == "endswith" and target_text.endswith(pattern):
            match_found = True
        # Add regex mode if needed:
        # elif match_mode == "regex":
        #     try:
        #         if re.search(pattern, target_text, re.IGNORECASE): # re.IGNORECASE if patterns are not pre-lowercased
        #             match_found = True
        #     except re.error:
        #         current_app.logger.warning(f"Invalid regex pattern in rule: {pattern}")

        if match_found:
            cat_id_str = str(rule.get("category_id"))
            if cat_id_str in categories_map:
                # current_app.logger.debug(f"Activity matched rule '{pattern}' -> category '{categories_map[cat_id_str]['name']}'")
                return rule.get("category_id") # Return ObjectId
            else:
                current_app.logger.warning(f"Rule pattern '{pattern}' matched, but category ID '{cat_id_str}' not found in categories map.")
                # Continue to check other rules in case of orphaned rule
    
    # current_app.logger.debug(f"No specific rule matched activity. P: '{process_name}', T: '{window_title[:50]}'. Using default category.")
    return default_category_id


# --- API Endpoints ---
@api_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    # ... (heartbeat logic as in your last working version, ensuring create_employee is called) ...
    current_app.logger.debug(f"Heartbeat request received. Headers: {dict(request.headers)}")
    try: data = request.get_json(); assert data is not None
    except: return jsonify({"status": "error", "message": "Invalid/Malformed JSON"}), 400
    employee_id, hostname = data.get('employee_id'), data.get('hostname', data.get('employee_id'))
    if not employee_id: return jsonify({"status": "error", "message": "Missing employee_id"}), 400
    create_employee(get_db(), employee_id, initial_name=hostname if hostname != employee_id else None)
    current_app.logger.info(f"Heartbeat processed: {employee_id} (Host: {hostname})")
    return jsonify({"status": "ok", "message": "Heartbeat received"}), 200


@api_bp.route('/log/activity', methods=['POST'])
def log_activity():
    current_app.logger.debug(f"/api/log/activity request. API Key OK: {'X-API-KEY' in request.headers}")
    try: data = request.get_json(); assert data is not None
    except: return jsonify({"status": "error", "message": "Invalid/Malformed JSON"}), 400
    
    employee_id = data.get('employee_id')
    activities_payload = data.get('activities')

    if not employee_id: return jsonify({"status": "error", "message": "Missing employee_id"}), 400
    if not isinstance(activities_payload, list): return jsonify({"status": "error", "message": "'activities' must be a list"}), 400
    if not activities_payload: return jsonify({"status": "ok", "message": "Empty 'activities' list"}), 200

    db = get_db()
    server_batch_timestamp = datetime.datetime.now(datetime.timezone.utc)
    all_rules, categories_map, default_cat_id = get_categorization_data(db) # Fetch/use cached rules
    
    activity_docs_to_insert, malformed_count, processed_count = [], 0, 0

    for i, act_data in enumerate(activities_payload):
        if not isinstance(act_data, dict): malformed_count += 1; continue
        try:
            start_time_str, end_time_str = act_data.get("start_time"), act_data.get("end_time")
            duration_s = act_data.get("duration_seconds")

            if not all([start_time_str, end_time_str, duration_s is not None]):
                current_app.logger.warning(f"Missing time/duration for {employee_id}, item {i}: {act_data}")
                malformed_count += 1; continue
            
            start_time = datetime.datetime.fromisoformat(start_time_str)
            end_time = datetime.datetime.fromisoformat(end_time_str)

            if not (isinstance(duration_s, (int, float)) and duration_s >= 0):
                duration_s = int(max(0, (end_time - start_time).total_seconds()))
            
            category_id = get_activity_category_id_from_rules(act_data, all_rules, categories_map, default_cat_id)

            doc = {
                "employee_id": employee_id, "timestamp": server_batch_timestamp,
                "window_title": act_data.get("window_title", "N/A"), "process_name": act_data.get("process_name", "N/A"),
                "start_time": start_time, "end_time": end_time, "duration_seconds": int(duration_s),
                "is_active": act_data.get("is_active", True), "log_type": "activity",
                "category_id": category_id # This will be an ObjectId or None
            }
            activity_docs_to_insert.append(doc)
            processed_count += 1
        except ValueError as ve:
            current_app.logger.warning(f"Time format error for {employee_id}, item {i}: {ve}. Data: {act_data}")
            malformed_count += 1
        except Exception as e_item:
            current_app.logger.error(f"Error processing item {i} for {employee_id}: {e_item}. Data: {act_data}", exc_info=True)
            malformed_count += 1

    if activity_docs_to_insert:
        try:
            result = db.activity_logs.insert_many(activity_docs_to_insert, ordered=False)
            db.employees.update_one({"employee_id": employee_id}, {"$set": {"last_seen": server_batch_timestamp}})
            msg = f"Logged {len(result.inserted_ids)} of {processed_count} activities for {employee_id}." + (f" Skipped {malformed_count}." if malformed_count > 0 else "")
            current_app.logger.info(msg)
            return jsonify({"status": "ok", "message": msg, "inserted": len(result.inserted_ids), "malformed": malformed_count}), 201
        except Exception as e_db:
             current_app.logger.error(f"DB error inserting logs for {employee_id}: {e_db}", exc_info=True)
             return jsonify({"status": "error", "message": "DB bulk insert error"}), 500
    elif malformed_count > 0:
        return jsonify({"status": "error", "message": f"All {malformed_count} activities malformed."}), 400
    else:
         return jsonify({"status": "ok", "message": "No valid activities processed"}), 200

@api_bp.route('/upload/screenshot', methods=['POST'])
def upload_screenshot():
    # ... (Your robust screenshot upload logic from previous version, including SyntaxError fix) ...
    # Ensure current_app.logger is used.
    if 'screenshot' not in request.files: return jsonify({"status": "error", "message": "No screenshot file part"}), 400
    file, emp_id, ts_str = request.files['screenshot'], request.form.get('employee_id'), request.form.get('timestamp')
    if not all([emp_id, ts_str, file, file.filename]): return jsonify({"status": "error", "message": "Missing form data or file"}), 400
    try: timestamp = datetime.datetime.fromisoformat(ts_str)
    except ValueError: return jsonify({"status": "error", "message": "Invalid timestamp"}), 400
    
    db = get_db()
    safe_emp_id = "".join(c if c.isalnum() or c in ['-', '_'] else "_" for c in emp_id)
    if not safe_emp_id: safe_emp_id = "unknown"
    filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{safe_emp_id}_{uuid.uuid4().hex[:8]}.png"
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    if not upload_folder: abort(500, "Upload folder not configured.")
    save_path = os.path.join(upload_folder, filename)

    try:
        file.save(save_path)
        db.activity_logs.insert_one({"employee_id": emp_id, "timestamp": timestamp, "log_type": "screenshot", "screenshot_path": filename})
        db.employees.update_one({"employee_id": emp_id}, {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}})
        current_app.logger.info(f"Screenshot saved: {filename} for {emp_id}")
        return jsonify({"status": "ok", "message": "Screenshot uploaded", "filename": filename}), 201
    except Exception as e:
        current_app.logger.error(f"Error saving screenshot {filename} for {emp_id}: {e}", exc_info=True)
        if os.path.exists(save_path):
            try: os.remove(save_path)
            except Exception as e_del: current_app.logger.error(f"Error deleting partial screenshot {save_path}: {e_del}")
        return jsonify({"status": "error", "message": "Could not save screenshot"}), 500


@api_bp.route('/download/agent')
@login_required
def download_agent_exe():
    # ... (Your robust agent download logic from previous version, uses flash) ...
    agent_path = current_app.config.get('AGENT_EXE_PATH', '')
    if not agent_path or not os.path.exists(agent_path):
        msg = f"Agent executable not found at '{agent_path}'"
        current_app.logger.error(f"{msg} (Admin: '{session.get('username')}')")
        flash(f"{msg}. Please check server configuration.", "danger")
        return redirect(request.referrer or url_for('settings.index'))
    try:
        return send_from_directory(os.path.dirname(agent_path), os.path.basename(agent_path), as_attachment=True, download_name="monitoring_agent.exe")
    except Exception as e:
        current_app.logger.error(f"Error sending agent file: {e}", exc_info=True)
        flash("Error sending agent file.", "danger")
        return redirect(request.referrer or url_for('settings.index'))


@api_bp.route('/active_employees', methods=['GET'])
@login_required
def get_active_employees():
    # ... (Your active employees logic from previous version) ...
    db = get_db()
    threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=current_app.config.get('ACTIVE_EMPLOYEE_THRESHOLD_MINUTES', 5))
    try:
        emps = list(db.employees.find(
            {"last_seen": {"$gte": threshold}, "status": {"$in": ["active", "pending_rename"]}},
            {"_id": 1, "display_name": 1, "employee_id": 1}
        ).sort("display_name", 1).limit(15))
        for emp in emps: emp['_id'] = str(emp['_id'])
        return jsonify(emps)
    except Exception as e:
        current_app.logger.error(f"Error fetching active_employees: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve list"}), 500