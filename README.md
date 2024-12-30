# Background

This was an exercise in learning about NVIDIA's reference workflow for interactive avatars.
Specifically following something similar to Tokkio, but as a semi-monolithic toy service in plain and simple Python.
This heavy lifting is done through NVCF such as RIVA and other NIM-based APIs. More can be found on build.nvidia.com.
An API key will be needed with sufficient credits to run this.

# Demo

https://github.com/user-attachments/assets/53894f7c-0226-468e-84b8-a908217d21e0

# Installation and Running Instructions

Follow these steps to set up and run the project on your local machine:

## Prerequisites

This project was tested with **Python 3.11** but may work with other versions. 

## Installation

1. **Navigate to the Project Directory and Install Requirements**

   After downloading or cloning the project, navigate to its directory and install the dependencies. If you cloned the repository, ensure that you have retrieved all files through Git LFS:
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

# TODO

- Fix animation synchronization
- Fix crash after closing a single connection
- Test scaling to multiple simultaneous connections
- Coturn server and further testing in a cloud environment
- Connect to vision system (there go my credits, unless triggered sparesly and used only for RAG)
- Code cleanup, edge cases and general polish
