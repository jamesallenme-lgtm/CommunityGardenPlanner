from __future__ import annotations

from datetime import date, timedelta
import html
import logging
from pathlib import Path
import re
from typing import Any

import altair as alt
import gspread
import pandas as pd
import streamlit as st
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials


DEFAULT_APP_TITLE = "Community Garden Planner"
APP_ICON = Path(__file__).resolve().parent / "assets" / "garden-icon.png"

st.set_page_config(
    page_title=DEFAULT_APP_TITLE,
    page_icon=str(APP_ICON),
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


def square_ids(width: int = 4, length: int = 8) -> list[str]:
    return [
        f"{chr(65 + row)}{column}"
        for row in range(width)
        for column in range(1, length + 1)
    ]


def sample_beds() -> pd.DataFrame:
    return pd.DataFrame(
        [(bed, f"Bed {bed}", 4, 8, bed) for bed in range(1, 5)],
        columns=["Bed", "Bed Name", "Width (ft)", "Length (ft)", "Display Order"],
    )


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
            for square, crop in zip(square_ids(4, 8), crops, strict=True)
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
    rows = [
        ("Beans", "Provider", 7, 55, 14, "#83C57A"),
        ("Beans", "Blue Lake", 8, 60, 14, "#83C57A"),
        ("Carrots", "Danvers", 10, 70, 14, "#F4A261"),
        ("Carrots", "Nantes", 14, 75, 14, "#F4A261"),
        ("Collards", "Champion", 8, 60, 30, "#70A9A1"),
        ("Lettuce", "Buttercrunch", 7, 45, 14, "#B7D77A"),
        ("Okra", "Clemson Spineless", 7, 55, 21, "#E9C46A"),
        ("Peppers", "California Wonder", 10, 75, 30, "#E76F51"),
        ("Tomatoes", "Celebrity", 7, 80, 30, "#D95D5D"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Crop",
            "Variety",
            "Germination Days",
            "Harvest Days",
            "Harvest Window Days",
            "Color",
        ],
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
    if (
        "private key" in details
        or "malformederror" in details
        or "unable to load pem" in details
        or "invalidheader" in details
    ):
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
    pd.DataFrame | None,
    str | None,
    str | None,
    str,
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
        app_title = str(spreadsheet.title or "").strip() or DEFAULT_APP_TITLE
        plantings = _worksheet_frame(spreadsheet, "Plantings")
        try:
            plant_library = _worksheet_frame(spreadsheet, "Plant Library")
            try:
                beds = _worksheet_frame(spreadsheet, "Beds")
            except WorksheetNotFound:
                beds = sample_beds()
            return (
                None,
                plantings,
                plant_library,
                beds,
                "Plantings-first",
                None,
                app_title,
            )
        except WorksheetNotFound:
            return (
                _worksheet_frame(spreadsheet, "Bed Assignments"),
                plantings,
                _worksheet_frame(spreadsheet, "Crop Library"),
                sample_beds(),
                "Legacy",
                None,
                app_title,
            )
    except Exception as error:
        LOGGER.exception("Google Sheets data load failed")
        return (
            None,
            None,
            None,
            None,
            None,
            connection_error_message(error),
            DEFAULT_APP_TITLE,
        )


def expand_square_spec(
    specification: Any, width: int = 4, length: int = 8
) -> list[str]:
    """Expand A1, A1:B4, and comma-separated combinations into square IDs."""
    valid_square = re.compile(r"^([A-Z])([1-9][0-9]*)$")
    expanded: list[str] = []
    for raw_token in str(specification or "").upper().split(","):
        token = raw_token.strip().replace(" ", "")
        if not token:
            continue
        endpoints = token.split(":")
        if len(endpoints) not in (1, 2):
            raise ValueError(f"Invalid square range: {raw_token.strip()}")
        start_match = valid_square.match(endpoints[0])
        end_match = valid_square.match(endpoints[-1])
        if not start_match or not end_match:
            raise ValueError(f"Invalid square range: {raw_token.strip()}")
        start_row, start_column = start_match.group(1), int(start_match.group(2))
        end_row, end_column = end_match.group(1), int(end_match.group(2))
        if (
            ord(start_row) - 64 > width
            or ord(end_row) - 64 > width
            or start_column > length
            or end_column > length
        ):
            raise ValueError(
                f"Square range is outside this {width} ft × {length} ft bed: "
                f"{raw_token.strip()}"
            )
        row_start, row_end = sorted((ord(start_row), ord(end_row)))
        column_start, column_end = sorted((start_column, end_column))
        expanded.extend(
            f"{chr(row)}{column}"
            for row in range(row_start, row_end + 1)
            for column in range(column_start, column_end + 1)
        )
    return list(dict.fromkeys(expanded))


def assignments_from_plantings(
    plantings: pd.DataFrame, beds: pd.DataFrame
) -> pd.DataFrame:
    """Derive today's bed occupancy; newer active plantings win overlaps."""
    today = date.today()
    active = plantings.dropna(subset=["Bed", "Plant Date"]).copy()
    active = active[
        active["Plant Date"].apply(
            lambda value: pd.notna(value) and pd.Timestamp(value).date() <= today
        )
    ]
    if "Clear Date" in active.columns:
        active = active[
            active["Clear Date"].apply(
                lambda value: pd.isna(value) or pd.Timestamp(value).date() > today
            )
        ]
    active = active.assign(
        _sort_date=pd.to_datetime(active["Plant Date"], errors="coerce")
    ).sort_values("_sort_date")
    occupied: dict[tuple[int, str], str] = {}
    bed_sizes = {
        int(row["Bed"]): (int(row["Width (ft)"]), int(row["Length (ft)"]))
        for _, row in beds.iterrows()
    }
    for _, row in active.iterrows():
        bed_number = int(row["Bed"])
        if bed_number not in bed_sizes:
            LOGGER.warning("Skipping planting for undefined Bed %s", bed_number)
            continue
        try:
            squares = expand_square_spec(row.get("Squares"), *bed_sizes[bed_number])
        except ValueError as error:
            LOGGER.warning("Skipping planting with %s", error)
            continue
        crop = str(row.get("Crop", "")).strip()
        if not crop:
            continue
        for square in squares:
            occupied[(bed_number, square)] = crop
    return pd.DataFrame(
        [
            {"Bed": bed, "Square": square, "Crop": crop}
            for (bed, square), crop in occupied.items()
        ],
        columns=["Bed", "Square", "Crop"],
    )


def normalize_beds(beds: pd.DataFrame) -> pd.DataFrame:
    """Validate and order spreadsheet-defined beds."""
    aliases = {"Name": "Bed Name", "Width": "Width (ft)", "Length": "Length (ft)"}
    beds = beds.rename(columns={key: value for key, value in aliases.items() if key in beds})
    required = {"Bed", "Width (ft)", "Length (ft)"}
    if not required.issubset(beds.columns):
        raise ValueError("Beds must include Bed, Width (ft), and Length (ft) columns.")
    if "Bed Name" not in beds.columns:
        beds["Bed Name"] = ""
    if "Display Order" not in beds.columns:
        beds["Display Order"] = range(1, len(beds) + 1)
    for column in ["Bed", "Width (ft)", "Length (ft)", "Display Order"]:
        beds[column] = pd.to_numeric(beds[column], errors="coerce")
    beds = beds.dropna(subset=["Bed", "Width (ft)", "Length (ft)"]).copy()
    beds = beds[
        beds["Bed"].between(1, 999)
        & beds["Width (ft)"].between(1, 26)
        & beds["Length (ft)"].between(1, 50)
    ]
    if beds.empty:
        raise ValueError("The Beds worksheet does not contain a valid bed.")
    beds[["Bed", "Width (ft)", "Length (ft)"]] = beds[
        ["Bed", "Width (ft)", "Length (ft)"]
    ].astype(int)
    beds["Display Order"] = beds["Display Order"].fillna(beds["Bed"]).astype(int)
    beds["Bed Name"] = beds.apply(
        lambda row: str(row["Bed Name"]).strip() or f"Bed {int(row['Bed'])}", axis=1
    )
    return beds.drop_duplicates("Bed", keep="last").sort_values(
        ["Display Order", "Bed"]
    )


def load_data() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    str,
    str,
    str,
]:
    assignments, plantings, crop_library, beds, schema, connection_error, app_title = (
        load_google_sheet_data()
    )
    if connection_error is None:
        source = f"Live Google Sheet · {schema}"
    else:
        assignments = sample_assignments()
        plantings = sample_plantings()
        crop_library = sample_crop_library()
        beds = sample_beds()
        schema = "Sample"
        source = f"Sample data — {connection_error}"
        app_title = DEFAULT_APP_TITLE

    if "Plant" in plantings.columns and "Crop" not in plantings.columns:
        plantings = plantings.rename(columns={"Plant": "Crop"})
    if "Plant" in crop_library.columns and "Crop" not in crop_library.columns:
        crop_library = crop_library.rename(columns={"Plant": "Crop"})
    plantings["Bed"] = pd.to_numeric(plantings["Bed"], errors="coerce").astype(
        "Int64"
    )
    plantings["Plant Date"] = pd.to_datetime(
        plantings["Plant Date"], errors="coerce"
    ).dt.date
    if "Clear Date" in plantings.columns:
        plantings["Clear Date"] = pd.to_datetime(
            plantings["Clear Date"], errors="coerce"
        ).dt.date
    plantings = plantings.dropna(subset=["Bed", "Plant Date"])
    crop_library["Germination Days"] = pd.to_numeric(
        crop_library["Germination Days"], errors="coerce"
    ).fillna(0)
    crop_library["Harvest Days"] = pd.to_numeric(
        crop_library["Harvest Days"], errors="coerce"
    ).fillna(0)
    if "Harvest Window Days" not in crop_library.columns:
        crop_library["Harvest Window Days"] = 14
    crop_library["Harvest Window Days"] = pd.to_numeric(
        crop_library["Harvest Window Days"], errors="coerce"
    ).fillna(14)
    beds = normalize_beds(beds)
    if schema == "Plantings-first":
        assignments = assignments_from_plantings(plantings, beds)
    assignments["Bed"] = pd.to_numeric(assignments["Bed"], errors="coerce").astype(
        "Int64"
    )
    return assignments, plantings, crop_library, beds, source, str(schema), app_title


def crop_settings(crop_library: pd.DataFrame) -> dict[str, dict[str, Any]]:
    settings = {"Empty": DEFAULT_CROPS["Empty"].copy()}
    for _, row in crop_library.iterrows():
        crop = str(row["Crop"]).strip()
        variety = str(row.get("Variety", "")).strip()
        details = {
            "color": str(row.get("Color") or "#D9E3D5"),
            "germination": int(row["Germination Days"]),
            "harvest": int(row["Harvest Days"]),
            "harvest_window": int(row.get("Harvest Window Days", 14)),
        }
        settings[f"{crop}\x1f{variety}"] = details
        settings.setdefault(crop, details)
    return settings


def planting_timing(
    crops: dict[str, dict[str, Any]], crop: Any, variety: Any = ""
) -> dict[str, Any]:
    crop_name = str(crop).strip()
    variety_name = str(variety or "").strip()
    return crops.get(
        f"{crop_name}\x1f{variety_name}",
        crops.get(crop_name, crops["Empty"]),
    )


def calculate_dates(
    plantings: pd.DataFrame, crops: dict[str, dict[str, Any]]
) -> pd.DataFrame:
    result = plantings.dropna(subset=["Plant Date"]).copy()
    result["Germination Date"] = result.apply(
        lambda row: row["Plant Date"]
        + timedelta(
            days=planting_timing(crops, row["Crop"], row.get("Variety"))["germination"]
        ),
        axis=1,
    )
    result["Expected Harvest"] = result.apply(
        lambda row: row["Plant Date"]
        + timedelta(
            days=planting_timing(crops, row["Crop"], row.get("Variety"))["harvest"]
        ),
        axis=1,
    )
    result["Harvest Window Days"] = result.apply(
        lambda row: planting_timing(crops, row["Crop"], row.get("Variety")).get(
            "harvest_window", 14
        ),
        axis=1,
    )
    result["Harvest Window End"] = result.apply(
        lambda row: row["Expected Harvest"]
        + timedelta(days=int(row["Harvest Window Days"])),
        axis=1,
    )
    return result


def bed_map(
    assignments: pd.DataFrame, bed_number: int, width: int, length: int
) -> dict[str, str]:
    bed_rows = assignments[assignments["Bed"] == bed_number]
    values = {
        str(row["Square"]).strip().upper(): str(row["Crop"]).strip()
        for _, row in bed_rows.iterrows()
    }
    return {
        square: values.get(square, "Empty") for square in square_ids(width, length)
    }


def bed_grid_html(
    assignments: pd.DataFrame,
    crops: dict[str, dict[str, Any]],
    bed_number: int,
    width: int,
    length: int,
    compact: bool = False,
) -> str:
    bed = bed_map(assignments, bed_number, width, length)
    cells = []
    for row_number in range(width):
        row = chr(65 + row_number)
        for column_number in range(1, length + 1):
            square = f"{row}{column_number}"
            crop = bed[square]
            color = crops.get(crop, {"color": "#D9E3D5"})["color"]
            content = "" if compact else (
                f"<strong>{html.escape(square)}</strong>"
                f"<small>{html.escape(crop)}</small>"
            )
            cells.append(
                f"<div class='garden-cell' title='{html.escape(square)}: "
                f"{html.escape(crop)}' style='background:{html.escape(str(color))};'>"
                f"{content}</div>"
            )
    mode = "compact-grid" if compact else "bed-grid"
    return (
        f"<div class='{mode}' style='grid-template-columns:repeat({length},minmax(0,1fr));'>"
        f"{''.join(cells)}</div>"
    )


def render_responsive_garden(
    assignments: pd.DataFrame,
    crops: dict[str, dict[str, Any]],
    beds: pd.DataFrame,
) -> None:
    desktop_beds = []
    compact_beds = []
    mobile_details = []
    for _, bed_row in beds.iterrows():
        bed_number = int(bed_row["Bed"])
        bed_name = html.escape(str(bed_row["Bed Name"]))
        width = int(bed_row["Width (ft)"])
        length = int(bed_row["Length (ft)"])
        dimensions = f"{width} ft x {length} ft"
        desktop_beds.append(
            f"<section class='desktop-bed'><h4>{bed_name} - {dimensions}</h4>"
            f"{bed_grid_html(assignments, crops, bed_number, width, length)}</section>"
        )
        compact_beds.append(
            f"<section class='compact-bed'><div class='compact-title'>{bed_name}</div>"
            f"{bed_grid_html(assignments, crops, bed_number, width, length, compact=True)}</section>"
        )
        mobile_details.append(
            f"<details class='mobile-bed-detail'><summary>View {bed_name} details</summary>"
            f"<div class='detail-heading'>{bed_name} - {dimensions}</div>"
            f"{bed_grid_html(assignments, crops, bed_number, width, length)}</details>"
        )

    planted_crops = sorted(
        {
            str(value).strip()
            for value in assignments["Crop"].dropna()
            if str(value).strip() and str(value).strip() != "Empty"
        }
    )
    legend = "".join(
        f"<span class='crop-legend-item'><i style='background:"
        f"{html.escape(str(crops.get(crop, {'color': '#D9E3D5'})['color']))};'></i>"
        f"{html.escape(crop)}</span>"
        for crop in planted_crops
    )

    st.markdown(
        f"""
        <style>
          .garden-desktop {{ display:block; }}
          .garden-mobile {{ display:none; }}
          .desktop-bed {{ margin:0 0 1.35rem 0; }}
          .desktop-bed h4 {{ margin:.2rem 0 .5rem 0; }}
          .bed-grid, .compact-grid {{
            display:grid; gap:4px;
          }}
          .garden-cell {{
            border:1px solid #62705c; border-radius:6px; min-height:68px;
            display:flex; flex-direction:column; align-items:center;
            justify-content:center; text-align:center; padding:4px; overflow:hidden;
          }}
          .garden-cell small {{
            font-size:.72rem; line-height:1.05; max-width:100%;
            overflow-wrap:anywhere; word-break:break-word;
          }}
          .crop-legend {{ display:flex; flex-wrap:wrap; gap:6px 12px; margin:.6rem 0 1rem; }}
          .crop-legend-item {{ display:inline-flex; align-items:center; font-size:.78rem; }}
          .crop-legend-item i {{
            width:12px; height:12px; border:1px solid #62705c;
            border-radius:3px; margin-right:5px;
          }}
          @media (max-width:700px) {{
            .garden-desktop {{ display:none; }}
            .garden-mobile {{ display:block; }}
            .mobile-plan {{
              border-left:3px solid #a7b5a2; padding-left:10px; margin:.3rem 0 1rem;
            }}
            .compact-bed {{ margin:0 0 9px 0; }}
            .compact-title {{ font-size:.8rem; font-weight:700; margin-bottom:2px; }}
            .compact-grid {{ gap:2px; }}
            .compact-grid .garden-cell {{
              min-height:9px; height:9px; padding:0; border-radius:2px; border-width:1px;
            }}
            .mobile-bed-detail {{
              border:1px solid #ccd6c8; border-radius:7px; margin:7px 0;
              padding:7px 9px; background:#999999;
            }}
            .mobile-bed-detail summary {{ cursor:pointer; font-weight:700; }}
            .detail-heading {{ font-size:.82rem; margin:8px 0 4px; color:#52604e; }}
            .mobile-bed-detail .bed-grid {{ gap:2px; }}
            .mobile-bed-detail .garden-cell {{ min-height:48px; padding:2px; }}
            .mobile-bed-detail .garden-cell small {{ font-size:.62rem; }}
          }}
        </style>
        <div class="crop-legend">{legend}</div>
        <div class="garden-desktop">{''.join(desktop_beds)}</div>
        <div class="garden-mobile">
          <div class="mobile-plan">{''.join(compact_beds)}</div>
          <div class="mobile-detail-list">{''.join(mobile_details)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def overview_page(
    assignments: pd.DataFrame,
    plantings: pd.DataFrame,
    crops: dict[str, dict[str, Any]],
    beds: pd.DataFrame,
    app_title: str,
) -> None:
    st.title(app_title)
    capacity = int((beds["Width (ft)"] * beds["Length (ft)"]).sum())
    st.caption(f"{len(beds)} raised beds · {capacity} square feet · read-only public view")
    planted = int((assignments["Crop"].astype(str) != "Empty").sum())
    schedule = calculate_dates(plantings, crops)
    upcoming = schedule[schedule["Expected Harvest"] >= date.today()]
    next_harvest = (
        upcoming["Expected Harvest"].min().strftime("%b %d")
        if not upcoming.empty
        else "None scheduled"
    )
    left, middle, right = st.columns(3)
    left.metric("Beds", len(beds))
    middle.metric("Planted squares", f"{planted} / {capacity}")
    right.metric("Next expected harvest", next_harvest)
    st.info("Garden coordinators update the private Google Sheet. This page is view-only.")
    render_responsive_garden(assignments, crops, beds)


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
    view = st.radio("View", ["Task list", "Gantt timeline"], horizontal=True)
    if view == "Task list":
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
            column_config={
                "Date": st.column_config.DateColumn(format="ddd, MMM D, YYYY")
            },
        )
        return

    render_gantt_chart(records)


def render_gantt_chart(records: pd.DataFrame) -> None:
    if records.empty:
        st.info("Add planting records to display the timeline.")
        return

    bed_values = sorted(int(value) for value in records["Bed"].dropna().unique())
    selected_bed = st.selectbox("Bed", ["All beds", *bed_values])

    filtered = records
    if selected_bed != "All beds":
        filtered = records[records["Bed"] == selected_bed]

    phase_rows = []
    for index, row in filtered.reset_index(drop=True).iterrows():
        planting_label = (
            f"Bed {int(row['Bed'])} · {row['Crop']} · {row['Squares']}"
        )
        if pd.notna(row.get("Variety")) and str(row.get("Variety")).strip():
            planting_label += f" · {row['Variety']}"
        germination_end = row["Germination Date"] + timedelta(days=1)
        harvest_start = row["Expected Harvest"]
        phase_rows.extend(
            [
                {
                    "Planting": planting_label,
                    "Order": index,
                    "Phase": "Germination",
                    "Start": row["Plant Date"],
                    "End": germination_end,
                },
                {
                    "Planting": planting_label,
                    "Order": index,
                    "Phase": "Growth",
                    "Start": germination_end,
                    "End": harvest_start,
                },
                {
                    "Planting": planting_label,
                    "Order": index,
                    "Phase": "Harvest",
                    "Start": harvest_start,
                    "End": harvest_start
                    + timedelta(days=int(row.get("Harvest Window Days", 14))),
                },
            ]
        )

    gantt_data = pd.DataFrame(phase_rows)
    gantt_data["Start"] = pd.to_datetime(gantt_data["Start"])
    gantt_data["End"] = pd.to_datetime(gantt_data["End"])
    phase_order = ["Germination", "Growth", "Harvest"]
    phase_range = ["#5B8FF9", "#61B15A", "#E3A62F"]

    bars = (
        alt.Chart(gantt_data)
        .mark_bar(cornerRadius=3, height=18)
        .encode(
            x=alt.X(
                "Start:T",
                title="Date",
                axis=alt.Axis(format="%b %d", labelAngle=-35, grid=True),
            ),
            x2="End:T",
            y=alt.Y(
                "Planting:N",
                title=None,
                sort=alt.SortField(field="Order", order="ascending"),
                axis=alt.Axis(labelLimit=330),
            ),
            color=alt.Color(
                "Phase:N",
                scale=alt.Scale(domain=phase_order, range=phase_range),
                legend=alt.Legend(title="Period", orient="top"),
            ),
            tooltip=[
                alt.Tooltip("Planting:N"),
                alt.Tooltip("Phase:N"),
                alt.Tooltip("Start:T", format="%b %d, %Y"),
                alt.Tooltip("End:T", format="%b %d, %Y"),
            ],
        )
    )
    today_rule = (
        alt.Chart(pd.DataFrame({"Today": [pd.Timestamp(date.today())]}))
        .mark_rule(color="#B23A48", strokeWidth=2, strokeDash=[5, 4])
        .encode(
            x="Today:T",
            tooltip=[alt.Tooltip("Today:T", title="Today", format="%b %d, %Y")],
        )
    )
    chart_height = max(260, 48 * len(filtered))
    chart = (
        (bars + today_rule)
        .properties(height=chart_height)
        .configure_view(stroke=None)
        .configure_axis(labelFontSize=11, titleFontSize=12)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(
        "The dashed red line marks today. Harvest-window length comes from the plant and variety library."
    )


def crop_library_page(crop_library: pd.DataFrame, schema: str) -> None:
    title = "Plant & Variety Library" if schema == "Plantings-first" else "Crop Timing Library"
    st.title(title)
    display_library = crop_library
    if schema == "Plantings-first":
        display_library = crop_library.rename(columns={"Crop": "Plant"})
    st.dataframe(display_library, hide_index=True, width="stretch")
    st.warning(
        "Timings are planning estimates. Adjust them in the private Sheet for the variety, season, and local climate."
    )


(
    assignments_data,
    plantings_data,
    crop_library_data,
    beds_data,
    data_source,
    sheet_schema,
    app_title,
) = load_data()
st.set_page_config(page_title=app_title, page_icon=str(APP_ICON))
crop_data = crop_settings(crop_library_data)
library_page_label = (
    "Plant Library" if sheet_schema == "Plantings-first" else "Crop Library"
)

with st.sidebar:
    st.header(app_title)
    page = st.radio(
        "Go to",
        ["Garden Overview", "Planting Records", "Tasks & Calendar", library_page_label],
    )
    st.divider()
    if st.button("Refresh garden data"):
        load_google_sheet_data.clear()
        st.rerun()
    if data_source.startswith("Live Google Sheet"):
        st.success(f"Data source: {data_source}")
    else:
        st.warning(f"Data source: {data_source}")
    st.caption("Public visitors cannot edit garden data from this app.")

if page == "Garden Overview":
    overview_page(assignments_data, plantings_data, crop_data, beds_data, app_title)
elif page == "Planting Records":
    plantings_page(plantings_data, crop_data)
elif page == "Tasks & Calendar":
    calendar_page(plantings_data, crop_data)
else:
    crop_library_page(crop_library_data, sheet_schema)
