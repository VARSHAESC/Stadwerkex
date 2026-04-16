# EnergyBot Installation & Setup Guide

Welcome to the **STADTWERKE X Infrastructure Platform**. This guide will help you set up and run the application on your system.

## 1. Prerequisites
- **Python 3.10+** OR **Docker Desktop** installed on your system.
- An **Internet Connection** (only for the first setup to download libraries).
- An **API Key** from your preferred AI provider (Groq, Azure OpenAI, or local Ollama).

## 2. Setting Up Your Credentials (GDPR Compliance)
Before starting, you must configure your data security settings.
1.  Locate the `.env` file in the main folder.
2.  **Right-click** the `.env` file and select **"Open with" > "Notepad"**.
3.  Fill in your details (replace `your_key_here` with your actual API key):
    ```env
    # --- AI Connection ---
    LLM_BASE_URL=https://api.groq.com/openai/v1
    LLM_API_KEY=your_key_here
    LLM_MODEL_NAME=llama-3.3-70b-versatile

    # --- App Access ---
    APP_USERNAME=admin
    APP_PASSWORD=choose_a_password
    ```
4.  **Save** the file (Ctrl+S) and close Notepad.

## 3. How to Start the App
Simply **double-click** the file named:
👉 `run_energybot.bat`

### What happens next?
- **Automatic Setup**: The script will automatically check if you have Docker. If not, it will automatically create a "Virtual Environment" and download all necessary libraries for you.
- **Launch**: Once ready, the app will open in your web browser at: `http://localhost:8501`

## 4. Troubleshooting
- **Port Conflict**: If port 8501 is already in use, you will see an error.
- **Missing Python/Docker**: Ensure at least one of these is installed and added to your system's PATH.
