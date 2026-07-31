from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Any

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials


st.set_page_config(
    page_title="Community Garden Planner",
    page_icon="🌱",
    layout="wide",
)

LOGGER = logging.getLogger("community_garden")

DEFAULT_CROPS = {
    "Empty": {"color": "#F4F1E8", "germination": 0, "harvest": 0},
    "Beans": {"color": "#83C57A", "germination": 7, "harvest": 55},
    "Carrots": {"color": "#F4A261", "germination": 10, "harvest": 70},
    "Collards": {"color": "#70A9A1", "germination": 8, "harvest": 60},
    "Lettuce": {"color": "#B7D77A", "germination": 7, "harvest": 45},
    "Okra": {"color": "#E9C46A", "germination": 7, "harvest": 55},
    "Peppers": {"color": "#E76F51", "germination": 10, "harvest": 75},
    "Tomatoes": {"color": "#D95D5D", "germination": 7, "harvest": 80},
}


def square_ids() -> list[str]:
    return [f"{row}{column}" for row in "ABCD" for column in range(1, 9)]


def sample_assignments() -> pd.DataFrame:
    patterns = {
        1: ["Carrots"] * 8 + ["Beans"] * 8 + ["Collards"] * 8 + ["Okra"] * 8,
        2: ["Tomatoes"] * 8 + ["Lettuce"] * 16 + ["Peppers"] * 8,
        3: ["Beans"] * 16 + ["Carrots"] * 16,
        4: ["Collards"] * 16 + ["Empty"] * 16,
    }
    rows = []
    for bed, crops in patterns.items():
        rows.extend(
            {"Bed": bed, "Square": square, "Crop": crop}
            for square, crop in zip(square_ids(), crops, strict=True)
        )
    return pd.DataFrame(rows)


def sample_plantings() -> pd.DataFrame:
    today = date.today()
    rows = [
        (1, "A1:A8", "Carrots", "Danvers", today - timedelta(days=12), "Direct sow"),
        (1, "B1:B8", "Beans", "Provider", today - timedelta(days=8), "Direct sow"),
        (1, "C1:C8", "Collards", "Champion", today - timedelta(days=18), "Transplant"),
        (1, "D1:D8", "Okra", "Clemson Spineless", today - timedelta(days=5), "Direct sow"),
        (2, "A1:A8", "Tomatoes", "Celebrity", today - timedelta(days=30), "Transplant"),
        (2, "B1:C8", "Lettuce", "Buttercrunch", today - timedelta(days=20), "Direct sow"),
    ]
    return pd.DataFrame(
        rows, columns=["Bed", "Squares", "Crop", "Variety", "Plant Date", "Notes"]
    )


def sample_crop_library() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Crop": crop,
                "Germination Days": details["germination"],
                "Harvest Days": details["harvest"],
                "Color": details["color"],
            }
            for crop, details in DEFAULT_CROPS.items()
            if crop != "Empty"
        ]
    )


def _worksheet_frame(spreadsheet: Any, worksheet_name: str) -> pd.DataFrame:
    records = spreadsheet.worksheet(worksheet_name).get_all_records()
    if not records:
        raise ValueError(f"The '{worksheet_name}' worksheet is empty.")
    return pd.DataFrame(records)


def connection_error_message(error: Exception) -> str:
    """Translate nested Google/cache errors into a safe public status message."""
    chain = []
    current: BaseException | None = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__

    details = " | ".join(chain).lower()
    if "secrets" in details or "google_service_account" in details:
        return "Streamlit Secrets are missing or incomplete"
    if "private key" in details or "malformederror" in details:
        return "the service-account private key is malformed"
    if "spreadsheetnotfound" in details or "requested entity was not found" in details:
        return "the spreadsheet ID is wrong or the Sheet was not shared with the service account"
    if "worksheetnotfound" in details:
        return "one or more worksheet names do not match the template"
    if "permission" in details or "403" in details:
        return "Google denied access; check API enablement and Sheet sharing"
    if "invalidgrant" in details or "invalid_grant" in details:
        return "Google rejected the service-account credentials"
    if "quota" in details or "429" in details:
        return "Google Sheets temporarily rate-limited the app"
    return "the Google Sheet connection failed; check the Streamlit app logs"


@st.cache_data(ttl=60, show_spinner="Loading the latest garden plan…")
def load_google_sheet_data() -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
    str | None,
]:
    try:
        service_account = dict(st.secrets["google_service_account"])
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        credentials = Credentials.from_service_account_info(
            service_account, scopes=scopes
        )
        client = gspread.authorize(credentials)
        spreadsheet_id = st.secrets["google_sheet"]["spreadsheet_id"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        return (
            _worksheet_frame(spreadsheet, "Bed Assignments"),
            _worksheet_frame(spreadsheet, "Plantings"),
            _worksheet_frame(spreadsheet, "Crop Library"),
            None,
        )
    except Exception as error:
        LOGGER.exception("Google Sheets data load failed")
        return None, None, None, connection_error_message(error)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    assignments, plantings, crop_library, connection_error = (
        load_google_sheet_data()
    )
    if connection_error is None:
        source = "Live Google Sheet"
    else:
        assignments = sample_assignments()
        plantings = sample_plantings()
        crop_library = sample_crop_library()
        source = f"Sample data — {connection_error}"

    assignments["Bed"] = pd.to_numeric(assignments["Bed"], errors="coerce").astype(
        "Int64"
    )
    plantings["Bed"] = pd.to_numeric(plantings["Bed"], errors="coerce").astype(
        "Int64"
    )
    plantings["Plant Date"] = pd.to_datetime(
        plantings["Plant Date"], errors="coerce"
    ).dt.date
    crop_library["Germination Days"] = pd.to_numeric(
        crop_library["Germination Days"], errors="coerce"
    ).fillna(0)
    crop_library["Harvest Days"] = pd.to_numeric(
        crop_library["Harvest Days"], errors="coerce"
    ).fillna(0)
    return assignments, plantings, crop_library, source


def crop_settings(crop_library: pd.DataFrame) -> dict[str, dict[str, Any]]:
    settings = {"Empty": DEFAULT_CROPS["Empty"].copy()}
    for _, row in crop_library.iterrows():
        crop = str(row["Crop"]).strip()
        settings[crop] = {
            "color": str(row.get("Color") or "#D9E3D5"),
            "germination": int(row["Germination Days"]),
            "harvest": int(row["Harvest Days"]),
        }
    return settings


def calculate_dates(
    plantings: pd.DataFrame, crops: dict[str, dict[str, Any]]
) -> pd.DataFrame:
    result = plantings.dropna(subset=["Plant Date"]).copy()
    result["Germination Date"] = result.apply(
        lambda row: row["Plant Date"]
        + timedelta(days=crops.get(str(row["Crop"]), crops["Empty"])["germination"]),
        axis=1,
    )
    result["Expected Harvest"] = result.apply(
        lambda row: row["Plant Date"]
        + timedelta(days=crops.get(str(row["Crop"]), crops["Empty"])["harvest"]),
        axis=1,
    )
    return result


def bed_map(assignments: pd.DataFrame, bed_number: int) -> dict[str, str]:
    bed_rows = assignments[assignments["Bed"] == bed_number]
    values = {
        str(row["Square"]).strip().upper(): str(row["Crop"]).strip()
        for _, row in bed_rows.iterrows()
    }
    return {square: values.get(square, "Empty") for square in square_ids()}


def render_bed(
    assignments: pd.DataFrame,
    crops: dict[str, dict[str, Any]],
    bed_number: int,
) -> None:
    bed = bed_map(assignments, bed_number)
    st.markdown(f"#### Bed {bed_number} · 4 ft × 8 ft")
    for row in "ABCD":
        columns = st.columns(8, gap="small")
        for index, column_number in enumerate(range(1, 9)):
            square = f"{row}{column_number}"
            crop = bed[square]
            color = crops.get(crop, {"color": "#D9E3D5"})["color"]
            columns[index].markdown(
                (
                    f"<div title='{square}: {crop}' style='background:{color};"
                    "border:1px solid #62705c;border-radius:6px;min-height:68px;"
                    "display:flex;flex-direction:column;align-items:center;"
                    "justify-content:center;text-align:center;padding:4px;"
                    "overflow:hidden'>"
                    f"<strong>{square}</strong><small style='font-size:0.72rem;"
                    "line-height:1.05;max-width:100%;overflow-wrap:anywhere;"
                    f"word-break:break-word'>{crop}</small></div>"
                ),
                unsafe_allow_html=True,
            )


def overview_page(
    assignments: pd.DataFrame,
    plantings: pd.DataFrame,
    crops: dict[str, dict[str, Any]],
) -> None:
    st.title("🌱 Community Garden Planner")
    st.caption("Four raised beds · 128 square feet · read-only public view")
    planted = int((assignments["Crop"].astype(str) != "Empty").sum())
    schedule = calculate_dates(plantings, crops)
    upcoming = schedule[schedule["Expected Harvest"] >= date.today()]
    next_harvest = (
        upcoming["Expected Harvest"].min().strftime("%b %d")
        if not upcoming.empty
        else "None scheduled"
    )
    left, middle, right = st.columns(3)
    left.metric("Beds", 4)
    middle.metric("Planted squares", f"{planted} / 128")
    right.metric("Next expected harvest", next_harvest)
    st.info("Garden coordinators update the private Google Sheet. This page is view-only.")
    for bed_number in range(1, 5):
        render_bed(assignments, crops, bed_number)
        if bed_number < 4:
            st.divider()


def plantings_page(
    plantings: pd.DataFrame, crops: dict[str, dict[str, Any]]
) -> None:
    st.title("Planting Records")
    st.write("Germination and harvest dates use the timing values in the Google Sheet.")
    records = calculate_dates(plantings, crops)
    st.dataframe(
        records,
        hide_index=True,
        width="stretch",
        column_config={
            "Plant Date": st.column_config.DateColumn(format="MMM D, YYYY"),
            "Germination Date": st.column_config.DateColumn(format="MMM D, YYYY"),
            "Expected Harvest": st.column_config.DateColumn(format="MMM D, YYYY"),
        },
    )


def calendar_page(
    plantings: pd.DataFrame, crops: dict[str, dict[str, Any]]
) -> None:
    st.title("Tasks & Calendar")
    records = calculate_dates(plantings, crops)
    tasks = []
    for _, row in records.iterrows():
        label = f"Bed {row['Bed']} · {row['Crop']} ({row['Squares']})"
        tasks.extend(
            [
                {"Date": row["Plant Date"], "Task": f"Plant {label}", "Type": "Plant"},
                {
                    "Date": row["Germination Date"],
                    "Task": f"Check germination: {label}",
                    "Type": "Germination",
                },
                {
                    "Date": row["Expected Harvest"],
                    "Task": f"Begin harvest: {label}",
                    "Type": "Harvest",
                },
            ]
        )
    task_frame = pd.DataFrame(tasks, columns=["Date", "Task", "Type"])
    if not task_frame.empty:
        task_frame = task_frame.sort_values("Date").reset_index(drop=True)
    filter_choice = st.radio("Show", ["Upcoming", "All tasks"], horizontal=True)
    if filter_choice == "Upcoming":
        task_frame = task_frame[task_frame["Date"] >= date.today()]
    st.dataframe(
        task_frame,
        hide_index=True,
        width="stretch",
        column_config={"Date": st.column_config.DateColumn(format="ddd, MMM D, YYYY")},
    )


def crop_library_page(crop_library: pd.DataFrame) -> None:
    st.title("Crop Timing Library")
    st.dataframe(crop_library, hide_index=True, width="stretch")
    st.warning(
        "Timings are planning estimates. Adjust them in the private Sheet for the variety, season, and local climate."
    )


assignments_data, plantings_data, crop_library_data, data_source = load_data()
crop_data = crop_settings(crop_library_data)

with st.sidebar:
    st.header("Community Garden")
    page = st.radio(
        "Go to",
        ["Garden Overview", "Planting Records", "Tasks & Calendar", "Crop Library"],
    )
    st.divider()
    if st.button("Refresh garden data"):
        load_google_sheet_data.clear()
        st.rerun()
    if data_source == "Live Google Sheet":
        st.success("Data source: Live Google Sheet")
    else:
        st.warning(f"Data source: {data_source}")
    st.caption("Public visitors cannot edit garden data from this app.")

if page == "Garden Overview":
    overview_page(assignments_data, plantings_data, crop_data)
elif page == "Planting Records":
    plantings_page(plantings_data, crop_data)
elif page == "Tasks & Calendar":
    calendar_page(plantings_data, crop_data)
else:
    crop_library_page(crop_library_data)
