# /root/EMS/server/models/db.py
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure # Added OperationFailure
from flask import current_app, g
import bcrypt
import datetime

# --- Database Connection & Initialization ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        try:
            # Ensure MONGO_URI is correctly formed in config.py
            # Example from config.py:
            # MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOSTNAME}:{MONGO_PORT}/{MONGO_DB_NAME}?authSource={MONGO_AUTH_DB}"
            # Or if no auth: MONGO_URI = f"mongodb://{MONGO_HOSTNAME}:{MONGO_PORT}/{MONGO_DB_NAME}"
            
            client = MongoClient(
                current_app.config['MONGO_URI'],
                serverSelectionTimeoutMS=5000, # Timeout for server selection
                uuidRepresentation='standard' # Recommended for modern PyMongo
            )
            # The ismaster command is cheap and does not require auth.
            client.admin.command('ismaster')
            g.db_client = client # Store the client itself for proper closing
            g.db = client[current_app.config['MONGO_DB_NAME']]
            current_app.logger.info(f"Successfully connected to MongoDB: {current_app.config['MONGO_DB_NAME']}")
            initialize_db(g.db) # Call initialization logic
        except ConnectionFailure as e:
            current_app.logger.critical(f"MongoDB Connection Failure: {e}")
            # Optionally, you could raise a custom exception or return None to indicate failure
            raise ConnectionFailure(f"Could not connect to MongoDB: {e}")
        except Exception as e:
            current_app.logger.critical(f"An unexpected error occurred during DB connection: {e}", exc_info=True)
            raise e # Re-raise the exception to halt app or be caught by a higher handler
    return g.db

def close_db(e=None):
    """Closes the database connection client at the end of the request or app context."""
    client = g.pop('db_client', None)
    if client is not None:
        client.close()
        current_app.logger.info("MongoDB client connection closed.")

def create_default_categories(db):
    """Creates default productivity categories if they don't exist."""
    default_categories_data = [
        {"name": "Productive", "description": "Work-related tasks and applications.", "color": "#2ecc71", "is_default": True, "is_fallback": False},
        {"name": "Unproductive", "description": "Non-work related activities, distractions.", "color": "#e74c3c", "is_default": True, "is_fallback": False},
        {"name": "Neutral/Undefined", "description": "General system usage or uncategorized activities.", "color": "#95a5a6", "is_default": True, "is_fallback": True} # Mark one as fallback
    ]
    try:
        for cat_data in default_categories_data:
            # Check if a category with this name already exists
            if db.categories.count_documents({"name": cat_data["name"]}) == 0:
                cat_data["created_at"] = datetime.datetime.now(datetime.timezone.utc)
                cat_data["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
                db.categories.insert_one(cat_data)
                current_app.logger.info(f"Inserted default category: {cat_data['name']}")
    except Exception as e:
        current_app.logger.error(f"Error creating default categories: {e}", exc_info=True)


def initialize_db(db):
    """Check if essential collections and indexes exist, and create them if needed."""
    current_app.logger.info("Starting database schema initialization check...")
    collections_with_indexes = {
        "users": [("username", 1, {"unique": True}), ("email", 1, {"unique": True})],
        "employees": [("employee_id", 1, {"unique": True}), ("last_seen", -1)],
        "activity_logs": [
            ("employee_id", 1), 
            ("timestamp", -1), 
            ("category_id", 1), # For querying by category
            ("log_type", 1),    # For distinguishing screenshots vs activity
            ("process_name", 1), # For faster lookups by process name
            # Consider a text index if you do a lot of free-text search on window_title
            # ("window_title", "text", {"name": "window_title_text_idx"}) 
        ],
        "categories": [("name", 1, {"unique": True})],
        "categorization_rules": [("category_id", 1), ("type", 1), ("pattern", 1)]
    }
    
    existing_collections = db.list_collection_names()

    for coll_name, indexes_to_create in collections_with_indexes.items():
        if coll_name not in existing_collections:
            current_app.logger.info(f"Creating collection: '{coll_name}'")
            try:
                db.create_collection(coll_name)
                if coll_name == 'users':
                    create_default_admin(db)
                elif coll_name == 'categories':
                    create_default_categories(db)
            except Exception as e_coll: # Catch errors during collection creation
                 current_app.logger.error(f"Failed to create collection '{coll_name}': {e_coll}", exc_info=True)
                 continue # Skip index creation for this collection if creation failed

        # Ensure indexes exist
        try:
            current_indexes_on_coll = [idx['name'] for idx in db[coll_name].list_indexes()]
            for idx_details in indexes_to_create:
                idx_field = idx_details[0]
                idx_order_or_type = idx_details[1] # Can be 1, -1, or "text"
                idx_options = idx_details[2] if len(idx_details) > 2 else {}
                
                # Construct a reasonably unique index name
                idx_name = f"{coll_name}_{idx_field}_{str(idx_order_or_type).replace(' ', '_')}_idx"
                if isinstance(idx_field, list): # Compound index
                    idx_name = f"{coll_name}_compound_{'_'.join([f[0] for f in idx_field])}_idx"


                if idx_name not in current_indexes_on_coll:
                    if isinstance(idx_field, list): # For compound indexes like [("employee_id", 1), ("timestamp", -1)]
                        db[coll_name].create_index(idx_field, name=idx_name, **idx_options)
                    else: # For single field indexes or text indexes
                        db[coll_name].create_index([(idx_field, idx_order_or_type)], name=idx_name, **idx_options)
                    current_app.logger.info(f"Created index '{idx_name}' on collection '{coll_name}'.")
        except OperationFailure as op_fail: # Catch specific MongoDB operation failures
            current_app.logger.warning(f"MongoDB OperationFailure during index creation for '{coll_name}': {op_fail}. This might be okay if index already exists with different options.")
        except Exception as e_idx:
            current_app.logger.error(f"Failed to create/ensure indexes for collection '{coll_name}': {e_idx}", exc_info=True)
            
    current_app.logger.info("Database schema initialization check completed.")


def create_default_admin(db):
    """Creates a default admin user if one doesn't exist."""
    try:
        if db.users.count_documents({'username': 'admin'}) == 0:
            hashed_password = bcrypt.hashpw('defaultpassword'.encode('utf-8'), bcrypt.gensalt())
            db.users.insert_one({
                'username': 'admin',
                'email': 'admin@tekpossible.net', # Default email
                'password_hash': hashed_password,
                'role': 'admin',
                'created_at': datetime.datetime.now(datetime.timezone.utc),
                'updated_at': datetime.datetime.now(datetime.timezone.utc)
            })
            current_app.logger.info("Default admin user 'admin' created with password 'defaultpassword'. IMPORTANT: Change this password immediately!")
        else:
            current_app.logger.info("Admin user 'admin' already exists.")
    except Exception as e:
        current_app.logger.error(f"Error creating default admin user: {e}", exc_info=True)


def create_employee(db, employee_id, initial_name=None):
    """Creates a new employee record if it doesn't exist, or updates last_seen."""
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        employee_doc = db.employees.find_one({"employee_id": employee_id})
        
        if not employee_doc:
            display_name_to_set = initial_name if initial_name and initial_name != employee_id else f"User_{employee_id[:8]}"
            
            employee_data = {
                "employee_id": employee_id,
                "display_name": display_name_to_set,
                "status": "pending_rename", 
                "first_seen": now,
                "last_seen": now,
                "created_at": now,
                "updated_at": now
                # Add other default fields like 'team', 'department' as None or default
            }
            result = db.employees.insert_one(employee_data)
            current_app.logger.info(f"Created new employee record for '{employee_id}' with display name '{employee_data['display_name']}'.")
            return result.inserted_id
        else:
            db.employees.update_one(
                {"_id": employee_doc["_id"]}, # Use _id for precise update
                {"$set": {"last_seen": now, "updated_at": now}}
            )
            # current_app.logger.debug(f"Employee {employee_id} already exists, updated last_seen.")
            return employee_doc['_id']
    except Exception as e:
        current_app.logger.error(f"Error in create_employee for {employee_id}: {e}", exc_info=True)
        return None # Indicate failure