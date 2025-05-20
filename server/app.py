# /root/EMS/server/app.py  (or /opt/employee/EMS/server/app.py based on your logs)
from flask import Flask, session, g, render_template, redirect, url_for, current_app, request # <-- ADD request HERE
from config import Config
from models.db import close_db, get_db
import os
import logging

# Import Blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.users import users_bp
from routes.api import api_bp
from routes.reports import reports_bp
from routes.settings import settings_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError as e:
        app.logger.warning(f"Could not create instance path: {e}")

    if not app.debug:
        app.logger.setLevel(logging.INFO)
    else:
        app.logger.setLevel(logging.DEBUG)
    app.logger.info('EMS Application starting up...')

    @app.teardown_appcontext
    def teardown_db(exception=None):
        close_db(exception)

    with app.app_context():
        try:
            get_db()
            app.logger.info("Database check/initialization completed during app startup.")
        except Exception as e:
            app.logger.critical(f"FATAL: Could not initialize database connection during startup: {e}")

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(settings_bp, url_prefix='/settings')

    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect(url_for('dashboard.view_dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(404)
    def not_found_error(error): # error object is passed here
        # Now 'request' is imported and can be used
        app.logger.warning(f"404 Not Found: {request.url} (Referer: {request.referrer}) - Error: {error}")
        pending_count = 0
        if 'user_id' in session:
            try:
                db = get_db()
                pending_count = db.employees.count_documents({"status": "pending_rename"})
            except Exception:
                pass
        return render_template('errors/404.html', pending_rename_count=pending_count), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Server Error (500): {error} for URL {request.url}", exc_info=True)
        pending_count = 0
        if 'user_id' in session:
            try:
                db = get_db()
                pending_count = db.employees.count_documents({"status": "pending_rename"})
            except Exception:
                pass
        return render_template('errors/500.html', pending_rename_count=pending_count), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        # Log the specific URL that caused the unhandled exception
        url_causing_error = "Unknown URL (request context not available)"
        if request: # Check if request context is available
            url_causing_error = request.url
        app.logger.error(f"Unhandled Exception: {e} at URL: {url_causing_error}", exc_info=True)
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
    app.run(host='0.0.0.0', port=5000, debug=(Config.FLASK_ENV == 'development'))