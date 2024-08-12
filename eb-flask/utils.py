import requests
from flask import current_app
import os
from io import BytesIO
from PIL import Image
import imagehash

# Helper Functions
def standardize_unit(unit, unknown_units):
    unit = unit.lower().rstrip('s')
    unit_standardization = {
        "ounce": "oz", "pound": "lb", "gram": "g", "kilogram": "kg",
        "tablespoon": "tbsp", "teaspoon": "tsp", "fluid ounce": "fl oz",
        "pint": "pt", "quart": "qt", "gallon": "gal", "milliliter": "ml",
        "liter": "L", "package": "pkg", "piece": "pc", "dozen": "doz",
        "unit not specified": "unit"
    }

    standardized_unit = unit_standardization.get(unit)
    if standardized_unit is None:
        unknown_units.add(unit)
        return unit  # Return the unit as is if not found in the dictionary

    return standardized_unit

def simplify_ingredients(detailed_ingredients):
    combined_ingredients = {}
    unknown_units = set()

    for ingredient in detailed_ingredients:
        standardized_unit = standardize_unit(ingredient['unit'], unknown_units)
        key = (ingredient['aisle'], ingredient['name'], standardized_unit)

        if key in combined_ingredients:
            combined_ingredients[key]['amount'] += ingredient['amount']
        else:
            combined_ingredients[key] = ingredient.copy()
            combined_ingredients[key]['unit'] = standardized_unit

    return list(combined_ingredients.values())

def download_image_to_memory(img_url):
    response = requests.get(img_url)
    img = Image.open(BytesIO(response.content))
    return img

def compare_images(user_img_url, recipe_img_url):
    user_img = download_image_to_memory(user_img_url)
    recipe_img = download_image_to_memory(recipe_img_url)

    hash_user_img = imagehash.average_hash(user_img)
    hash_recipe_img = imagehash.average_hash(recipe_img)

    similarity = 1 - (hash_user_img - hash_recipe_img) / len(hash_user_img.hash) ** 2
    return similarity

# Spoonacular API Interaction Functions
def search_recipes(api_key, query):
    url = 'https://api.spoonacular.com/recipes/complexSearch'
    params = {
        'apiKey': api_key,
        'query': query,
        'number': 6,
        'sort': 'random',
        'maxServings': 1,
        'instructionsRequired': True,
        'addRecipeInformation': True,
        'fillIngredients': True,
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get('results', [])
    return []

def fetch_recipes(api_key, meal_type, intolerances=[], number=1):
    url = 'https://api.spoonacular.com/recipes/complexSearch'
    params = {
        'apiKey': api_key,
        'intolerances': ','.join(intolerances),
        'maxCalories': 700,
        'maxServings': 2,
        'maxReadyTime': 30,
        'number': number,
        'type': meal_type,
        'addRecipeInformation': 'true',
        'fillIngredients': 'false',
        'sort': 'random'
    }

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            recipes = response.json().get('results', [])
            return [
                {
                    'RecipeID': recipe['id'],
                    'Title': recipe['title'],
                    'ImageURL': recipe['image']
                }
                for recipe in recipes
            ]
    except Exception as e:
        print(f"Exception occurred: {e}")
    return []

def get_full_recipe_details(api_key, recipe_id):
    url_details = f'https://api.spoonacular.com/recipes/{recipe_id}/information'
    url_nutrition = f'https://api.spoonacular.com/recipes/{recipe_id}/nutritionWidget.json'
    params = {'apiKey': api_key, 'includeNutrition': True}

    try:
        response_details = requests.get(url_details, params=params)
        if response_details.status_code == 200:
            recipe_details = response_details.json()
        else:
            print(f"Error: Unable to fetch recipe details. Status code: {response_details.status_code}")
            return None

        response_nutrition = requests.get(url_nutrition, params=params)
        if response_nutrition.status_code == 200:
            recipe_details['nutrition'] = response_nutrition.json()
        else:
            print(f"Error: Unable to fetch nutrition information. Status code: {response_nutrition.status_code}")
            return None

        return recipe_details
    except requests.exceptions.RequestException as e:
        print(f"Network-related exception occurred: {e}")
    except Exception as e:
        print(f"General exception occurred: {e}")
    return None

def get_recipes_information(api_key, recipe_ids):
    recipes_info = []

    for recipe_id in recipe_ids:
        url = f'https://api.spoonacular.com/recipes/{recipe_id}/information'
        params = {'apiKey': api_key}

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                recipes_info.append(response.json())
            else:
                print(f"Error: Unable to fetch recipe information for ID {recipe_id}. Status code: {response.status_code}")
        except Exception as e:
            print(f"Exception occurred while fetching recipe ID {recipe_id}: {e}")

    return recipes_info

def get_one_recipe_information(api_key, recipe_id):
    url = f'https://api.spoonacular.com/recipes/{recipe_id}/information'
    params = {'apiKey': api_key}

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error: Unable to fetch recipe information for ID {recipe_id}. Status code: {response.status_code}")
    except Exception as e:
        print(f"Exception occurred while fetching recipe ID {recipe_id}: {e}")
    return None