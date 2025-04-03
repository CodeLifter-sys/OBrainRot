# app.py

import os
from flask import Flask, request, jsonify
from celery.result import AsyncResult
import logging # Added for better logging

# Import the Celery app and the specific task function
from video_task import app as celery_app
from video_task import generate_video_task

# Configure basic logging
logging.basicConfig(level=logging.INFO)

# Initialize the Flask application
app = Flask(__name__)

# --- API Endpoint to Submit Task ---
@app.route('/submit_video_task', methods=['POST'])
def submit_task():
    """
    API endpoint to submit a video generation task.
    Expects JSON payload with 'reddit_url' (required) and optional 'llm' (boolean).
    Optionally accepts 'background_video_key' to select a predefined video.
    """
    if not request.is_json:
        logging.warning("Request received without JSON content-type")
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    reddit_url = data.get('reddit_url')
    use_llm = data.get('llm', False) # Default to False if not provided
    background_video_key = data.get('background_video_key') # Optional key

    if not reddit_url:
        logging.warning("Submit task request missing 'reddit_url'")
        return jsonify({"error": "'reddit_url' is required in JSON payload"}), 400

    if not isinstance(use_llm, bool):
         logging.warning(f"Submit task request received non-boolean 'llm': {use_llm}")
         return jsonify({"error": "'llm' must be a boolean (true/false)"}), 400

    # --- Handle Background Video Selection (Safer Approach) ---
    # Define allowed background videos mapped by keys
    allowed_backgrounds = {
        "subway": "assets/subway.mp4", # Default
        "beach": "assets/beach_background.mp4", # Example: Add more here
        "nature": "assets/nature_loop.mp4",   # Example
        # Add paths to your other background videos - MAKE SURE THESE FILES EXIST
    }

    # Determine the video path based on the key, defaulting to subway
    if background_video_key and background_video_key in allowed_backgrounds:
        video_path = allowed_backgrounds[background_video_key]
        logging.info(f"Using background video: '{background_video_key}' ({video_path})")
    elif background_video_key:
        logging.warning(f"Invalid background_video_key '{background_video_key}'. Using default.")
        video_path = allowed_backgrounds["subway"] # Use default if key is invalid
    else:
        video_path = allowed_backgrounds["subway"] # Use default if no key is provided
        logging.info(f"No background_video_key provided. Using default: {video_path}")

    # Check if the selected background video file exists before queueing
    if not os.path.exists(video_path):
         logging.error(f"Selected background video file not found at: {video_path}")
         # Return an error to the client if the essential background video is missing
         return jsonify({"error": f"Server configuration error: Background video '{video_path}' not found."}), 500

    # --- Dispatch the Celery Task ---
    # The task itself will handle creating its unique directory and managing file paths within it.
    try:
        logging.info(f"Dispatching video task for URL: {reddit_url}, LLM: {use_llm}, Background: {video_path}")
        # Pass the determined video_path to the task
        task = generate_video_task.delay(
            reddit_url=reddit_url,
            video_path=video_path,
            llm=use_llm
        )
        response_data = {
            "message": "Video generation task submitted successfully.",
            "task_id": task.id
        }
        logging.info(f"Task {task.id} submitted successfully.")
        # 202 Accepted: Request accepted, processing started in background
        return jsonify(response_data), 202

    except Exception as e:
        # Handle potential errors during task submission (e.g., broker connection issue)
        logging.error(f"Error submitting task to Celery: {e}", exc_info=True) # Log traceback
        return jsonify({"error": "Failed to submit task to the queue."}), 500


# --- API Endpoint to Check Task Status ---
@app.route('/task_status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """
    API endpoint to check the status and result of a Celery task.
    """
    logging.info(f"Checking status for task_id: {task_id}")
    task_result = AsyncResult(task_id, app=celery_app)

    response_data = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "error_info": None
    }

    if task_result.successful():
        response_data["result"] = task_result.get()
        logging.info(f"Task {task_id} status: {task_result.status}, Result: {response_data['result']}")
    elif task_result.failed():
        try:
            # task_result.info often holds the exception instance or traceback string
            error_info = str(task_result.info) if task_result.info else "No error details available."
            response_data["error_info"] = error_info
            logging.warning(f"Task {task_id} status: {task_result.status}, Error: {error_info}")
        except Exception as e:
             response_data["error_info"] = f"Could not retrieve error details: {e}"
             logging.error(f"Error retrieving failure info for task {task_id}: {e}", exc_info=True)
    else:
        # Other statuses include PENDING, STARTED, RETRY
        logging.info(f"Task {task_id} status: {task_result.status}")


    return jsonify(response_data), 200


# --- Root Endpoint (Optional) ---
@app.route('/')
def index():
    return "Welcome to the Video Generation API!"

# --- Run the Flask App ---
if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible on your network
    # Use debug=True only for development, set to False in production
    # Consider using a production-ready WSGI server like Gunicorn or Waitress
    logging.info("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=False) # Set debug=False for production/stable testing