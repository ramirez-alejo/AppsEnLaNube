# Use an official Python runtime as a parent image
FROM python:3.12

RUN mkdir /src
WORKDIR /src
ADD requirements.txt /src/

RUN apt-get update && apt-get -y install gcc
RUN pip install --upgrade pip
# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5001 available to the world outside this container
EXPOSE 5000