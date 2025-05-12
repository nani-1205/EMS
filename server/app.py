from flask import Flask, session, g, render_template, redirect, url_for
from config import Config
from models.db import close_db, get_db
import os

# Import Blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.users import users_bp
from routes.api import api_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize DB connection context
    @app.before_request
    def before_request():
        # Establish DB connection for the request context
        # The actual connection happens in get_db() when first called
        pass # get_db() handles connection pooling/reuse within context

    @app.teardown_appcontext
    def teardown_db(exception):
        # Close the database connection when the app context ends
        close_db(exception)

    # Simple check if admin user exists on startup (via initialize_db in get_db)
    with app.app_context():
        try:
            get_db() # This will trigger initialize_db if collections are missing
            print("Database check/initialization completed.")
        except Exception as e:
            print(f"FATAL: Could not initialize database connection: {e}")
            # Decide how to handle this - exit, fallback, etc.
            # For now, we'll print the error and continue, but the app might not function.


    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp) # No prefix, handles root/dashboard
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Basic root route - redirect to login or dashboard
    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect(url_for('dashboard.view_dashboard'))
        return redirect(url_for('auth.login'))

    # Simple error handlers (customize as needed)
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        # Log the error details here
        print(f"Server Error: {error}")
        # db.session.rollback() # If using SQLAlchemy
        return render_template('errors/500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    # Use waitress or gunicorn for production instead of Flask's built-in server
    app.run(host='0.0.0.0', port=5000, debug=(Config.FLASK_ENV == 'development'))