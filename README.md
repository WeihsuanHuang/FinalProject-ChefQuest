# ChefQuest

## Overview
ChefQuest, a cross-device interactive web application, aims to simplify meal preparation. It offers features such as a random meal plan generator for selected dates and meal types, as well as an auto-generating shopping list for necessary ingredients, thus reducing the burden of meal preparation. By making cooking more accessible, ChefQuest encourages university students to cook at home, potentially fostering healthier eating habits over time. For the record, ChefQuest is not an application that forces university students to cook every meal in a week by themselves. It is more of a customized planning tool that allows students to base their cooking on their schedules and arrange dates for home cooking. 

## Installation
Follow these steps to set up the project on your local machine.

### Prerequisites
- **Python 3.9+**: [Download Python](https://www.python.org/downloads/)
- **MongoDB**: [Install MongoDB](https://docs.mongodb.com/manual/installation/)
- **AWS CLI**: [Install AWS CLI](https://aws.amazon.com/cli/)
- **Spoonacular API Key**: [Get Spoonacular API Key](https://spoonacular.com/food-api)
- **AWS Elastic Beanstalk CLI**: [Install EB CLI](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3-install.html)


### Setup
1. **Download the ZIP file**
   - Download the ZIP file of the project and extract it to your desired location.


2. **Navigate to the project directory**
   - Open your terminal or command prompt and navigate to the project directory:
     ```sh
     cd path/to/project_directory
     ```

3. **Set up a virtual environment**
   - If your project uses Python, set up a virtual environment:
     ```sh
     python3 -m venv venv
     source venv/bin/activate  # On Windows use `venv\Scripts\activate`
     ```
4. **Install dependencies**
   - Install the necessary dependencies for your Flask project:
     ```sh
     pip install -r requirements.txt

5. **Set up environment variables**
   - Create a `.env` file in the project root and add the required variables:
   
   - Open the `.env` file in a text editor and add your secret keys and API keys:
       ```plaintext
       RECIPE_API_KEY=your_spoonacular_api_key
       MONGODB_URI=your_mongodb_uri
       AWS_ACCESS_KEY_ID=your_aws_access_key_id
       AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
       S3_BUCKET=your_s3_bucket_name
       AWS_REGION=your_s3_bucket_region
       ```
6. **Set up MongoDB**
   - Ensure MongoDB is installed and running on your local machine or provide the URI for a remote MongoDB instance. You can use a cloud service like MongoDB Atlas if preferred.

7. **Install and configure the AWS CLI**
    ```sh
    aws configure
    ```
    - Follow the prompts to enter your AWS Access Key ID, AWS Secret Access Key, and the default region.

8. **Running the Application**
    - python application.run

9. **Deployment to AWS Elastic Beanstalk**
   - Initialize your EB environment
   ```sh
   eb init
   ```
   - Create an Elastic Beanstalk environment
   ```sh
   eb create your-environment-name
   ```
   - Deploy your application
   ```sh
   eb deploy
   ```

### LICENSE
The LICENSE file should contain the full text of the license under which you are distributing your project.
