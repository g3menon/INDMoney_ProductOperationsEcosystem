FROM python:3.11-slim

# Install Chromium system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libglib2.0-0 libnspr4 libnss3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend requirements live under backend/
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium

# Copy backend package (FastAPI app package is `backend/app`)
COPY backend/ ./backend/
WORKDIR /app/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]