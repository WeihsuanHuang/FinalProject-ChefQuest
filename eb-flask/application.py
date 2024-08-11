from flask import Flask, render_template
from auth.routes import auth_bp
from recipes.routes import recipes_bp
import os
from dotenv import load_dotenv
import boto3

load_dotenv()

# Flask app setup
application = Flask(__name__)
application.secret_key = os.urandom(24).hex()

# image upload
application.config['S3_BUCKET'] = os.getenv('S3_BUCKET')
application.config['S3_KEY'] = os.getenv('AWS_ACCESS_KEY_ID')
application.config['S3_SECRET'] = os.getenv('AWS_SECRET_ACCESS_KEY')
application.config['S3_REGION'] = os.getenv('AWS_REGION')
application.config['S3_LOCATION'] = f"http://{application.config['S3_BUCKET']}.s3.amazonaws.com/"

# Database and API configuration
application.config['MONGO_URI'] = os.getenv('MONGO_URI')
application.config['RECIPE_API_KEY'] = os.getenv('RECIPE_API_KEY')

# Register Blueprints
application.register_blueprint(auth_bp, url_prefix='/auth')
application.register_blueprint(recipes_bp)

s3 = boto3.client(
    "s3",    
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)

# Home Route
@application.route('/')
def index():
    application.logger.info("Index route accessed")
    try:
        application.logger.debug("Attempting to render index.html")
        return render_template('index.html')
    except Exception as e:
        application.logger.error(f"Error in index route: {str(e)}")
        return f"An error occurred: {str(e)}", 500

# Add a health check route
@application.route('/health')
def health_check():
    return "OK", 200


if __name__ == '__main__':
    application.run(debug=True)