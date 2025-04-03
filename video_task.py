# video_task.py

import os
import shutil # For potential cleanup later if needed
import traceback # For logging exceptions
from celery import Celery
from dotenv import load_dotenv
from dict import *
import logging # Added for better logging

# Import your project modules - ensure they are importable by the worker
from scraping import *
from audio import *
from force_alignment import *
# from dict import * # Check if needed and adjust import
from video_generator import *
from search import *

# Configure basic logging for the task module
logging.basicConfig(level=logging.INFO)

# --- Celery Configuration ---
load_dotenv() # Load environment variables early

BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

app = Celery('video_task',
             broker=BROKER_URL,
             backend=RESULT_BACKEND)

# Optional Celery configuration
# app.conf.update(...) # Add any specific Celery settings if needed

# --- Your Core Logic as a Celery Task ---
@app.task(bind=True, name='tasks.generate_video')
def generate_video_task(self, reddit_url, video_path='assets/subway.mp4', llm=False):
    """
    Celery task to generate a video. Creates a unique directory for each task's files.
    """
    task_id = self.request.id
    logging.info(f"[Task {task_id}] Received: URL={reddit_url}, Background={video_path}, LLM={llm}")

    # --- Create Unique Task Directory ---
    base_tasks_dir = 'task_outputs' # Main directory to hold all task outputs
    task_dir = os.path.join(base_tasks_dir, task_id)
    try:
        os.makedirs(task_dir, exist_ok=True)
        logging.info(f"[Task {task_id}] Created task directory: {task_dir}")
    except OSError as e:
        logging.error(f"[Task {task_id}] Failed to create task directory {task_dir}: {e}")
        # Raise an exception to indicate failure early
        raise OSError(f"Failed to create task directory: {e}") from e

    # --- Define File Paths WITHIN the Task Directory ---
    # Use simple, consistent names within the unique directory
    scraped_url_txt = os.path.join(task_dir, 'scraped.txt')
    output_pre_txt = os.path.join(task_dir, 'processed_pre.txt')
    final_output_txt = os.path.join(task_dir, 'processed_final.txt')
    temp_audio_wav = os.path.join(task_dir, 'output.wav') # Initial audio output
    speech_final_wav = os.path.join(task_dir, 'output_converted.wav') # Final audio
    subtitle_path_ass = os.path.join(task_dir, 'subtitles.ass')
    output_filename = 'final_video.mp4' # Simple name for the final video
    output_path = os.path.join(task_dir, output_filename) # Full path to final video

    intermediate_files = [
        scraped_url_txt, output_pre_txt, final_output_txt,
        temp_audio_wav, speech_final_wav, subtitle_path_ass
    ]

    # --- Execute Video Generation Logic ---
    try:
        logging.info(f"[Task {task_id}] L1: SCRAPING START")
        if not llm:
            map_request = scrape(reddit_url)
        else:
            logging.info("[Task {task_id}] Using LLM for scraping.")
            reddit_scrape = scrape_llm(reddit_url)
            text = vader(reddit_scrape) # Assuming vader is imported
            api = os.getenv('GROQ_API_KEY')
            if not api:
                raise ValueError("GROQ_API_KEY not found in environment variables.")
            map_request= groq(text, api) # Assuming groq is imported
            logging.info(f"[Task {task_id}] LLM Map Request: {map_request}")

        save_map_to_txt(map_request, scraped_url_txt) # Save to task dir
        logging.info(f"[Task {task_id}] L1: SCRAPING END - Saved to {scraped_url_txt}")

        # ## AUDIO CONVERSION
        logging.info(f"[Task {task_id}] L2: AUDIO CONVERSION START")
        # Ensure your audio function accepts 'output_path' argument correctly
        audio(scraped_url_txt, speaker_wav="assets/default.mp3", file_path=temp_audio_wav)
        logging.info(f"[Task {task_id}] Initial audio saved to {temp_audio_wav}")
        # Ensure convert_audio uses the correct input/output paths
        convert_audio(temp_audio_wav, speech_final_wav)
        logging.info(f"[Task {task_id}] Converted audio saved to {speech_final_wav}")
        logging.info(f"[Task {task_id}] L2: AUDIO CONVERSION END")

        # IMPORTANT PRE PROCESSING STUFF
        logging.info(f"[Task {task_id}] Pre-processing text")
        process_text(scraped_url_txt, output_pre_txt)
        process_text_section2(output_pre_txt, final_output_txt)
        logging.info(f"[Task {task_id}] Text processing complete. Final text at {final_output_txt}")

        with open(final_output_txt, 'r') as file:
            text = file.read().strip()

        # A BUNCH OF HARDCORE FORCED ALIGNMENT FORMATTING
        logging.info(f"[Task {task_id}] L3: FORCE ALIGNMENT START")
        transcript = format_text(text)
        # Ensure these functions use the correct audio path (speech_final_wav)
        bundle, waveform, labels, emission1 = class_label_prob(speech_final_wav)
        trellis, emission, tokens = trellis_algo(labels, text, emission1)
        path = backtrack(trellis, emission, tokens)
        segments = merge_repeats(path, transcript)
        word_segments = merge_words(segments)
        timing_list = []
        for (i, word) in enumerate(word_segments):
            # Ensure display_segment uses the correct variables
             timing_list.append(display_segment(bundle, trellis, word_segments, waveform, i))

        logging.info(f"[Task {task_id}] L3: FORCE ALIGNMENT END")

        # FINAL VIDEO
        logging.info(f"[Task {task_id}] L4: VIDEO GENERATION START")
        # Ensure convert_timing_to_ass saves to subtitle_path_ass
        convert_timing_to_ass(timing_list, subtitle_path_ass)
        logging.info(f"[Task {task_id}] Subtitles saved to {subtitle_path_ass}")

        # Ensure add_subtitles_and_overlay_audio uses the correct paths:
        # input video (video_path), final audio (speech_final_wav),
        # subtitles (subtitle_path_ass), and FINAL output path (output_path)
        add_subtitles_and_overlay_audio(video_path, speech_final_wav, subtitle_path_ass, output_path)
        logging.info(f"[Task {task_id}] L4: VIDEO GENERATION END")

        logging.info(f"[Task {task_id}] SUCCESS! Final video saved at: {output_path}")

        # Return the path to the generated video upon success
        return output_path

    except Exception as e:
        logging.error(f"[Task {task_id}] Execution FAILED: {e}", exc_info=True)
        # Log the traceback for detailed debugging
        # traceback.print_exc() # Already logged by exc_info=True
        # Re-raise the exception so Celery marks the task as FAILED
        # and the error info is available via the result backend
        raise

    finally:
        # --- Optional Cleanup of Intermediate Files ---
        # This block executes whether the task succeeded or failed.
        # We only clean up if the task *didn't* fail, to preserve files for debugging.
        if task_result := self.AsyncResult(self.request.id): # Check if result exists
             if task_result.successful(): # Check if task was successful *before* finally block finished
                logging.info(f"[Task {task_id}] Cleaning up intermediate files...")
                files_cleaned = 0
                files_not_found = 0
                for file_path in intermediate_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            files_cleaned += 1
                        else:
                           files_not_found +=1
                    except OSError as err:
                        logging.warning(f"[Task {task_id}] Error cleaning up file {file_path}: {err}")
                logging.info(f"[Task {task_id}] Cleanup complete. Removed: {files_cleaned}, Not found: {files_not_found}.")
             else:
                 logging.warning(f"[Task {task_id}] Task did not succeed. Skipping cleanup of intermediate files in {task_dir} for debugging.")
        else:
             logging.warning(f"[Task {task_id}] Could not get task result in finally block. Skipping cleanup.")


# Note: Ensure all imported functions (scrape, audio, convert_audio, etc.)
# correctly handle the full file paths passed to them, especially for output arguments.