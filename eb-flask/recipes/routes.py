from flask import Blueprint, render_template, request, flash, redirect, session, url_for, jsonify, current_app
from urllib.parse import unquote
from utils import search_recipes, fetch_recipes, get_full_recipe_details, get_recipes_information, simplify_ingredients, compare_images, get_one_recipe_information
from pymongo import MongoClient
from datetime import datetime, timedelta
from auth.routes import get_user_by_email
from bson import ObjectId
import uuid
import os
import math
import logging
import boto3
from werkzeug.utils import secure_filename


# Flask Blueprint setup
recipes_bp = Blueprint('recipes', __name__)

@recipes_bp.before_app_request
def setup_db():
    if not hasattr(current_app, 'mongo_client'):
        # Setup database connection
        mongo_uri = current_app.config['MONGO_URI']
        current_app.mongo_client = MongoClient(mongo_uri)
        current_app.db = current_app.mongo_client.user_login_system
        current_app.users_collection = current_app.db.users
        current_app.favorites_collection = current_app.db.favorites
        current_app.meal_plans_collection = current_app.db.meal_plans
        current_app.shopping_lists_collection = current_app.db.shopping_lists


@recipes_bp.route('/explore', methods=['GET', 'POST'])
def explore():
    api_key = current_app.config['RECIPE_API_KEY']
    if request.method == 'POST':
        query = request.form.get('search_query', '')
        recipes = search_recipes(api_key, query)
        return render_template('explore.html', recipes=recipes, search_query=query)
    
    search_query = request.args.get('search_query', '')
    decoded_search_query = unquote(search_query)
    recipes = search_recipes(api_key, decoded_search_query)
    return render_template('explore.html', recipes=recipes, search_query=decoded_search_query)

@recipes_bp.route('/recipe/<int:recipe_id>')
def view_recipe(recipe_id):
    api_key = current_app.config['RECIPE_API_KEY']
    search_query = request.args.get('search_query', '')
    recipe = get_full_recipe_details(api_key, recipe_id)
    if recipe:
        return render_template('view_recipe.html', recipe=recipe, search_query=search_query)
    return "Recipe not found", 404

@recipes_bp.route('/recipe/<int:recipe_id>/add_to_favorites', methods=['POST'])
def add_to_favorites(recipe_id):
    if 'email' not in session:
        flash('You need to be logged in to save favorites.')
        return redirect(url_for('auth.login'))

    recipe_title = request.form.get('title')
    recipe_image = request.form.get('image')
    email = session['email']

    # Check if the recipe already exists in favorites
    existing_favorite = current_app.favorites_collection.find_one({
        'email': email,
        'RecipeID': recipe_id
    })

    if existing_favorite:
        return jsonify({'message': 'Recipe is already in Saved!'}), 200
    else:
        current_app.favorites_collection.insert_one({
            'email': email,
            'RecipeID': recipe_id,
            'Title': recipe_title,
            'ImageURL': recipe_image
        })
        flash('Recipe added to favorites!')

    return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id, search_query=request.args.get('search_query', '')))

@recipes_bp.route('/favorites')
def favorites():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    favorite_recipes_cursor = current_app.favorites_collection.find({'email': email})
    favorite_recipes = list(favorite_recipes_cursor)  # Convert cursor to list
    return render_template('favorites.html', favorite_recipes=favorite_recipes)

@recipes_bp.route('/delete_from_favorites/<recipe_id>', methods=['DELETE'])
def delete_from_favorites(recipe_id):
    if 'email' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    email = session['email']
    
    try:
        recipe_id = int(recipe_id)  # Convert recipe_id to integer
    except ValueError:
        return jsonify({"error": "Invalid recipe ID format"}), 400

    query = {"RecipeID": recipe_id, "email": email}  # Updated field name to "email"

    result = current_app.favorites_collection.delete_one(query)
    
    if result.deleted_count == 1:
        return jsonify({"success": True}), 200
    else:
        return jsonify({"error": "Recipe not found or you are not authorized to delete it"}), 404

from datetime import datetime, timedelta

@recipes_bp.route('/planner', methods=['GET', 'POST'])
def planner():
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        return redirect(url_for('recipes.meal_type', start_date=start_date, end_date=end_date))

    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']

    # Retrieve existing date ranges from the database for the logged-in user
    existing_plans = current_app.meal_plans_collection.find({"email": email}, {"duration": 1, "_id": 0})
    disabled_dates = set()

    for plan in existing_plans:
        start = datetime.strptime(plan["duration"]["start_date"], "%Y-%m-%d")
        end = datetime.strptime(plan["duration"]["end_date"], "%Y-%m-%d")
        current_date = start
        while current_date <= end:
            disabled_dates.add(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

    # Convert the set to a sorted list
    disabled_dates = sorted(disabled_dates)
    print("Disabled Dates:", disabled_dates)  # Debugging

    # Render the template with disabled dates
    return render_template('planner.html', disabled_dates=disabled_dates)

@recipes_bp.route('/meal_type', methods=['GET', 'POST'])
def meal_type():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        meal_types = request.form.to_dict(flat=False)
        session['meal_types'] = meal_types
        session['start_date'] = request.form.get('start_date')
        session['end_date'] = request.form.get('end_date')
        return redirect(url_for('recipes.generate_meal_plan'))

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    date_range = [start_date]
    if start_date != end_date:
        current_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        while current_date < end_date:
            current_date += timedelta(days=1)
            date_range.append(current_date.strftime('%Y-%m-%d'))
    return render_template('meal_type.html', date_range=date_range)

@recipes_bp.route('/generate_meal_plan', methods=['GET', 'POST'])
def generate_meal_plan():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    user = get_user_by_email(email)
    api_key = current_app.config['RECIPE_API_KEY']

    if request.method == 'POST':
        meal_plan = session.get('meal_plan')
        if meal_plan:
            inserted_id = current_app.meal_plans_collection.insert_one(meal_plan).inserted_id
            meal_plan['_id'] = str(inserted_id)
            flash('The meal plan is saved successfully!')
            return redirect(url_for('recipes.my_plan'))

    meal_types = session.get('meal_types')
    start_date = session.get('start_date')
    end_date = session.get('end_date')

    if not meal_types or not start_date or not end_date:
        flash('Please select a date range and meal types first.')
        return redirect(url_for('recipes.planner'))

    meal_plan_template = {
        "email": session['email'],
        "duration": {"start_date": start_date, "end_date": end_date},
        "createDate": str(datetime.today().date()),
        "meals": []
    }

    date_range = [start_date]
    if start_date != end_date:
        current_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        while current_date < end_date:
            current_date += timedelta(days=1)
            date_range.append(current_date.strftime('%Y-%m-%d'))

    for date in date_range:
        for meal_type in meal_types.get(date, []):
                intolerances = user.get('allergies', [])
                recipes = fetch_recipes(api_key, meal_type, intolerances=intolerances)
                for recipe in recipes:
                    meal_plan_template['meals'].append({
                        'MealID': str(uuid.uuid4()),
                        "Date": date,
                        "MealType": meal_type,
                        "Recipe":recipe
                        
                    })

    session['meal_plan'] = meal_plan_template
    return render_template('generate.html', meal_plan=meal_plan_template)

@recipes_bp.route('/my_plan', methods=['GET'])
def my_plan():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    meal_plans = list(current_app.meal_plans_collection.find({"email": email}).sort("duration.start_date", 1))

    return render_template('my_plan.html', meal_plans=meal_plans)

@recipes_bp.route('/delete_meal_plan/<plan_id>', methods=['DELETE'])
def delete_meal_plan(plan_id):
    if 'email' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    email = session['email']
    result = current_app.meal_plans_collection.delete_one({"_id": ObjectId(plan_id), "email": email})

    if result.deleted_count == 1:
        return jsonify({"success": True}), 200
    else:
        return jsonify({"error": "Meal plan not found or you are not authorized to delete it"}), 404

@recipes_bp.route('/manage_meal_plan/<plan_id>', methods=['GET'])
def manage_meal_plan(plan_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    meal_plan = current_app.meal_plans_collection.find_one({"_id": ObjectId(plan_id)})
    
    # Meal type order for sorting
    meal_type_order = {"Breakfast": 0, "Lunch": 1, "Dinner": 2}
    meal_plan['meals'] = sorted(meal_plan['meals'], key=lambda meal: (meal['Date'], meal_type_order.get(meal['MealType'], 3)))

    if not meal_plan:
        flash('Meal plan not found.')
        return redirect(url_for('recipes.my_plan'))

    return render_template('manage.html', meal_plan=meal_plan)

@recipes_bp.route('/update_meal_plan/<plan_id>', methods=['POST'])
def update_meal_plan(plan_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    meal_plan = current_app.meal_plans_collection.find_one({"_id": ObjectId(plan_id)})
    if not meal_plan:
        flash('Meal plan not found.')
        return redirect(url_for('recipes.my_plan'))

    print("Form data received:")  # Debug statement
    for key in request.form:
        print(f"{key}: {request.form[key]}")  # Debug statement

    updated_meals = []
    removed_MealID = []

    for meal in meal_plan['meals']:
        meal_id = meal.get('MealID')
        print(f"Processing meal ID: {meal_id}")  # Debug statement
        if meal_id and request.form.get(f'remove-{meal_id}') == 'true':
            print(f"Removing meal ID: {meal_id}")  # Debug statement
            removed_MealID.append(meal_id)
            continue  # Skip this meal if marked for removal
        updated_meals.append(meal)

    # Sort the updated meals by date
    updated_meals.sort(key=lambda x: x['Date'])

    # Update the meal plan in the database
    current_app.meal_plans_collection.update_one(
        {"_id": ObjectId(plan_id)},
        {"$set": {"meals": updated_meals}}
    )

    flash('Meal plan updated successfully!')
    return redirect(url_for('recipes.my_plan'))

@recipes_bp.route('/select_meal_plan/<int:recipe_id>', methods=['GET'])
def select_meal_plan(recipe_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    meal_plans = list(current_app.meal_plans_collection.find({"email": email}).sort("duration.start_date", 1))
    return render_template('select_meal_plan.html', meal_plans=meal_plans, recipe_id=recipe_id)

@recipes_bp.route('/add_to_meal_plan_form/<int:recipe_id>/<plan_id>', methods=['GET'])
def add_to_meal_plan_form(recipe_id, plan_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    print(f"Received recipe_id: {recipe_id}, plan_id: {plan_id}")  # Debugging
    email = session['email']

    meal_plan = current_app.meal_plans_collection.find_one({"_id": ObjectId(plan_id)})
    if not meal_plan:
        print("Meal plan not found")
        flash('Meal plan not found.')
        return redirect(url_for('recipes.select_meal_plan', recipe_id=recipe_id))

    start_date = meal_plan['duration']['start_date']
    end_date = meal_plan['duration']['end_date']

    api_key = current_app.config['RECIPE_API_KEY']
    recipe = get_one_recipe_information(api_key, recipe_id)
    if not recipe:
        print(f"Recipe not found with recipe_id: {recipe_id}")
        flash('Recipe not found.')
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id))

    return render_template('add_to_meal_plan_form.html', recipe=recipe, plan_id=plan_id, start_date=start_date, end_date=end_date)

@recipes_bp.route('/add_to_meal_plan/<int:recipe_id>/<plan_id>', methods=['POST'])
def add_to_meal_plan(recipe_id, plan_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    user = current_app.users_collection.find_one({'email': email})

    if not user:
        return redirect(url_for('auth.login'))

    date = request.form.get('date')
    meal_type = request.form.get('meal_type')
    print(f"Received form data - Date: {date}, Meal Type: {meal_type}")  # Debugging

    print(f"Looking for recipe with recipe_id: {recipe_id}")

    
    api_key = current_app.config['RECIPE_API_KEY']
    # Ensure recipe_id is treated as an integer
    recipe = get_one_recipe_information(api_key, recipe_id)
    if not recipe:
        print(f"Recipe not found with recipe_id: {recipe_id}")
        flash('Recipe not found.')
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id))

    recipedetail = {
        'ImageURL': recipe['image'],
        'RecipeID': recipe['id'],
        'Title': recipe['title']
    }
    #print(f"Recipe details: {recipedetail}")

    meal_plan = current_app.meal_plans_collection.find_one({'_id': ObjectId(plan_id)})
    if meal_plan:
        print("Meal plan found, adding recipe to it")
        meal_plan['meals'].append({
            'Date': date,
            'MealID': str(uuid.uuid4()),
            'MealType': meal_type,
            'Recipe': recipedetail
        })
        current_app.meal_plans_collection.update_one(
            {'_id': meal_plan['_id']},
            {'$set': {'meals': meal_plan['meals']}}
        )
        print("Meal plan updated successfully")
    else:
        print("Meal plan not found")

    flash('Meal added to meal plan successfully!')
    return redirect(url_for('recipes.my_plan'))

@recipes_bp.route('/generate_ingredients/<plan_id>', methods=['POST'])
def generate_ingredients(plan_id):
    if 'email' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    email = session['email']
    meal_plan = current_app.meal_plans_collection.find_one({"_id": ObjectId(plan_id), "email": email})

    if not meal_plan:
        return jsonify({"success": False, "message": "Meal plan not found"}), 404

    recipe_ids = [meal['Recipe']['RecipeID'] for meal in meal_plan['meals'] if 'Recipe' in meal and 'RecipeID' in meal['Recipe']]
    print("Debug: recipe_ids =", recipe_ids)  # Debug log

    detailed_ingredients = []

    api_key = current_app.config['RECIPE_API_KEY']
    recipes_info = get_recipes_information(api_key, recipe_ids)
    for recipe_info in recipes_info:
        if recipe_info:
            for ingredient in recipe_info['extendedIngredients']:
                detailed_ingredients.append({
                    'aisle': ingredient['aisle'],
                    'name': ingredient['name'],
                    'amount': ingredient['amount'],
                    'unit': ingredient['unit'] if ingredient['unit'] else 'unit not specified',
                })

    # Apply the simplify_ingredients function
    simplified_ingredients = simplify_ingredients(detailed_ingredients)

    return jsonify({"success": True, "message": "Ingredients added to shopping list", "ingredients": simplified_ingredients})

@recipes_bp.route('/save_ingredients', methods=['POST'])
def save_ingredients():
    if 'email' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    email = session['email']
    data = request.json
    plan_id = data.get('plan_id')
    selected_ingredients = data.get('selected_ingredients')

    # Fetch the meal plan to get the duration
    meal_plan = current_app.meal_plans_collection.find_one({"_id": ObjectId(plan_id), "email": email})
    if not meal_plan:
        return jsonify({"success": False, "message": "Meal plan not found"}), 404

    start_date = meal_plan['duration']['start_date']
    end_date = meal_plan['duration']['end_date']
    
    shopping_list_template = {
        "email": email,
        "plan_id": ObjectId(plan_id),
        "duration": {"start_date": start_date, "end_date": end_date},
        "createDate": str(datetime.today().date()),
        "ingredient": selected_ingredients
    }

    # Check if the shopping list for the given plan_id already exists
    existing_shopping_list = current_app.shopping_lists_collection.find_one({"plan_id": ObjectId(plan_id), "email": email})

    if existing_shopping_list:
        # Update the existing shopping list
        current_app.shopping_lists_collection.update_one(
            {"_id": existing_shopping_list["_id"]},
            {"$set": {"createDate": str(datetime.today().date()), "ingredient": selected_ingredients}}
        )
        return jsonify({"success": True, "message": "Shopping list updated"}), 200
    else:
        # Insert a new shopping list
        current_app.shopping_lists_collection.insert_one(shopping_list_template)
        return jsonify({"success": True, "message": "Shopping list created"}), 200
    
@recipes_bp.route('/shopping_list')
def shopping_list():
    if 'email' not in session:
        return redirect(url_for('auth.login'))  # Redirect to login if user is not authenticated
    return render_template('shopping_list.html')

@recipes_bp.route('/get_shopping_lists')
def get_shopping_lists():
    email = session['email']

    shopping_lists = list(current_app.shopping_lists_collection.find({"email": email}))
    logging.debug(f"Found {len(shopping_lists)} shopping lists")

    response = []
    for plan in shopping_lists:
        try:
            list_item = {
                "plan_id": str(plan["_id"]),
                "name": f"{plan['duration']['start_date']} to {plan['duration']['end_date']}"
            }
            response.append(list_item)
        except KeyError as e:
            logging.error(f"KeyError in plan: {e}")
            logging.debug(f"Plan data: {plan}")

    logging.debug(f"Returning {len(response)} shopping lists")
    return jsonify({"shopping_lists": response})

@recipes_bp.route('/get_ingredients/<plan_id>', methods=['GET'])
def get_ingredients(plan_id):
    print(f"Received request for ingredients with plan_id: {plan_id}")
    
    try:
        plan_object_id = ObjectId(plan_id)
    except Exception as e:
        print(f"Error converting plan_id to ObjectId: {e}")
        return jsonify({"error": "Invalid plan_id"}), 400

    # Change the query to search for _id instead of plan_id
    query = {"_id": plan_object_id, "email": session['email']}
    print(f"Query: {query}")
    print(f"Session email: {session['email']}")

    ingredients = current_app.shopping_lists_collection.find_one(query)
    
    #print(f"Fetched ingredients: {ingredients}")

    if ingredients and 'ingredient' in ingredients:
        # Your existing code for processing ingredients
        simplified_ingredients = simplify_ingredients(ingredients['ingredient'])  # No need for simplify_ingredients function
        
        # Group ingredients by aisle
        ingredients_by_aisle = {}
        for ing in simplified_ingredients:
            aisle = ing.get('aisle', 'Unspecified')
            if aisle not in ingredients_by_aisle:
                ingredients_by_aisle[aisle] = []
            ingredients_by_aisle[aisle].append({
                "name": ing["name"],
                "amount": ing["amount"],
                "unit": ing["unit"]
            })
        
        response = [
            {"aisle": aisle, "ingredients": ings}
            for aisle, ings in ingredients_by_aisle.items()
        ]
        
        #print(f"Final response: {response}")
        return jsonify({"ingredients": response})
    else:
        print("No ingredients found or 'ingredient' key missing")
        return jsonify({"error": "No ingredients found for this plan"}), 404
    
@recipes_bp.route('/delete_shopping_list/<_id>', methods=['DELETE'])
def delete_shopping_list(_id):
    print(f"Received request to delete shopping list with plan_id: {_id}")  # Debug statement
    
    # Convert plan_id to ObjectId
    try:
        plan_object_id = ObjectId(_id)
    except Exception as e:
        return jsonify({"error": "Invalid _id"}), 400
    
    # Delete shopping list from MongoDB
    result = current_app.shopping_lists_collection.delete_one({"_id": plan_object_id, "email": session['email']})
    
    if result.deleted_count == 1:
        return '', 204
    else:
        return jsonify({"error": "Shopping list not found"}), 404

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@recipes_bp.route('/upload', methods=['GET', 'POST'])
def upload_file():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    user = get_user_by_email(email)

    recipe_img_url = request.args.get('recipe_img_url')

    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        if file and allowed_file(file.filename):
            user_id = str(user['_id'])  # Assuming MongoDB's ObjectId, convert to string
            file_extension = os.path.splitext(file.filename)[1]
            filename = secure_filename(f"meal_{user_id}{file_extension}")
            try:
                # Get S3 client from current_app
                s3 = boto3.client(
                    "s3",
                    region_name=current_app.config["S3_REGION"],
                    aws_access_key_id=current_app.config["S3_KEY"],
                    aws_secret_access_key=current_app.config["S3_SECRET"]
                )
                logger.debug("S3 client created successfully")

                # Upload the new file to S3
                s3.upload_fileobj(
                    file,
                    current_app.config["S3_BUCKET"],
                    filename
                )
                file_url = f"{current_app.config['S3_LOCATION']}{filename}"
                logger.debug(f"File URL: {file_url}")

                # Assuming compare_images function is updated to handle URLs
                score = compare_images(file_url, recipe_img_url)
                score = math.ceil(score * 100)

                today_date_str = datetime.today().strftime('%Y-%m-%d')
                meal_plans_collection = current_app.meal_plans_collection
                meal_plans_collection.update_one(
                    {
                        "email": email,
                        "meals": {
                            "$elemMatch": {
                                'Date': today_date_str,
                                "Recipe.ImageURL": recipe_img_url
                            }
                        }
                    },
                    {
                        "$set": {
                            "meals.$.cook_status": True,
                            "meals.$.similarity_score": score
                        }
                    }
                )


                # Delete the uploaded file from S3 after scoring
                s3.delete_object(Bucket=current_app.config["S3_BUCKET"], Key=filename)
                logger.debug(f"Deleted uploaded image: {filename}")

                return jsonify({'score': score})
            except Exception as e:
                logger.error(f"Error uploading file to S3: {str(e)}")
                return jsonify({'error': str(e)}), 500
    return render_template('upload.html', recipe_img_url=recipe_img_url)

@recipes_bp.route('/add_recipe_from_favorite/<int:recipe_id>', methods=['GET', 'POST'])
def add_recipe_from_favorite(recipe_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']

    # If recipe_id is not in the URL, check if it's in the query parameters
    if recipe_id is None:
        recipe_id = request.args.get('recipe_id')

    if not recipe_id:
        flash('Recipe ID is required.')
        return redirect(url_for('recipes.favorites'))

    # Retrieve existing date ranges from the database for the logged-in user
    existing_plans = current_app.meal_plans_collection.find({"email": email}, {"duration": 1, "_id": 0})
    disabled_dates = set()

    for plan in existing_plans:
        start = datetime.strptime(plan["duration"]["start_date"], "%Y-%m-%d")
        end = datetime.strptime(plan["duration"]["end_date"], "%Y-%m-%d")
        current_date = start
        while current_date <= end:
            disabled_dates.add(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

    # Convert the set to a sorted list
    disabled_dates = sorted(disabled_dates) if disabled_dates else []
    print("Disabled Dates:", disabled_dates)  # Debugging

    api_key = current_app.config['RECIPE_API_KEY']
    recipe = get_one_recipe_information(api_key, recipe_id)
    if not recipe:
        print(f"Recipe not found with recipe_id: {recipe_id}")
        flash('Recipe not found.')
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id))

    # Render the template with disabled dates and recipe
    return render_template('create_newplan_withrecipe.html', disabled_dates=disabled_dates, recipe=recipe)

@recipes_bp.route('/create_mealplan_with_recipe/<int:recipe_id>', methods=['POST'])
def create_mealplan_with_recipe(recipe_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']
    user = current_app.users_collection.find_one({'email': email})

    if not user:
        return redirect(url_for('auth.login'))

    date = request.form.get('date')
    meal_type = request.form.get('meal_type')
    print(f"Received form data - Date: {date}, Meal Type: {meal_type}")  # Debugging

    api_key = current_app.config['RECIPE_API_KEY']
    # Ensure recipe_id is treated as an integer
    recipe = get_one_recipe_information(api_key, recipe_id)
    if not recipe:
        print(f"Recipe not found with recipe_id: {recipe_id}")
        flash('Recipe not found.')
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id))

    # Create a meal plan for a week starting from the selected date
    start_date = date
    end_date = date

    meal = {
        'Date': date,
        'MealID': str(uuid.uuid4()),
        'MealType': meal_type,
        'Recipe': {
            'ImageURL': recipe['image'],
            'RecipeID': recipe['id'],
            'Title': recipe['title']
        }
        
    }

    meal_plan = {
        "createDate": str(datetime.today().date()),
        "duration": {
            "start_date": start_date,
            "end_date": end_date
        },
        "email": email,
        "meals": [meal]  # Start with the current meal in a list
    }

    # Insert the new meal plan into the collection
    result = current_app.meal_plans_collection.insert_one(meal_plan)

    if result.inserted_id:
        flash('Meal plan created successfully!')
        return redirect(url_for('recipes.my_plan'))
    else:
        flash('Failed to create meal plan. Please try again.')
        return redirect(url_for('recipes.view_recipe', recipe_id=recipe_id))
