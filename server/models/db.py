from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from flask import current_app, g
import bcrypt # For password hashing
import datetime

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        try:
            client = MongoClient(
                current_app.config['MONGO_URI'],
                serverSelectionTimeoutMS=5000 # 5 second timeout
            )
            # The ismaster command is cheap and does not require auth.
            client.admin.command('ismaster')
            g.db = client[current_app.config['MONGO_DB_NAME']]
            print(f"Successfully connected to MongoDB: {current_app.config['MONGO_DB_NAME']}")
            # --- Database and Collection Check/Creation ---
            initialize_db(g.db)
            # --- End Check/Creation ---
        except ConnectionFailure as e:
            print(f"Could not connect to MongoDB: {e}")
            # Decide how to handle connection failure (e.g., raise error, return None)
            # For now, let's raise it so the app fails visibly during development
            raise ConnectionFailure(f"Could not connect to MongoDB: {e}")
        except Exception as e:
            print(f"An error occurred during DB connection: {e}")
            raise e
    return g.db

def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db_client = g.pop('db_client', None) # Assuming client stored in g.db_client if needed
    if db_client is not None:
        db_client.close()
        print("MongoDB connection closed.")

def initialize_db(db):
    """Check if essential collections exist and create an initial admin user if needed."""
    required_collections = ['users', 'activity_logs', 'employees'] # Add more as needed
    existing_collections = db.list_collection_names()

    for coll in required_collections:
        if coll not in existing_collections:
            print(f"Creating collection: {coll}")
            db.create_collection(coll)
            if coll == 'users':
                # Create a default admin user if the users collection was just created
                print("Users collection created. Creating default admin user...")
                create_default_admin(db)
            if coll == 'employees':
                 # Index employee ID for faster lookups
                db.employees.create_index("employee_id", unique=True)
                print("Created index on employees.employee_id")


    # Optionally add indexes here
    db.activity_logs.create_index([("employee_id", 1), ("timestamp", -1)])
    print("Checked/Created essential DB collections and indexes.")


def create_default_admin(db):
    """Creates a default admin user if one doesn't exist."""
    if db.users.count_documents({'username': 'admin'}) == 0:
        # IMPORTANT: Change the default password immediately!
        hashed_password = bcrypt.hashpw('defaultpassword'.encode('utf-8'), bcrypt.gensalt())
        db.users.insert_one({
            'username': 'admin',
            'email': 'admin@tekpossible.net', # From screenshot
            'password_hash': hashed_password,
            'role': 'admin',
            'created_at': datetime.datetime.now(datetime.timezone.utc)
        })
        print("Default admin user 'admin' created with password 'defaultpassword'. CHANGE IT NOW!")
    else:
        print("Admin user already exists.")

# --- User Helper Functions ---
def create_employee(db, employee_id, initial_name=None):
    """Creates a new employee record when an agent first connects."""
    if not db.employees.find_one({"employee_id": employee_id}):
        employee_data = {
            "employee_id": employee_id,
            "display_name": initial_name or f"New User ({employee_id})", # Default name
            "status": "pending_rename", # Flag for admin
            "first_seen": datetime.datetime.now(datetime.timezone.utc),
            "last_seen": datetime.datetime.now(datetime.timezone.utc),
            # Add other fields like 'team', 'department' etc. later
        }
        result = db.employees.insert_one(employee_data)
        print(f"Created new employee record for {employee_id}")
        return result.inserted_id
    else:
        # Update last seen if employee already exists
        db.employees.update_one(
            {"employee_id": employee_id},
            {"$set": {"last_seen": datetime.datetime.now(datetime.timezone.utc)}}
        )
        print(f"Employee {employee_id} already exists, updated last_seen.")
        return db.employees.find_one({"employee_id": employee_id})['_id']