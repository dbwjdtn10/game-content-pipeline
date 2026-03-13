"""Streamlit dashboard for the Game Content Pipeline.

Run with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

API_BASE = st.sidebar.text_input("API Base URL", value="http://localhost:8000")

st.set_page_config(
    page_title="Game Content Pipeline",
    page_icon="🎮",
    layout="wide",
)


def api_get(path: str) -> dict[str, Any] | list[Any] | None:
    """GET helper that returns parsed JSON or None on error."""
    try:
        resp = httpx.get(f"{API_BASE}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"API request failed: {exc}")
        return None


def api_post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """POST helper."""
    try:
        resp = httpx.post(f"{API_BASE}{path}", json=payload or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"API request failed: {exc}")
        return None


# ------------------------------------------------------------------
# Sidebar navigation
# ------------------------------------------------------------------

page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Content Review", "Balance Chart", "Run Pipeline"],
)

# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


def page_overview() -> None:
    st.header("Pipeline Overview")

    data = api_get("/stats/overview")
    if data is None:
        return

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Content Items", data.get("total_content", 0))
    with col2:
        st.metric("Pipeline Runs", data.get("pipeline_runs", 0))

    st.subheader("Content Counts by Type & Status")

    counts = data.get("counts", [])
    if counts:
        import pandas as pd  # noqa: F811

        df = pd.DataFrame(counts)
        pivot = df.pivot_table(
            index="content_type",
            columns="status",
            values="count",
            aggfunc="sum",
            fill_value=0,
        )
        st.dataframe(pivot, use_container_width=True)
        st.bar_chart(pivot)
    else:
        st.info("No content data yet.")


def page_content_review() -> None:
    st.header("Content Review")

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        content_type = st.selectbox(
            "Content Type", ["all", "item", "monster", "quest", "skill"]
        )
    with col_filter2:
        status = st.selectbox(
            "Status", ["all", "draft", "reviewing", "approved", "rejected"]
        )

    params: dict[str, str] = {}
    if content_type != "all":
        params["content_type"] = content_type
    if status != "all":
        params["status"] = status

    query = "&".join(f"{k}={v}" for k, v in params.items())
    data = api_get(f"/content?{query}")
    if data is None:
        return

    items = data.get("items", [])
    if not items:
        st.info("No content items match the filters.")
        return

    for item in items:
        with st.expander(
            f"[{item['content_type'].upper()}] {item.get('content_id', item['id'])} "
            f"(v{item['version']}) - {item['status']}"
        ):
            st.json(item["data"])

            if item.get("validation_result"):
                st.subheader("Validation")
                st.json(item["validation_result"])

            if item["status"] in ("draft", "reviewing"):
                reviewer = st.text_input(
                    "Reviewer name", key=f"rev_{item['id']}"
                )
                comment = st.text_area(
                    "Comment (optional)", key=f"cmt_{item['id']}"
                )

                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button("Approve", key=f"approve_{item['id']}"):
                        if not reviewer:
                            st.warning("Enter a reviewer name.")
                        else:
                            result = api_post(
                                f"/content/{item['id']}/approve",
                                {"reviewed_by": reviewer, "comment": comment or None},
                            )
                            if result:
                                st.success("Approved!")
                                st.rerun()
                with col_r:
                    if st.button("Reject", key=f"reject_{item['id']}"):
                        if not reviewer:
                            st.warning("Enter a reviewer name.")
                        else:
                            result = api_post(
                                f"/content/{item['id']}/reject",
                                {"reviewed_by": reviewer, "comment": comment or None},
                            )
                            if result:
                                st.success("Rejected.")
                                st.rerun()


def page_balance_chart() -> None:
    st.header("Balance Chart - Stat Distributions")

    content_type = st.selectbox(
        "Content type to analyse",
        ["item", "monster", "skill"],
        key="balance_type",
    )

    data = api_get(f"/content?content_type={content_type}&status=approved&limit=500")
    if data is None:
        return

    items = data.get("items", [])
    if not items:
        st.info("No approved content of this type to chart.")
        return

    import pandas as pd

    # Extract stat fields
    stat_rows: list[dict[str, Any]] = []
    for item in items:
        content = item.get("data", {})
        stats = content.get("stats", {})
        if stats:
            row = {"name": content.get("name", content.get("id", "?"))}
            row.update(stats)
            stat_rows.append(row)

    if not stat_rows:
        st.info("No stat data found in items.")
        return

    df = pd.DataFrame(stat_rows).set_index("name")
    st.subheader("Stat Values")
    st.dataframe(df, use_container_width=True)

    st.subheader("Distribution per Stat")
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if numeric_cols:
        st.bar_chart(df[numeric_cols])

        st.subheader("Summary Statistics")
        st.dataframe(df[numeric_cols].describe(), use_container_width=True)


def page_run_pipeline() -> None:
    st.header("Run Pipeline")

    default_yaml = """\
name: example_pipeline
steps:
  - name: generate_items
    generator: generate
    params:
      content_type: item
  - name: validate_items
    generator: validate
    params:
      content_type: item
    depends_on:
      - generate_items
  - name: export_items
    generator: export
    params:
      export_format: json
    depends_on:
      - validate_items
"""

    yaml_config = st.text_area(
        "Pipeline YAML Config", value=default_yaml, height=300
    )
    retry_on_fail = st.number_input(
        "Retry on fail", min_value=0, max_value=5, value=0
    )

    if st.button("Run Pipeline"):
        result = api_post(
            "/pipeline/run",
            {"yaml_config": yaml_config, "retry_on_fail": retry_on_fail},
        )
        if result:
            st.success(f"Pipeline started: {result.get('pipeline_id')}")
            st.json(result)

    st.divider()
    st.subheader("Check Pipeline Status")
    pipeline_id = st.text_input("Pipeline Run ID")
    if pipeline_id and st.button("Check Status"):
        result = api_get(f"/pipeline/{pipeline_id}/status")
        if result:
            st.json(result)


# ------------------------------------------------------------------
# Page dispatch
# ------------------------------------------------------------------

if page == "Overview":
    page_overview()
elif page == "Content Review":
    page_content_review()
elif page == "Balance Chart":
    page_balance_chart()
elif page == "Run Pipeline":
    page_run_pipeline()
