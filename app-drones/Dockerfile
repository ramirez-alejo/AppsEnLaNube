# Use an official Python runtime as a parent image
FROM python:3.12-slim

COPY app.py .
COPY database.py .
COPY requirements.txt .
COPY modelos modelos

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5001 available to the world outside this container
EXPOSE 5000