# Use an official Python runtime as a parent image
FROM python:3.12-slim

COPY app.py .
COPY requirements.txt .
COPY Modelos Modelos

RUN apt-get update && apt-get -y install gcc

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
