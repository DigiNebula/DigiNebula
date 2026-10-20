# 🛡️ Campus Safeguard

### A DigiNebula Project

Campus Safeguard is a Python-based web application built using Streamlit and Google's Gemini API. It provides an interactive interface for users to submit requests and receive AI-generated responses.

The project is developed under **DigiNebula**, with a focus on building useful and accessible technology solutions.

## ✨ Features

- **AI-Powered Responses:** Uses the Gemini API to generate responses to user requests.
- **Interactive Interface:** Built with Streamlit for a simple web-based experience.
- **Credit System:** Includes a credit-based usage system.
- **Response Processing:** Processes requests and displays generated results.
- **Web Deployment:** Can be deployed using Streamlit Community Cloud.

## 🛠️ Technologies Used

- Python
- Streamlit
- Google Gemini API
- Requests

## 📂 Project Structure

```text
DigiNebula/
├── safeguard_bot_updated.py
├── requirements.txt
└── README.md
```

## ⚙️ Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR-USERNAME/DigiNebula.git
```

### 2. Open the Project Directory

```bash
cd DigiNebula
```

### 3. Switch to the Project Branch

```bash
git checkout campus-safegaurd
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

Your `requirements.txt` should include:

```text
streamlit
requests
```

### 5. Configure the Gemini API Key

The application requires a Gemini API key.

For local development, create `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "YOUR_API_KEY"
```

Replace `YOUR_API_KEY` with your own API key.

**Important:** Never upload your actual API key or the `secrets.toml` file to GitHub.

### 6. Run the Application

```bash
python -m streamlit run safeguard_bot_updated.py
```

Streamlit will provide a local URL where you can open the application in your browser.

## ☁️ Deployment

To deploy Campus Safeguard using Streamlit Community Cloud:

1. Sign in to Streamlit Community Cloud.
2. Connect your GitHub account.
3. Select the `DigiNebula` repository.
4. Choose the `campus-safegaurd` branch.
5. Set the main file path to `safeguard_bot_updated.py`.
6. Add `GEMINI_API_KEY` in the app's Secrets settings.
7. Deploy the application.

## 🔐 Security

- Keep API keys and credentials private.
- Never commit secret configuration files.
- Avoid storing sensitive user information in publicly accessible files.
- Review data storage and payment-related functionality before using the app in a real environment.

## 🏢 Developed By

**DigiNebula**

*Ideas Beyond Limits. Technology Without Boundaries.*

---

*Campus Safeguard is an evolving project. Features may change as development continues.*
