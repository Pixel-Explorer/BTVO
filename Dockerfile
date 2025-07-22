# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY . .

# Make port 8080 available to the world outside this container
# Google Cloud Run expects the server to listen on the port defined by the PORT env var, which defaults to 8080.
ENV PORT 8080

# Define the command to run the app using gunicorn (a production-grade server)
# This is more robust than `python main.py`
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "0", "main:app", "--bind", "0.0.0.0:8080"]