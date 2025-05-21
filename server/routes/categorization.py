# /root/EMS/server/routes/categorization.py
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app, session
)
from models.db import get_db
from routes.auth import login_required
from bson import ObjectId # For converting string ID back to ObjectId for edits/deletes later
import datetime

categorization_bp = Blueprint('categorization', __name__)

# --- CATEGORY MANAGEMENT ---
@categorization_bp.route('/')
@login_required
def manage_categories():
    """Lists categories and provides a form to add a new one."""
    db = get_db()
    categories_list = []
    try:
        categories_list = list(db.categories.find().sort("name", 1))
    except Exception as e:
        current_app.logger.error(f"Error fetching categories: {e}", exc_info=True)
        flash("Could not retrieve categories from the database.", "danger")

    # For layout consistency, always fetch pending_rename_count
    pending_rename_count = 0
    try:
        pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    except Exception as e:
        current_app.logger.error(f"Error fetching pending_rename_count for categorization page: {e}")


    return render_template('categorization/manage_categories.html',
                           categories=categories_list,
                           active_page='categorization', # For sidebar highlighting
                           pending_rename_count=pending_rename_count)

@categorization_bp.route('/category/add', methods=['POST'])
@login_required
def add_category():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        color = request.form.get('color', '#cccccc').strip() # Default color

        if not name:
            flash("Category name is required.", "warning")
        elif db.categories.count_documents({"name": name}) > 0:
            flash(f"A category with the name '{name}' already exists.", "warning")
        else:
            try:
                new_category = {
                    "name": name,
                    "description": description,
                    "color": color,
                    "created_at": datetime.datetime.now(datetime.timezone.utc),
                    "updated_at": datetime.datetime.now(datetime.timezone.utc),
                    "is_default": False # Manually added categories are not "default" system ones
                }
                db.categories.insert_one(new_category)
                flash(f"Category '{name}' added successfully.", "success")
                current_app.logger.info(f"Admin '{session.get('username')}' added category: {name}")
            except Exception as e:
                current_app.logger.error(f"Error adding category '{name}': {e}", exc_info=True)
                flash(f"An error occurred while adding the category: {str(e)}", "danger")
    
    return redirect(url_for('categorization.manage_categories'))


@categorization_bp.route('/category/edit/<category_id_str>', methods=['GET', 'POST'])
@login_required
def edit_category(category_id_str):
    db = get_db()
    try:
        category_oid = ObjectId(category_id_str)
    except Exception:
        flash("Invalid category ID format.", "danger")
        return redirect(url_for('categorization.manage_categories'))

    category = db.categories.find_one({"_id": category_oid})
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for('categorization.manage_categories'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        color = request.form.get('color', '#cccccc').strip()
        
        form_errors = False
        if not name:
            flash("Category name is required.", "warning")
            form_errors = True
        # Check if name changed and if new name conflicts (excluding current doc)
        elif name != category.get('name') and db.categories.count_documents({"name": name, "_id": {"$ne": category_oid}}) > 0:
            flash(f"Another category with the name '{name}' already exists.", "warning")
            form_errors = True
        
        if not form_errors:
            try:
                update_data = {
                    "name": name,
                    "description": description,
                    "color": color,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc)
                }
                db.categories.update_one({"_id": category_oid}, {"$set": update_data})
                flash(f"Category '{name}' updated successfully.", "success")
                current_app.logger.info(f"Admin '{session.get('username')}' updated category ID: {category_id_str} to name: {name}")
                return redirect(url_for('categorization.manage_categories'))
            except Exception as e:
                flash(f"Error updating category: {str(e)}", "danger")
                current_app.logger.error(f"Error updating category {category_id_str}: {e}", exc_info=True)
        # If errors, re-render form below (or fall through to GET)
    
    pending_rename_count = db.employees.count_documents({"status": "pending_rename"})
    # For GET or if POST had errors and re-renders
    return render_template('categorization/edit_category_form.html', 
                           category=category, 
                           active_page='categorization',
                           pending_rename_count=pending_rename_count)


@categorization_bp.route('/category/delete/<category_id_str>', methods=['POST']) # POST for deletion
@login_required
def delete_category(category_id_str):
    db = get_db()
    try:
        category_oid = ObjectId(category_id_str)
    except Exception:
        flash("Invalid category ID format.", "danger")
        return redirect(url_for('categorization.manage_categories'))

    category = db.categories.find_one({"_id": category_oid})
    if not category:
        flash("Category not found.", "danger")
    elif category.get("is_default"): # Prevent deletion of seeded default categories
        flash(f"Default category '{category.get('name')}' cannot be deleted.", "warning")
    else:
        try:
            # Optional: Check if any rules are associated with this category
            rules_count = db.categorization_rules.count_documents({"category_id": category_oid})
            if rules_count > 0:
                flash(f"Cannot delete category '{category.get('name')}' as it has {rules_count} associated rule(s). Please delete or reassign rules first.", "warning")
            else:
                db.categories.delete_one({"_id": category_oid})
                flash(f"Category '{category.get('name')}' deleted successfully.", "success")
                current_app.logger.info(f"Admin '{session.get('username')}' deleted category ID: {category_id_str}, Name: {category.get('name')}")
        except Exception as e:
            flash(f"Error deleting category: {str(e)}", "danger")
            current_app.logger.error(f"Error deleting category {category_id_str}: {e}", exc_info=True)
            
    return redirect(url_for('categorization.manage_categories'))

# TODO: Add routes and logic for managing Categorization Rules (add, edit, delete rule)
# These will be similar to category management but link to a category.