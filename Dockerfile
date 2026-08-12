FROM python:3.11-slim

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies (FFmpeg, git, build-essential, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    build-essential \
    curl \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces requires a user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy requirements and install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY --chown=user . $HOME/app

# Create required asset & output directories
RUN mkdir -p assets/images assets/audio assets/video assets/visuals assets/templates output data logs temp

# Expose Hugging Face Space port
EXPOSE 7860

# Launch app.py (starts Gradio Dashboard on 7860 + Telegram Bot in background)
CMD ["python", "app.py"]
