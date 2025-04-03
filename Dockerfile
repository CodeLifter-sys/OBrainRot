# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Set environment variables early so they’re available in later steps
ENV COQUI_TOS_AGREED=1 \
    XDG_DATA_HOME="/root/.local/share" \
    TORCH_HOME="/root/.cache/torch"

# Install system dependencies. Using --no-install-recommends minimizes extra packages.
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential ffmpeg vim && \
    rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy only the requirements file first to leverage caching of dependency installation
COPY requirements.txt .

# Install Python dependencies; this layer only re-runs if requirements.txt changes
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories and download models in one layer.
# This prevents re-downloading models unless something in the earlier layers changes.
# RUN mkdir -p /root/.local/share/tts /root/.cache/torch/hub/checkpoints && \
#     # echo "y" | tts --download-model tts_models/multilingual/multi-dataset/xtts_v2 && \
#     curl -L -o /root/.cache/torch/hub/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth \
#          "https://download.pytorch.org/torchaudio/models/wav2vec2_fairseq_base_ls960_asr_ls960.pth"

# Finally, copy the rest of the application code.
# This ensures that changes in your code don’t trigger re-installation of dependencies or re-downloading of models.
COPY . .

# Start both Celery and the main app
# CMD bash -c "celery -A video_tasks.app worker --loglevel=INFO -P solo & python3 app.py"
