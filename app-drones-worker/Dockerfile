# Use an official Python runtime as a parent image
FROM python:3.12-slim

COPY app.py .
COPY database.py .
COPY requirements.txt .
COPY modelos modelos
COPY logos logos

RUN apt-get update && apt-get -y install gcc
RUN apt-get install ffmpeg libsm6 libxext6  -y

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
