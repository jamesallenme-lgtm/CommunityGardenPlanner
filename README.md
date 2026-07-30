# Community Garden Planner

A small, mobile-friendly Streamlit demo for a food-bank community garden. It includes:

- Four 4 ft × 8 ft raised beds, each shown as 32 one-square-foot cells
- Editable crop assignments for every square
- Planting records with calculated germination and harvest dates
- A chronological task/calendar view
- Sample plantings and a simple crop timing library

The demo stores edits in the current Streamlit browser session. Restarting the app
or using **Reset sample data** restores the examples. For a multi-user production
version, the session data can later be replaced with Google Sheets, SQLite, or
another shared data source.

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Create and activate a virtual environment (recommended).
4. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Start the app:

   ```bash
   streamlit run app.py
   ```

Streamlit will display a local address, normally `http://localhost:8501`.

## Deploy free on Streamlit Community Cloud

1. Create a free GitHub account if you do not already have one.
2. Create a new GitHub repository and upload `app.py`, `requirements.txt`, and
   this `README.md` to the repository root.
3. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with
   GitHub.
4. Select **Create app**.
5. Choose the repository and branch containing these files.
6. Set the main file path to `app.py`.
7. Select **Deploy**.

The app does not require secrets or paid services. Community Cloud will install
the packages from `requirements.txt` automatically and provide a public URL you
can share with volunteers.

## Suggested next steps

- Store garden data in a shared Google Sheet or hosted database.
- Add volunteer-friendly forms for harvests, watering, and completed tasks.
- Put a QR code on each bed that opens a bed-specific page.
- Add seasons, crop rotation history, harvest weights, and printable reports.
