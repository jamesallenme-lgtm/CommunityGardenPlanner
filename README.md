# Community Garden Planner

A public, read-only Streamlit dashboard backed by a private Google Sheet.

The app includes:

- Spreadsheet-defined raised beds shown as one-square-foot grids
- Responsive garden maps: full-size beds on desktop and a compact vertical site plan with expandable bed details on mobile
- Planting records with calculated germination and harvest dates
- A chronological task list and bed-filtered Gantt timeline
- Color-coded germination, growth, and 14-day harvest periods
- A crop timing library
- Automatic refresh from Google Sheets every 60 seconds

Garden coordinators edit the private Google Sheet. Public visitors can view the
dashboard but cannot change shared data from Streamlit.

## Plantings-first migration

The app name shown on the overview page, in the sidebar, and in the browser tab
comes from the Google Sheets document name. Rename the spreadsheet in Google
Drive to change the app title; no code or worksheet change is required. When the
app is using sample data, it falls back to `Community Garden Planner`.

The app supports both spreadsheet structures during migration:

- **Plantings-first:** `Beds`, `Plantings`, `Plant Library`, `Grid Reference`, and `Instructions`
- **Legacy:** `Bed Assignments`, `Plantings`, and `Crop Library`

When `Plant Library` exists, the app automatically switches to Plantings-first
mode. It derives today's bed maps from active Plantings rows, uses both Plant and
Variety for timing, honors Clear Date, and uses each variety's Harvest Window
Days in the Gantt chart. The `Beds` tab controls bed numbers, names, dimensions,
display order, total capacity, and the shape of every grid in the app.

Recommended cutover:

1. Import `community-garden-plantings-first-v3.xlsx` as a new Google Sheet.
2. Share the new Sheet with the existing service-account email as a Viewer.
3. Confirm the Plantings and Plant Library data.
4. Copy the new spreadsheet ID.
5. Replace only `google_sheet.spreadsheet_id` in Streamlit Secrets.
6. Reboot the app and confirm the sidebar says
   **Live Google Sheet · Plantings-first**.

To roll back, restore the previous spreadsheet ID. No code rollback is needed.

## Files

- `app.py` — the Streamlit application
- `requirements.txt` — Python dependencies
- `community-garden-plantings-first-v3.xlsx` — current workbook to import into Google Sheets

## 1. Create the Google Sheet

1. Upload `community-garden-data-template.xlsx` to Google Drive.
2. Open the uploaded file.
3. Select **File → Save as Google Sheets**.
4. Confirm that these worksheet names remain unchanged:

   - `Bed Assignments`
   - `Plantings`
   - `Crop Library`

5. Keep the Sheet's general access set to **Restricted**.
6. Give trusted coordinators **Editor** access.

Do not rename the column headers. The app uses them to identify the data.

## 2. Create a read-only Google service account

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project, such as `Community Garden Planner`.
3. Open **APIs & Services → Library**.
4. Enable both:

   - Google Sheets API
   - Google Drive API

5. Open **IAM & Admin → Service Accounts**.
6. Select **Create service account**.
7. Name it `community-garden-reader`.
8. Finish creating it without assigning a project role.
9. Open the new service account and select **Keys**.
10. Select **Add key → Create new key → JSON**.
11. Download the JSON key and keep it private.

Never upload the JSON key to GitHub or place its contents in `app.py`.

## 3. Share the Sheet with the service account

1. Open the downloaded JSON key in a text editor.
2. Copy its `client_email` value. It ends in
   `iam.gserviceaccount.com`.
3. Open the Google Sheet and select **Share**.
4. Add the service-account email as a **Viewer**, not an Editor.

The app requests read-only Google API scopes, and the Sheet grants this account
viewer access only.

## 4. Find the spreadsheet ID

The Sheet address looks like:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
```

Copy only the value between `/d/` and `/edit`.

## 5. Add secrets to Streamlit Community Cloud

1. Open the app in your Streamlit Community Cloud workspace.
2. Open **App settings → Secrets**.
3. Add the following TOML, replacing every placeholder with the matching value
   from the downloaded JSON key:

```toml
[google_sheet]
spreadsheet_id = "YOUR_SPREADSHEET_ID"

[google_service_account]
type = "service_account"
project_id = "YOUR_PROJECT_ID"
private_key_id = "YOUR_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n"
client_email = "community-garden-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com"
client_id = "YOUR_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "YOUR_CLIENT_X509_CERT_URL"
```

The easiest way to avoid transcription mistakes is to copy each value directly
from the JSON file. The `private_key` value must include the complete
`-----BEGIN PRIVATE KEY-----` header, encoded key body, and
`-----END PRIVATE KEY-----` footer. Preserve the `\n` sequences between them.

4. Save the secrets.
5. Reboot the Streamlit app.

The sidebar should display **Data source: Live Google Sheet**. If it displays
sample data instead, check the service-account email sharing, spreadsheet ID,
worksheet names, APIs, and secret values.

## 6. Upload the updated project to GitHub

The repository root should contain:

```text
app.py
requirements.txt
README.md
community-garden-data-template.xlsx
```

Commit the updated files to the repository's `main` branch. Streamlit Community
Cloud normally redeploys automatically.

## Editing the garden

- Add or resize beds on `Beds`. Width creates lettered rows (A, B, C…) and
  Length creates numbered columns (1, 2, 3…). Width supports 1–26 feet and
  Length supports 1–50 feet.
- Add or update planting records on `Plantings`; its Bed dropdown comes from
  the `Beds` tab.
- Adjust variety-specific timing and display colors on `Plant Library`.
- Use **Refresh garden data** in Streamlit to reload immediately, or wait up to
  60 seconds for the cache to refresh.

For example, adding Bed 5 with Width 3 and Length 12 makes the app display a
3×12 square-foot grid and accept square references from A1 through C12. No code
change is required.

## Local development

Install the dependencies and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without local Streamlit secrets, the app intentionally uses its built-in sample
data.
