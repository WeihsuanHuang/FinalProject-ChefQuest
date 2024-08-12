from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from pymongo import MongoClient
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask_bcrypt import Bcrypt
import boto3


# Flask Blueprint setup
auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()

# Database setup
@auth_bp.before_app_request
def setup_db():
    if not hasattr(current_app, 'mongo_client'):
        mongo_uri = current_app.config['MONGO_URI']
        current_app.mongo_client = MongoClient(mongo_uri)
        current_app.db = current_app.mongo_client.user_login_system
        current_app.users_collection = current_app.db.users
        current_app.favorites_collection = current_app.db.favorites
        current_app.meal_plans_collection = current_app.db.meal_plans
        current_app.shopping_lists_collection = current_app.db.shopping_lists

# Helper functions
def get_user_by_email(email):
    return current_app.users_collection.find_one({"email": email})

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def update_user_intro_status(email, status):
    try:
        result = current_app.users_collection.update_one(
            {"email": email},
            {"$set": {"has_seen_intro": status}}
        )
        if result.modified_count == 1:
            print(f"Updated intro status for user {email}")
            return True
        else:
            print(f"Failed to update intro status for user {email}")
            return False
    except Exception as e:
        print(f"Error updating intro status for user {email}: {str(e)}")
        return False

# Routes
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if get_user_by_email(email):
            flash('Email already exists!')
            return redirect(url_for('auth.signup'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        current_app.users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password,
            'has_seen_intro': False
        })
        flash('Signup successful! Please log in.')
        return redirect(url_for('auth.login'))

    return render_template('signup.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = get_user_by_email(email)

        if user and bcrypt.check_password_hash(user['password'], password):
            session['email'] = email
            session['has_seen_intro'] = user.get('has_seen_intro', False)
            session['show_intro_guide'] = not user.get('has_seen_intro', False)
            return redirect(url_for('auth.home'))

        flash('Invalid email or password!')

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.pop('email', None)
    flash('Logged out successfully!')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    user = get_user_by_email(email)

    if request.method == 'POST':
        new_username = request.form.get('username')
        allergies = request.form.getlist('allergy')

        # Handle file upload
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and allowed_file(file.filename):
                file_extension = os.path.splitext(file.filename)[1]
                user_id = str(user['_id'])
                filename = secure_filename(f"profile_{user_id}{file_extension}")
                try:
                    s3 = boto3.client(
                        "s3",
                        region_name=current_app.config["S3_REGION"],
                        aws_access_key_id=current_app.config["S3_KEY"],
                        aws_secret_access_key=current_app.config["S3_SECRET"]
                    )
                    s3.upload_fileobj(file, current_app.config["S3_BUCKET"], filename)
                    file_url = f"{current_app.config['S3_LOCATION']}{filename}"
                    current_app.users_collection.update_one(
                        {'email': email}, {'$set': {'profile_photo': file_url}}
                    )
                except Exception as e:
                    return jsonify({'error': str(e)}), 500

        # Update the user's data in the database
        current_app.users_collection.update_one(
            {'email': email}, {'$set': {'username': new_username, 'allergies': allergies}}
        )
        session['username'] = new_username

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'message': 'Profile updated successfully!'})
        else:
            flash('Profile updated successfully!')
            return redirect(url_for('auth.profile'))

    return render_template('profile.html',
                           username=user['username'],
                           email=user['email'],
                           allergies=user.get('allergies', []),
                           profile_photo=user.get('profile_photo'))

@auth_bp.route('/home')
def home():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    show_intro_guide = session.get('show_intro_guide', False)
    email = session['email']
    user = current_app.users_collection.find_one({'email': email})

    if not user:
        return redirect(url_for('auth.login'))

    username = user.get('username', 'User')
    meals_today = []

    if not show_intro_guide:
        today_date_str = datetime.today().strftime('%Y-%m-%d')
        today_meal_plan = current_app.meal_plans_collection.find_one({
            'email': email,
            'meals': {
                '$elemMatch': {
                    'Date': today_date_str,
                    '$or': [
                        {'cook_status': {'$ne': True}},
                        {'cook_status': {'$exists': False}}
                    ]
                }
            }
        })

        if today_meal_plan:
            meal_type_order = {"Breakfast": 0, "Lunch": 1, "Dinner": 2}
            meals_today = sorted(
                [meal for meal in today_meal_plan['meals']
                 if meal['Date'] == today_date_str and not meal.get('cook_status', False)],
                key=lambda meal: meal_type_order.get(meal['MealType'], 3)
            )

    return render_template('home.html',
                           username=username,
                           meals_today=meals_today,
                           show_intro_guide=show_intro_guide)

@auth_bp.route('/update_intro_status', methods=['POST'])
def update_intro_status():
    if 'email' in session:
        update_user_intro_status(session['email'], True)
        session['has_seen_intro'] = True
        session['show_intro_guide'] = False
        return jsonify({'success': True})
    return jsonify({'success': False}), 401