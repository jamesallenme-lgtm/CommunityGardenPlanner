from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="FBSS Hope Garden (Beta)",
    page_icon="🌱",
    layout="wide",
)

CROPS = {
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


def sample_beds() -> dict[int, dict[str, str]]:
    patterns = {
        1: ["Carrots"] * 8 + ["Beans"] * 8 + ["Collards"] * 8 + ["Okra"] * 8,
        2: ["Tomatoes"] * 8 + ["Lettuce"] * 16 + ["Peppers"] * 8,
        3: ["Beans"] * 16 + ["Carrots"] * 16,
        4: ["Collards"] * 16 + ["Empty"] * 16,
    }
    return {
        bed: dict(zip(square_ids(), crops, strict=True))
        for bed, crops in patterns.items()
    }


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


def calculate_dates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["Plant Date"] = pd.to_datetime(result["Plant Date"]).dt.date
    result["Germination Date"] = result.apply(
        lambda row: row["Plant Date"]
        + timedelta(days=CROPS.get(row["Crop"], CROPS["Empty"])["germination"]),
        axis=1,
    )
    result["Expected Harvest"] = result.apply(
        lambda row: row["Plant Date"]
        + timedelta(days=CROPS.get(row["Crop"], CROPS["Empty"])["harvest"]),
        axis=1,
    )
    return result


def initialize_state() -> None:
    if "beds" not in st.session_state:
        st.session_state.beds = sample_beds()
    if "plantings" not in st.session_state:
        st.session_state.plantings = sample_plantings()


def render_bed(bed_number: int, editable: bool = False) -> None:
    bed = st.session_state.beds[bed_number]
    st.markdown(f"#### Bed {bed_number} · 4 ft × 8 ft")
    for row in "ABCD":
        columns = st.columns(8, gap="small")
        for index, column_number in enumerate(range(1, 9)):
            square = f"{row}{column_number}"
            crop = bed[square]
            color = CROPS[crop]["color"]
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
    if editable:
        with st.expander(f"Edit Bed {bed_number} assignments"):
            edit_frame = pd.DataFrame(
                [
                    {"Square": square, "Crop": crop}
                    for square, crop in bed.items()
                ]
            )
            edited = st.data_editor(
                edit_frame,
                hide_index=True,
                width="stretch",
                disabled=["Square"],
                column_config={
                    "Crop": st.column_config.SelectboxColumn(
                        "Crop", options=list(CROPS), required=True
                    )
                },
                key=f"bed_editor_{bed_number}",
            )
            if st.button("Save assignments", key=f"save_bed_{bed_number}"):
                st.session_state.beds[bed_number] = dict(
                    zip(edited["Square"], edited["Crop"], strict=True)
                )
                st.success(f"Bed {bed_number} updated.")
                st.rerun()


def overview_page() -> None:
    st.title("🌱 FBSS Hope Garden (Beta)")
    st.caption("Four raised beds · 128 square feet · sample plan")
    planted = sum(
        crop != "Empty"
        for bed in st.session_state.beds.values()
        for crop in bed.values()
    )
    left, middle, right = st.columns(3)
    left.metric("Beds", 4)
    middle.metric("Planted squares", f"{planted} / 128")
    next_harvest = calculate_dates(st.session_state.plantings)[
        "Expected Harvest"
    ].min()
    right.metric("Next expected harvest", next_harvest.strftime("%b %d"))
    st.info(
        "Each cell represents one square foot. Use **Edit Bed Maps** to change crops."
    )
    for bed_number in range(1, 5):
        render_bed(bed_number)
        if bed_number < 4:
            st.divider()


def edit_beds_page() -> None:
    st.title("Edit Bed Maps")
    st.write(
        "Choose a crop for any square, save the bed, and the visual map updates immediately."
    )
    selected_bed = st.selectbox("Raised bed", [1, 2, 3, 4])
    render_bed(selected_bed, editable=True)


def plantings_page() -> None:
    st.title("Planting Records")
    st.write(
        "Germination and harvest dates are calculated from the crop timing library."
    )
    edited = st.data_editor(
        st.session_state.plantings,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Bed": st.column_config.SelectboxColumn(options=[1, 2, 3, 4], required=True),
            "Crop": st.column_config.SelectboxColumn(
                options=[crop for crop in CROPS if crop != "Empty"], required=True
            ),
            "Plant Date": st.column_config.DateColumn(required=True),
        },
        key="planting_editor",
    )
    if st.button("Save planting records", type="primary"):
        st.session_state.plantings = edited
        st.success("Planting records saved.")
        st.rerun()
    if not edited.empty:
        st.markdown("#### Calculated schedule")
        st.dataframe(
            calculate_dates(edited),
            hide_index=True,
            width="stretch",
            column_config={
                "Plant Date": st.column_config.DateColumn(format="MMM D, YYYY"),
                "Germination Date": st.column_config.DateColumn(format="MMM D, YYYY"),
                "Expected Harvest": st.column_config.DateColumn(format="MMM D, YYYY"),
            },
        )


def calendar_page() -> None:
    st.title("Tasks & Calendar")
    records = calculate_dates(st.session_state.plantings)
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
    task_frame = pd.DataFrame(tasks).sort_values("Date").reset_index(drop=True)
    filter_choice = st.radio(
        "Show", ["Upcoming", "All tasks"], horizontal=True
    )
    if filter_choice == "Upcoming":
        task_frame = task_frame[task_frame["Date"] >= date.today()]
    st.dataframe(
        task_frame,
        hide_index=True,
        width="stretch",
        column_config={"Date": st.column_config.DateColumn(format="ddd, MMM D, YYYY")},
    )
    st.caption(
        "This simple calendar is a chronological task list, which works well on phones."
    )


def crop_library_page() -> None:
    st.title("Crop Timing Library")
    library = pd.DataFrame(
        [
            {
                "Crop": crop,
                "Germination (days)": details["germination"],
                "Harvest (days)": details["harvest"],
            }
            for crop, details in CROPS.items()
            if crop != "Empty"
        ]
    )
    st.dataframe(library, hide_index=True, width="stretch")
    st.warning(
        "Timings are demonstration defaults. Adjust them for the variety, season, and local climate."
    )


initialize_state()
with st.sidebar:
    st.header("Community Garden")
    page = st.radio(
        "Go to",
        [
            "Garden Overview",
            "Edit Bed Maps",
            "Planting Records",
            "Tasks & Calendar",
            "Crop Library",
        ],
    )
    st.divider()
    if st.button("Reset sample data"):
        st.session_state.beds = sample_beds()
        st.session_state.plantings = sample_plantings()
        st.rerun()
    st.caption("Demo data is stored only for this browser session.")

pages = {
    "Garden Overview": overview_page,
    "Edit Bed Maps": edit_beds_page,
    "Planting Records": plantings_page,
    "Tasks & Calendar": calendar_page,
    "Crop Library": crop_library_page,
}
pages[page]()
