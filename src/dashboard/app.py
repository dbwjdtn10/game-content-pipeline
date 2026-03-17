"""Streamlit dashboard for the Game Content Pipeline.

Run with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import streamlit as st

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

st.set_page_config(
    page_title="Game Content Pipeline",
    page_icon="🎮",
    layout="wide",
)

API_BASE = st.sidebar.text_input("API Base URL", value="http://localhost:8000")


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
    [
        "Overview",
        "Content Review",
        "Version History",
        "Balance Chart",
        "Pipeline Runs",
        "Run Pipeline",
    ],
)

# ------------------------------------------------------------------
# Helper: Validation result display
# ------------------------------------------------------------------


def render_validation_result(validation: dict[str, Any]) -> None:
    """Render validation results with color-coded severity indicators."""
    checks = validation.get("checks", [])
    regen = validation.get("regeneration")

    if regen:
        attempts = regen.get("attempts", 0)
        succeeded = regen.get("succeeded", False)
        if succeeded:
            st.success(f"Auto-regeneration succeeded after {attempts} attempt(s)")
        else:
            st.warning(f"Auto-regeneration exhausted {attempts} attempts without full success")

        history = regen.get("validation_history", [])
        if history:
            with st.expander(f"Regeneration History ({len(history)} rounds)"):
                for i, round_results in enumerate(history, 1):
                    st.markdown(f"**Round {i}**")
                    for check in round_results:
                        _render_single_check(check)
                    st.divider()

    if not checks and not regen:
        st.json(validation)
        return

    for check in checks:
        _render_single_check(check)


def _render_single_check(check: dict[str, Any]) -> None:
    """Render a single validation check result."""
    passed = check.get("passed", True)
    severity = check.get("severity", "info")
    name = check.get("check_name", "unknown")
    message = check.get("message", "")

    if passed:
        icon = "✅"
    elif severity == "error":
        icon = "❌"
    else:
        icon = "⚠️"

    st.markdown(f"{icon} **{name}** — {message}")

    details = check.get("details")
    if details and not passed:
        with st.expander(f"Details: {name}"):
            st.json(details)


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


def page_overview() -> None:
    st.header("Pipeline Overview")

    data = api_get("/stats/overview")
    if data is None:
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Content Items", data.get("total_content", 0))
    with col2:
        st.metric("Pipeline Runs", data.get("pipeline_runs", 0))
    with col3:
        counts = data.get("counts", [])
        approved = sum(c["count"] for c in counts if c.get("status") == "approved")
        st.metric("Approved Items", approved)

    st.subheader("Content Counts by Type & Status")

    if counts:
        import pandas as pd

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
        label = (
            f"[{item['content_type'].upper()}] {item.get('content_id', item['id'])} "
            f"(v{item['version']}) — {item['status']}"
        )
        with st.expander(label):
            # Content data
            tab_data, tab_validation, tab_actions = st.tabs(
                ["Content Data", "Validation", "Actions"]
            )

            with tab_data:
                content_data = item.get("data", {})
                # Show key fields in a structured way
                if "name" in content_data:
                    st.markdown(f"**Name:** {content_data['name']}")
                if "rarity" in content_data:
                    st.markdown(f"**Rarity:** {content_data['rarity']}")
                if "type" in content_data:
                    st.markdown(f"**Type:** {content_data['type']}")
                if "level_requirement" in content_data or "level" in content_data:
                    lvl = content_data.get("level_requirement", content_data.get("level"))
                    st.markdown(f"**Level:** {lvl}")
                if "description" in content_data:
                    st.markdown(f"**Description:** {content_data['description']}")
                if "stats" in content_data:
                    st.markdown("**Stats:**")
                    stats = content_data["stats"]
                    cols = st.columns(len(stats))
                    for col, (k, v) in zip(cols, stats.items()):
                        col.metric(k.upper(), v)
                if "lore" in content_data:
                    st.markdown(f"*{content_data['lore']}*")

                with st.expander("Raw JSON"):
                    st.json(content_data)

            with tab_validation:
                if item.get("validation_result"):
                    render_validation_result(item["validation_result"])
                else:
                    st.info("No validation results available.")

            with tab_actions:
                if item["status"] in ("draft", "reviewing"):
                    reviewer = st.text_input(
                        "Reviewer name", key=f"rev_{item['id']}"
                    )
                    comment = st.text_area(
                        "Comment", key=f"cmt_{item['id']}"
                    )

                    col_a, col_r, col_regen = st.columns(3)
                    with col_a:
                        if st.button("Approve", key=f"approve_{item['id']}", type="primary"):
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
                    with col_regen:
                        max_attempts = st.number_input(
                            "Max attempts",
                            min_value=1,
                            max_value=5,
                            value=3,
                            key=f"regen_att_{item['id']}",
                        )
                        if st.button("Regenerate", key=f"regen_{item['id']}"):
                            result = api_post(
                                f"/content/{item['id']}/regenerate",
                                {"max_attempts": max_attempts},
                            )
                            if result:
                                st.info(
                                    "Regeneration started. A new version will be "
                                    "created once complete."
                                )

                elif item["status"] == "approved":
                    st.success("This content has been approved.")
                    if item.get("reviewed_by"):
                        st.markdown(f"**Reviewed by:** {item['reviewed_by']}")
                    if item.get("review_comment"):
                        st.markdown(f"**Comment:** {item['review_comment']}")
                elif item["status"] == "rejected":
                    st.error("This content was rejected.")
                    if item.get("reviewed_by"):
                        st.markdown(f"**Rejected by:** {item['reviewed_by']}")
                    if item.get("review_comment"):
                        st.markdown(f"**Reason:** {item['review_comment']}")

                    # Offer regeneration for rejected content
                    st.divider()
                    st.markdown("**Try regenerating with AI feedback:**")
                    max_attempts = st.number_input(
                        "Max attempts",
                        min_value=1,
                        max_value=5,
                        value=3,
                        key=f"regen_rej_att_{item['id']}",
                    )
                    if st.button("Regenerate", key=f"regen_rej_{item['id']}"):
                        result = api_post(
                            f"/content/{item['id']}/regenerate",
                            {"max_attempts": max_attempts},
                        )
                        if result:
                            st.info("Regeneration started.")


def page_version_history() -> None:
    st.header("Version History")

    col1, col2 = st.columns(2)
    with col1:
        content_type = st.selectbox(
            "Content Type",
            ["item", "monster", "quest", "skill"],
            key="hist_type",
        )
    with col2:
        content_id = st.text_input("Content ID", key="hist_id")

    if not content_id:
        st.info("Enter a Content ID to view version history.")
        return

    data = api_get(f"/content/{content_type}/{content_id}/history")
    if data is None or not data:
        st.warning("No versions found.")
        return

    st.subheader(f"Versions of {content_type}/{content_id} ({len(data)} total)")

    for version in data:
        v_num = version.get("version", "?")
        status = version.get("status", "unknown")
        created = version.get("created_at", "")

        status_icons = {
            "draft": "📝",
            "reviewing": "🔍",
            "approved": "✅",
            "rejected": "❌",
        }
        icon = status_icons.get(status, "❓")

        with st.expander(f"{icon} Version {v_num} — {status} ({created})"):
            tab_data, tab_diff = st.tabs(["Data", "Changes"])

            with tab_data:
                st.json(version.get("data", {}))
                if version.get("validation_result"):
                    st.divider()
                    st.markdown("**Validation:**")
                    render_validation_result(version["validation_result"])

            with tab_diff:
                # Show what changed from previous version
                v_idx = data.index(version)
                if v_idx < len(data) - 1:
                    prev = data[v_idx + 1]  # list is newest-first
                    curr_data = version.get("data", {})
                    prev_data = prev.get("data", {})

                    changes = []
                    all_keys = set(curr_data.keys()) | set(prev_data.keys())
                    for key in sorted(all_keys):
                        old_val = prev_data.get(key)
                        new_val = curr_data.get(key)
                        if old_val != new_val:
                            changes.append(
                                f"- **{key}**: `{old_val}` → `{new_val}`"
                            )

                    if changes:
                        st.markdown("\n".join(changes))
                    else:
                        st.info("No data changes from previous version.")
                else:
                    st.info("This is the first version.")

            if version.get("reviewed_by"):
                st.markdown(
                    f"*Reviewed by {version['reviewed_by']}*"
                    + (f" — {version['review_comment']}" if version.get("review_comment") else "")
                )


def page_balance_chart() -> None:
    st.header("Balance Chart — Stat Distributions")

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
            row = {
                "name": content.get("name", content.get("id", "?")),
                "level": content.get("level_requirement", content.get("level", 0)),
                "rarity": content.get("rarity", "unknown"),
            }
            row.update(stats)
            stat_rows.append(row)

    if not stat_rows:
        st.info("No stat data found in items.")
        return

    df = pd.DataFrame(stat_rows)

    # Overview metrics
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    stat_cols = [c for c in numeric_cols if c != "level"]

    if stat_cols:
        cols = st.columns(len(stat_cols))
        for col, stat_name in zip(cols, stat_cols):
            col.metric(
                stat_name.upper(),
                f"avg: {df[stat_name].mean():.0f}",
                f"std: {df[stat_name].std():.1f}",
            )

    st.subheader("Stat Values by Item")
    st.dataframe(df.set_index("name"), use_container_width=True)

    st.subheader("Distribution per Stat")
    if stat_cols:
        st.bar_chart(df.set_index("name")[stat_cols])

    # Level vs Stats scatter
    if "level" in df.columns and stat_cols:
        st.subheader("Level vs Total Stats")
        df["total_stats"] = df[stat_cols].sum(axis=1)
        chart_df = df[["level", "total_stats"]].set_index("level").sort_index()
        st.line_chart(chart_df)

    st.subheader("Summary Statistics")
    if stat_cols:
        st.dataframe(df[stat_cols].describe(), use_container_width=True)


def page_pipeline_runs() -> None:
    st.header("Pipeline Run History")

    data = api_get("/pipeline/history?limit=20")
    if data is None:
        return

    if not data:
        st.info("No pipeline runs yet.")
        return

    for run in data:
        status = run.get("status", "unknown")
        name = run.get("name", "unnamed")
        run_id = run.get("id", "?")
        started = run.get("started_at", "")
        completed = run.get("completed_at")

        status_icons = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
        }
        icon = status_icons.get(status, "❓")

        duration = ""
        if started and completed:
            try:
                t_start = datetime.fromisoformat(started.replace("Z", "+00:00"))
                t_end = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                dur = (t_end - t_start).total_seconds()
                duration = f" ({dur:.1f}s)"
            except (ValueError, TypeError):
                pass

        with st.expander(f"{icon} [{status.upper()}] {name} — {run_id[:8]}...{duration}"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Run ID:** `{run_id}`")
                st.markdown(f"**Status:** {status}")
            with col2:
                st.markdown(f"**Started:** {started}")
                st.markdown(f"**Completed:** {completed or 'N/A'}")

            result = run.get("result")
            if result:
                st.subheader("Result")
                steps = result.get("steps", {})
                if steps:
                    for step_name, step_data in steps.items():
                        step_status = step_data.get("status", "unknown")
                        s_icon = status_icons.get(step_status, "❓")
                        st.markdown(f"{s_icon} **{step_name}** — {step_status}")
                        if step_data.get("error"):
                            st.error(step_data["error"])
                else:
                    st.json(result)

            config = run.get("config")
            if config:
                with st.expander("Pipeline Config"):
                    st.json(config)


def page_run_pipeline() -> None:
    st.header("Run Pipeline")

    default_yaml = """\
name: example_pipeline
steps:
  - name: generate_items
    generator: generate
    params:
      content_type: item
      max_regeneration_attempts: 3
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

    col1, col2 = st.columns(2)
    with col1:
        retry_on_fail = st.number_input(
            "Retry on fail", min_value=0, max_value=5, value=0
        )
    with col2:
        st.markdown("")  # spacer
        st.markdown("")
        run_clicked = st.button("Run Pipeline", type="primary")

    if run_clicked:
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
            status = result.get("status", "unknown")
            if status == "completed":
                st.success(f"Pipeline {status}")
            elif status == "failed":
                st.error(f"Pipeline {status}")
            else:
                st.info(f"Pipeline {status}")
            st.json(result)


# ------------------------------------------------------------------
# Page dispatch
# ------------------------------------------------------------------

if page == "Overview":
    page_overview()
elif page == "Content Review":
    page_content_review()
elif page == "Version History":
    page_version_history()
elif page == "Balance Chart":
    page_balance_chart()
elif page == "Pipeline Runs":
    page_pipeline_runs()
elif page == "Run Pipeline":
    page_run_pipeline()
