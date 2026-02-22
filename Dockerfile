FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create CSV directory (download_csv will populate salesdata.csv on startup)
RUN mkdir -p core/data/csv

# Run bot
CMD ["python", "bot.py"]
