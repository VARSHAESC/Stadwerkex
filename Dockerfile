# -----------------------------
# Base image
# -----------------------------
FROM python:3.10-slim

# -----------------------------
# Workdir
# -----------------------------
WORKDIR /app

# -----------------------------
# OS packages
# -----------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
 && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Copy deps first + install
# -----------------------------
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------
# Pre-download embedding model (for offline runtime)
# (Use python -c instead of heredoc to avoid Windows parsing issues)
# -----------------------------
ENV HF_HOME=/app/hf_cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'); print('Embedding model cached.')"

# -----------------------------
# Copy app
# -----------------------------
COPY . /app

# -----------------------------
# Expose + start
# -----------------------------
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]