# GitHub Push Guide: STADTWERKE WÜLFRATH

Follow these steps to securely upload your project to GitHub for deployment.

## Option A: Install Git (Recommended)
You have `winget` installed on your Windows system. Run this command in your terminal to install Git automatically:
```powershell
winget install --id Git.Git -e --source winget
```
*After installation, restart your terminal.*

## Option B: Manual Upload (Easiest for Demo)
If you don't want to install Git, you can upload files manually:
1.  **Create the Repository** on GitHub (Set to **Private**).
2.  Click the link **"uploading an existing file"** on the setup page.
3.  **Selective Drag & Drop**: Drag all files from your project folder into the browser, **EXCEPT**:
    - Do **NOT** upload `.env` (Security Risk!)
    - Do **NOT** upload `__pycache__` or `cache/`
    - Do **NOT** upload `chroma_db/`
4.  Click **"Commit changes"**.

## Option C: Initialize Git Locally (If Git is installed)
1.  Log in to [GitHub](https://github.com/).
2.  Click the **"+"** icon (top-right) and select **"New repository"**.
3.  Name it (e.g., `stadtwerke-demo`).
4.  **Crucial**: Set it to **Private** if you want to protect your data.
5.  Click **"Create repository"**. Do NOT initialize with README or license.

## 2. Initialize Git Locally
Open your terminal (PowerShell or Command Prompt) in your project folder and run:
```powershell
# Initialize git
git init

# Add all files (the .gitignore will automatically skip sensitive files)
git add .

# Create first commit
git commit -m "Initial commit for Stadtwerke Wuelfrath platform"
```

## 3. Link and Push to GitHub
Copy the commands from the GitHub "Quick Setup" page (the one with your repo URL):
```powershell
# Replace the URL with your actual repo URL
git remote add origin https://github.com/YOUR_USERNAME/stadtwerke-demo.git

# Set branch name
git branch -M main

# Push the code
git push -u origin main
```

## 4. Verification Check
Refresh your GitHub page. You should see your files there.
- **Double Check**: Ensure the `.env` file is NOT on GitHub. 
- If you see `.env` on GitHub, delete the repo immediately and start over after checking your `.gitignore`.
