FROM python:3.11-slim

# Install system dependencies for PaddleOCR/OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set up environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

WORKDIR /app

# Copy backend files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -e '.[ocr]'

# Pre-download PaddleOCR models at build time
RUN python -c "import os; os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE', 'huggingface'); from paddleocr import PPStructureV3; PPStructureV3()" || echo "Failed to pre-download models, will download on first run"

# Create a non-root user (UID 1000) for Hugging Face Spaces
RUN useradd -m -u 1000 user

# Copy the downloaded models to the new user's home directory and set permissions
RUN if [ -d "/root/.paddlex" ]; then \
        cp -r /root/.paddlex /home/user/.paddlex && \
        chown -R user:user /home/user/.paddlex; \
    fi

# Set permissions for the app directory
RUN chown -R user:user /app

# Switch to the non-root user
USER user

# Expose the default port for HF Spaces
EXPOSE 7860

# Run the application
CMD ["uvicorn", "documouse.main:app", "--host", "0.0.0.0", "--port", "7860"]
