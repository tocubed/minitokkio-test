# Background

This was an exercise in learning about NVIDIA's reference workflow for interactive avatars.
Specifically following something similar to Tokkio, but as a semi-monolithic toy service in plain and simple Python.
This heavy lifting is done through NVCF such as RIVA and other NIM-based APIs. More can be found on build.nvidia.com.
An API key will be needed with sufficient credits to run this.

# Installation and Running Instructions

Follow these steps to set up and run the project on your local machine:

## Prerequisites

This project was tested with **Python 3.11** but may work with other versions. It assumes you have **pip** (included with Python) and **Git** (commonly available for developers).

## Installation

1. **Navigate to the Project Directory and Install Requirements**

   After downloading or cloning the project, navigate to its directory and install the dependencies:
   ```bash
   cd <project_directory>
   pip install -r requirements.txt
   ```

## Running the Project

1. **Set the Required Environment Variable**

   The project depends on the `NVAPI_KEY` environment variable for proper functioning. Ensure this variable is set before running the application. You can obtain an API key from [build.nvidia.com](https://build.nvidia.com):

   ```bash
   export NVAPI_KEY=<your_api_key>  # On Linux/MacOS
   set NVAPI_KEY=<your_api_key>    # On Windows
   ```

2. **Run the Main Script**

   Execute the `run.py` file to start the application:
   ```bash
   python run.py
   ```

3. **Access the Application**

   Once the application is running, open your browser and navigate to the URL displayed in the terminal (e.g., `http://127.0.0.1:5000`).