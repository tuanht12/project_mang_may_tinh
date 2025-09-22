# Project Setup Instructions

## Requirements

- **Python 3.9** is required for this project.

## Setup Guide

1. **Install Python 3.9**  
    Make sure Python 3.9 is installed on your system. You can check your version with:
    ```bash
    python3 --version
    ```

2. **Create a Virtual Environment**  
    Create a virtual environment named `mmt_venv`:
    ```bash
    python3.9 -m venv mmt_venv
    ```

3. **Activate the Virtual Environment**

    - On **macOS/Linux**:
      ```bash
      source mmt_venv/bin/activate
      ```
    - On **Windows**:
      ```cmd
      mmt_venv\Scripts\activate
      ```

4. **Install Dependencies**  
    With the virtual environment activated, install all required packages:
    ```bash
    pip install -r requirements.txt
    ```

5. **Run a Test Script**  
    To verify your setup, create a file named `hello_world.py` run the script:
    ```bash
    python hello_world.py
    ```
    If you see `Hello, world!` and `All modules imported successfully.` printed, your environment is set up correctly.

You're now ready to start working on the project!


6. **Code Formatting**  
    Before committing your code, run the following command to automatically format your code using [Black](https://black.readthedocs.io/):
    ```bash
    black .
    ```
    This ensures consistent code style throughout the project.
