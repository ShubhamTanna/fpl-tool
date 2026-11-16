"""FPL Tool - Shubham's personal FPL app. Run from the project root:

    .venv/bin/streamlit run app/streamlit_app.py
"""
import streamlit as st

import common

st.set_page_config(page_title="FPL Tool", layout="wide")
common.apply_theme()

pages = [
    st.Page("app_pages/my_team.py", title="My team", url_path="my-team", default=True),
    st.Page("app_pages/drafts.py", title="Drafts", url_path="drafts"),
    st.Page("app_pages/player.py", title="Player", url_path="player"),
    st.Page("app_pages/boosts.py", title="Boosts", url_path="boosts"),
    st.Page("app_pages/scout.py", title="Scout", url_path="scout"),
    st.Page("app_pages/projections.py", title="Projections", url_path="projections"),
    st.Page("app_pages/model_lab.py", title="Model lab", url_path="model-lab"),
]
nav = st.navigation(pages, position="top")
nav.run()
