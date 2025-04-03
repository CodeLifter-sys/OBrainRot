
# Reddit Video Generator API

## Overview

This project provides a web API built with Flask to generate videos based on content scraped from a Reddit URL. It uses Celery for background task processing to handle potentially long-running video generation jobs asynchronously, ensuring the API remains responsive. Each video generation task runs in its own unique temporary directory to manage intermediate files and the final output.

The core process involves:
1.  Receiving a Reddit URL (and optional parameters) via a REST API call.
2.  Scraping content from the specified Reddit thread.
3.  (Optionally) Processing scraped text using an LLM (via Groq API).
4.  Converting the text content to speech.
5.  Performing forced alignment to synchronize audio with text timings.
6.  Generating subtitles (.ass format).
7.  Combining a background video, the generated audio, and subtitles into a final video file.
8.  Providing an API endpoint to check the status and result of the generation task.

## Features

* **REST API:** Submit video generation jobs easily via HTTP POST requests.
* **Asynchronous Processing:** Uses Celery and a message broker (like Redis) to handle video generation in the background without blocking the API.
* **Task Status Tracking:** API endpoint to query the status (Pending, Started, Success, Failure) and result (output video path or error details) of submitted tasks.
* **Selectable Backgrounds:** Choose from predefined background videos using a key in the API request.
* **Optional LLM Processing:** Utilize an LLM for enhanced text processing (requires Groq API key).
* **Isolated Task Execution:** Each task creates and uses a unique directory (`task_outputs/<task_id>/`) for all its files, preventing conflicts.
* **Configurable:** Uses environment variables (`.env` file) for sensitive data like API keys and broker URLs.

## Architecture

1.  **Flask (`app.py`):** Provides the web API endpoints (`/submit_video_task`, `/task_status/<task_id>`). It receives user requests, validates them, and dispatches tasks to the Celery queue.
2.  **Celery (`video_task.py`):** Defines the background task (`generate_video_task`) that contains the core video generation logic. It also holds the Celery application instance configuration.
3.  **Celery Workers:** Separate processes that run (`celery -A video_task.app worker ...`) and listen to the message queue for tasks dispatched by Flask. They execute the `generate_video_task`.
4.  **Message Broker (e.g., Redis):** Acts as the communication channel between Flask (producer) and Celery Workers (consumers). Stores task requests until a worker picks them up. Also used as the Result Backend to store task status and results.
5.  **Core Logic Modules:** Various Python files (`scraping.py`, `audio.py`, `video_generator.py`, etc.) containing the specific functions for scraping, text-to-speech, alignment, and video processing, called by the Celery task.

```mermaid
graph LR
    Client -->|POST /submit_video_task| Flask_API[Flask App (app.py)];
    Flask_API -->|Task Request| Broker[(Message Broker - Redis)];
    Broker -->|Task| Celery_Worker[Celery Worker (video_task.py)];
    Celery_Worker -->|Task Status/Result| Broker;
    Flask_API -->|GET /task_status/id| Broker;
    Broker -->|Status/Result| Flask_API;
    Flask_API -->|Response (task_id / status)| Client;
    Celery_Worker -->|Calls| LogicModules[Core Logic (scraping, audio, etc.)];
    Celery_Worker -->|Writes Files| TaskOutputs[task_outputs/task_id/...];
```

## Prerequisites

* Python 3.8+
* `pip` (Python package installer)
* Git (for cloning the repository)
* **Message Broker:** Redis (recommended) or RabbitMQ installed and running.
* **(Optional) Groq API Key:** If using the LLM feature (`llm: true`).

## Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```

2.  **Create a Virtual Environment:** (Recommended)
    ```bash
    python -m venv venv
    # Activate it:
    # Windows
    venv\Scripts\activate
    # Linux/macOS
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Ensure `requirements.txt` includes Flask, Celery, redis (or pika for RabbitMQ), python-dotenv, and all dependencies required by your core logic modules like `scraping.py`, `audio.py`, etc.)*

4.  **Configure Environment Variables:**
    Create a file named `.env` in the project root directory. Add the following variables, adjusting values as needed:

    ```dotenv
    # .env

    # Celery Broker URL (Redis example)
    CELERY_BROKER_URL=redis://localhost:6379/0

    # Celery Result Backend URL (Redis example)
    CELERY_RESULT_BACKEND=redis://localhost:6379/0

    # Groq API Key (only required if using llm=True)
    GROQ_API_KEY=your_groq_api_key_here
    ```

5.  **Ensure Assets Exist:**
    Make sure the necessary asset files are present, especially the default background video and speaker WAV file referenced in `video_task.py` and `app.py`:
    * `assets/subway.mp4` (or your default)
    * `assets/default.mp3` (or your default speaker wav)
    * Any other background videos listed in `allowed_backgrounds` in `app.py`.

## Running the Application

You need to run three components, typically each in its own terminal window:

1.  **Start the Message Broker:**
    * **Redis (using Docker):** `docker run -d -p 6379:6379 redis`
    * **Redis (local install):** Ensure the Redis server service is running (`sudo systemctl start redis-server` or similar).

2.  **Start the Celery Worker:**
    Navigate to the project's root directory in your terminal (with the virtual environment activated) and run:
    ```bash
    celery -A video_task.app worker --loglevel=INFO -P solo
    ```
    * `-A video_task.app`: Points to the Celery app instance in `video_task.py`.
    * `--loglevel=INFO`: Sets the logging level.
    * `-P solo`: Use this execution pool on Windows if the default (`prefork`) causes issues. Remove on Linux/macOS unless needed. You can use `-c <number>` to set concurrency on non-Windows systems (e.g., `-c 2`).

3.  **Start the Flask Server:**
    Navigate to the project's root directory in another terminal (with the virtual environment activated) and run:
    ```bash
    python app.py
    ```
    The server will typically start on `http://0.0.0.0:5000`.

## API Endpoints

### 1. Submit Video Generation Task

* **URL:** `/submit_video_task`
* **Method:** `POST`
* **Request Body:** JSON
    ```json
    {
      "reddit_url": "string (required)",
      "llm": "boolean (optional, default: false)",
      "background_video_key": "string (optional, default: 'subway')"
    }
    ```
    * `reddit_url`: The full URL of the Reddit post/comment thread to process.
    * `llm`: Set to `true` to enable LLM processing (requires `GROQ_API_KEY`).
    * `background_video_key`: A key corresponding to an entry in the `allowed_backgrounds` dictionary in `app.py` (e.g., "subway", "beach"). If omitted or invalid, the default ("subway") is used.

* **Success Response (202 Accepted):**
    ```json
    {
      "message": "Video generation task submitted successfully.",
      "task_id": "string (unique ID for the submitted task)"
    }
    ```

* **Error Responses:**
    * `400 Bad Request`: Invalid JSON, missing `reddit_url`, or invalid `llm` type.
    * `500 Internal Server Error`: Failed to connect to the broker, background video asset missing on the server, or other server-side issues during task submission.

* **Example (`curl`):**
    ```bash
    curl -X POST http://127.0.0.1:5000/submit_video_task \
         -H "Content-Type: application/json" \
         -d '{
               "reddit_url": "https://www.reddit.com/r/some_subreddit/comments/abcdef/some_post_title/",
               "llm": false,
               "background_video_key": "subway"
             }'
    ```

### 2. Check Task Status

* **URL:** `/task_status/<task_id>`
* **Method:** `GET`
* **URL Parameters:**
    * `task_id`: The unique ID returned when the task was submitted.

* **Success Response (200 OK):**
    ```json
    {
      "task_id": "string",
      "status": "string (e.g., PENDING, STARTED, SUCCESS, FAILURE, RETRY)",
      "result": "string (path to output video if status is SUCCESS) / null",
      "error_info": "string (error details if status is FAILURE) / null"
    }
    ```

* **Example (`curl`):** (Replace `<task_id>` with an actual ID)
    ```bash
    curl http://127.0.0.1:5000/task_status/<task_id>
    ```

## Project Structure

```
.
├── assets/                 # Static assets (background videos, default audio)
│   ├── subway.mp4
│   ├── beach_background.mp4
│   └── default.mp3
├── task_outputs/           # Runtime directory for task-specific outputs (created automatically)
│   └── <task_id>/          # Unique directory per task
│       ├── scraped.txt
│       ├── output.wav
│       ├── subtitles.ass
│       └── final_video.mp4
│   └── <another_task_id>/
│       └── ...
├── venv/                   # Python virtual environment (if used)
├── app.py                  # Flask application: API endpoints
├── video_task.py          # Celery application definition and task logic
├── scraping.py             # Module for Reddit scraping logic
├── audio.py                # Module for text-to-speech and audio processing
├── force_alignment.py      # Module for audio-text alignment logic
├── video_generator.py      # Module for final video compositing (audio + video + subtitles)
├── search.py               # Module potentially used by LLM logic (based on imports)
# Add other custom modules like dict.py if applicable
├── requirements.txt        # Python package dependencies
├── .env                    # Environment variables (API keys, Broker URL) - !! DO NOT COMMIT !!
└── README.md               # This documentation file
```

## Configuration

Configuration is primarily handled through environment variables defined in the `.env` file. Key variables include:

* `CELERY_BROKER_URL`: Connection URL for the message broker.
* `CELERY_RESULT_BACKEND`: Connection URL for the result backend (often same as broker).
* `GROQ_API_KEY`: Required only if using the `llm: true` feature.

## Key Dependencies

* **Flask:** Web framework for the API.
* **Celery:** Distributed task queue for background processing.
* **redis / pika:** Python client for the message broker (Redis or RabbitMQ).
* **python-dotenv:** For loading environment variables from the `.env` file.
* *(Add other major libraries used by your core logic modules)*

---