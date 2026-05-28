# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app.
COPY . /app

# Install dependencies. Runtime configuration should be provided through
# environment variables or an external .env file mounted by the user.
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8765
EXPOSE 8765

# Run the aiohttp WebSocket server
CMD ["python", "src/sia_server.py"]
