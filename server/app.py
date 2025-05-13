# /root/EMS/server/app.py
from flask import Flask, session, g, render_template, redirect, url_for, current_app
from config import Config
from models.db import close_db, get_db # get_db also calls initialize_db
import os
import logging # For more control over logging if needed

# Import Blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.users import users_bp
from routes.api import api_bp
from routes.reports import reports_bp   # <-- IMPORT Reports Blueprint
from routes.settings import settings_bp # <-- IMPORT Settings Blueprint

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure the instance folder exists (Flask might use it for some things)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError as e:
        app.logger.warning(f"Could not create instance path: {e}") # Use app.logger

    # --- Logging Configuration (Basic example, expand as needed) ---
    if not app.debug: # More detailed logging in production
        # Example: Log to a file
        # import logging
        # from logging.handlers import RotatingFileHandler
        # file_handler = RotatingFileHandler('ems_server.log', maxBytes=10240, backupCount=10)
        # file_handler.setFormatter(logging.Formatter(
        #     '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        # ))
        # file_handler.setLevel(logging.INFO)
        # app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO) # Default level for production
    else:
        app.logger.setLevel(logging.DEBUG) # Debug level for development

    app.logger.info('EMS Application starting up...')


    # Initialize DB connection context
    # @app.before_request
    # def before_request_func():
    #     # get_db() will be called when needed by a route, establishing connection.
    #     # No explicit action needed here if get_db() handles its own establishment.
    #     pass

    @app.teardown_appcontext
    def teardown_db(exception=None): # Add exception parameter
        # Close the database connection when the app context ends
        close_db(exception) # Pass exception to close_db if it uses it

    # Simple check if admin user exists on startup (via initialize_db in get_db)
    # This is done implicitly when get_db() is first called.
    with app.app_context():
        try:
            get_db() # This will trigger initialize_db if collections are missing
            app.logger.info("Database check/initialization completed during app startup.")
        except Exception as e:
            app.logger.critical(f"FATAL: Could not initialize database connection during startup: {e}")
            # In a real scenario, you might want to prevent the app from starting or exit.
            # For now, we log and continue, but parts of the app will fail.


    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp) # No prefix, handles root/dashboard
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(reports_bp, url_prefix='/reports')     # <-- REGISTER Reports Blueprint
    app.register_blueprint(settings_bp, url_prefix='/settings')   # <-- REGISTER Settings Blueprint

    # Basic root route - redirect to login or dashboard
    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect(url_for('dashboard.view_dashboard'))
        return redirect(url_for('auth.login'))

    # Simple error handlers (customize as needed)
    @app.errorhandler(404)
    def not_found_error(error):
        app.logger.warning(f"404 Not Found: {request.url} (Referer: {request.referrer})")
        # Pass data needed by layout.html, like pending_rename_count
        # This might require fetching it here or ensuring layout can handle its absence.
        pending_count = 0
        if 'user_id' in session: # Only try to fetch if user is logged in
            try:
                db = get_db()
                pending_count = db.employees.count_documents({"status": "pending_rename"})
            except Exception: # Broad except because DB might not be available
                pass
        return render_template('errors/404.html', pending_rename_count=pending_count), 404

    @app.errorhandler(500)
    def internal_error(error):
        # Log the error details here
        app.logger.error(f"Server Error (500): {error}", exc_info=True) # exc_info=True includes traceback
        # db.session.rollback() # If using SQLAlchemy
        pending_count = 0
        if 'user_id' in session:
            try:
                db = get_db()
                pending_count = db.employees.count_documents({"status": "pending_rename"})
            except Exception:
                pass
        return render_template('errors/500.html', pending_rename_count=pending_count), 500

    @app.errorhandler(Exception) # Catch-all for other unhandled exceptions
    def unhandled_exception(e):
        app.logger.error(f"Unhandled Exception: {e}", exc_info=True)
        # You might want a generic error page or just rely on the 500 handler if it's an HTTP exception
        pending_count = 0
        if 'user_id' in session:
            try:
                db = get_db()
                pending_count = db.employees.count_documents({"status": "pending_rename"})
            except Exception:
                pass
        return render_template('errors/500.html', error_message="An unexpected error occurred.", pending_rename_count=pending_count), 500


    return app

if __name__ == '__main__':
    app = create_app()
    # Use waitress or gunicorn for production instead of Flask's built-in server
    # The host 0.0.0.0 makes it accessible externally.
    app.run(host='0.0.0.0', port=5000, debug=(Config.FLASK_ENV == 'development'))