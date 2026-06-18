# Start from an official Python base image
FROM python:3.13-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first (for faster rebuilds)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app
COPY . .

# Tell Docker the app listens on port 8000
EXPOSE 8000

# The command that runs when the container starts
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]