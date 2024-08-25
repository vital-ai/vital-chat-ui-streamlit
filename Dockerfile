FROM python:3.11-slim

# Set environment variables to configure Streamlit
ENV STREAMLIT_SERVER_FILE_WATCHER_TYPE="none"
ENV STREAMLIT_SERVER_RUN_ON_SAVE="false"
ENV STREAMLIT_SERVER_HEADLESS="true"
ENV STREAMLIT_CLIENT_TOOLBAR_MODE="minimal"
ENV STREAMLIT_CLIENT_SHOW_SIDEBAR_NAVIGATION="false"
ENV STREAMLIT_GLOBAL_SHOW_DEPLOY_BUTTON="false"
ENV STREAMLIT_SERVER_PORT="8181"
ENV STREAMLIT_SERVER_ADDRESS="0.0.0.0"
ENV STREAMLIT_EMAIL_ADDRESS=""
ENV STREAMLIT_DISABLE_EMAIL_COLLECTION="true"
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"
ENV STREAMLIT_SERVER_ENABLE_CORS="false"
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION="false"

RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    && apt-get clean \

ENV CXXFLAGS="-std=c++11"

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt ./

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port Streamlit runs on
EXPOSE 8181

# Command to run the Streamlit app
CMD ["streamlit", "run", "app.py"]