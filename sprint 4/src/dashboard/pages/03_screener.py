import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st  # noqa: E402

from src.dashboard.utils import db, screen  # noqa: E402
from src.screener.engine import load_config  # noqa: E402

st.title("Investment Screener")
cfg = load_config()
snap = db.get_snapshot()

# ── state ────────────────────────────────────────────────────────────────────
for k, v in screen.slider_defaults().items():
    st.session_state.setdefault(f"sl_{k}", v)
st.session_state.setdefault("extras", [])
st.session_state.setdefault("active_preset", None)


def _apply_preset(preset_key: str):
    vals, extras = screen.preset_to_state(preset_key, cfg)
    for k, v in vals.items():
        st.session_state[f"sl_{k}"] = v
    st.session_state["extras"] = extras
    st.session_state["active_preset"] = preset_key


def _manual_change():
    st.session_state["extras"] = []          # moving a slider detaches from the preset's extra rules
    st.session_state["active_preset"] = None


def _reset():
    for k, v in screen.slider_defaults().items():
        st.session_state[f"sl_{k}"] = v
    st.session_state["extras"], st.session_state["active_preset"] = [], None


# ── presets ──────────────────────────────────────────────────────────────────
cols = st.columns(len(screen.PRESET_BUTTONS) + 1)
for col, (label, key) in zip(cols, screen.PRESET_BUTTONS):
    col.button(label, key=f"btn_{key}", on_click=_apply_preset, args=(key,), width="stretch",
               type="primary" if st.session_state["active_preset"] == key else "secondary")
cols[-1].button("Reset", on_click=_reset, width="stretch")

# ── sliders (sidebar) ────────────────────────────────────────────────────────
st.sidebar.header("Filters")
st.sidebar.caption("A filter is applied only when its slider is moved off the 'no filter' end.")
values = {}
for s in screen.SLIDERS:
    values[s["key"]] = st.sidebar.slider(s["label"], min_value=s["lo"], max_value=s["hi"], step=s["step"],
                                         format=s["fmt"], key=f"sl_{s['key']}", on_change=_manual_change)

res, filters = screen.run(snap, values, st.session_state["extras"], cfg)
view = screen.view_frame(res, filters)

if st.session_state["active_preset"]:
    p = cfg["presets"][st.session_state["active_preset"]]
    st.info(f"**{p['label']}** — {p['description']}.")
if st.session_state["extras"]:
    txt = ", ".join(screen.LABELS.get(f["metric"], f["metric"]) + (f" {f['op']} {f['value']}" if "value" in f else " = yes")
                    for f in st.session_state["extras"])
    st.caption(f"Extra preset rules not on the sliders: {txt}")
if any(f["metric"] in ("de", "de_declining") for f in filters):
    st.caption("D/E filters skip Financials (banks, NBFCs, insurers), where leverage is not comparable.")

st.subheader(f"{len(view)} companies match your filters")
st.dataframe(view, hide_index=True, width="stretch")
st.download_button("Download CSV", screen.to_csv_bytes(view), file_name="screener_results.csv",
                   mime="text/csv", disabled=view.empty)
