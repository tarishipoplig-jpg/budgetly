Budgetly — Personal Budget Tracker (Flask + SQLite + Chart.js)

Quick start:

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Run the app:

```bash
python "app.py"
```

3. Open http://127.0.0.1:5000 in your browser.

Notes:
- Users can sign up and log in with an email and password. Passwords are stored as secure hashes in `budget.db`.
- Chart.js is loaded from CDN in the templates.
- Update `SECRET_KEY` in `app.py` before deploying.
