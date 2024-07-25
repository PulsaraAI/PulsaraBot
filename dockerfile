FROM python:3.8-slim

# Set working directory
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the app
CMD ["gunicorn", "-w", "4", "-k", "gevent", "-b", "0.0.0.0:8000", "app:app"]
