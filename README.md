[README.md](https://github.com/user-attachments/files/30571655/README.md)
# Community Garden Planner

A public, read-only Streamlit dashboard backed by a private Google Sheet.

The app includes:

- Four 4 ft × 8 ft raised beds shown as 32 one-square-foot cells each
- Planting records with calculated germination and harvest dates
- A chronological task/calendar view
- A crop timing library
- Automatic refresh from Google Sheets every 60 seconds

Garden coordinators edit the private Google Sheet. Public visitors can view the
dashboard but cannot change shared data from Streamlit.

## Files

- `app.py` — the Streamlit application
- `requirements.txt` — Python dependencies
- `community-garden-data-template.xlsx` — starter workbook to import into Google Sheets

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
from the JSON file. Preserve the `\n` sequences in `private_key`.

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

- Edit square assignments on `Bed Assignments`.
- Add or update planting records on `Plantings`.
- Adjust crop timing and display colors on `Crop Library`.
- Use **Refresh garden data** in Streamlit to reload immediately, or wait up to
  60 seconds for the cache to refresh.

## Local development

Install the dependencies and run:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Without local Streamlit secrets, the app intentionally uses its built-in sample
data.
