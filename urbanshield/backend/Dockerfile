FROM python:3.11-slim

WORKDIR /app

# Copy backend requirements from the repository-root build context.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and runtime data.
COPY backend ./backend
COPY db ./db
COPY ml ./ml
COPY ai_assistant ./ai_assistant
COPY frontend ./frontend
COPY .env.example ./.env

# Create logs directory
RUN mkdir -p logs

# Run FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
