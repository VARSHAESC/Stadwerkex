# Deployment Guide: STADTWERKE WÜLFRATH Demo

To get a public link for your demo, the easiest and most professional method is using **Streamlit Cloud**. Follow these steps:

## 1. Prepare your GitHub Repository
1.  **Create a private repo** on GitHub (e.g., `energybot-demo`).
2.  **Push your code** to this repo. Make sure your `.gitignore` includes any folders you don't want to share (like `cache/` or `.env`).
3.  **Required files**: Ensure these three files are in your root folder:
    - `app.py` (Main entry)
    - `requirements.txt` (List of Python libraries)
    - `packages.txt` (If you need system-level libraries, though usually not needed for this app)

## 2. Generate requirements.txt
Run this command in your terminal to create the dependency list that Streamlit Cloud needs:
```powershell
pip freeze > requirements.txt
```

## 3. Connect to Streamlit Cloud
1.  Go to [share.streamlit.io](https://share.streamlit.io/).
2.  Log in with your **GitHub account**.
3.  Click **"New app"**.
4.  Select your repository (`energybot-demo`), the branch (`main`), and the main file (`app.py`).

## 4. Set up your Secrets (IMPORTANT)
Your app depends on the Groq API key and passwords. You must NOT include these in your code.
1.  In the Streamlit deployment settings, find the **"Secrets"** section.
2.  Paste your environment variables there exactly as they appear in your `.env` file, but in TOML format:
    ```toml
    GROQ_API_KEY = "your-key-here"
    GROQ_MODEL = "llama-3.3-70b-versatile"
    APP_USERNAME = "admin"
    APP_PASSWORD = "your-password"
    ```

## 5. Get your Link
1.  Click **"Deploy!"**.
2.  Streamlit will install the dependencies and launch your app.
3.  Once finished, you will have a public URL like: `https://stadtwerke-wuelfrath.streamlit.app`

---

### ⚠️ Pro-Tip for the Demo
Since you are using an Excel file as your database, Streamlit Cloud will read the Excel file you pushed to GitHub.
If you use the **"Update"** feature in the cloud, it will update the Excel file in the app's *temporary memory*, but it **won't** save back to your GitHub repo permanently. For a long-term database, you would eventually move to a SQL database or Google Sheets, but for a demo, the current Excel setup works perfectly!
