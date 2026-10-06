import datetime
import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu
from streamlit_gsheets import GSheetsConnection

from config.settings import MY_TEAM, OFFICIAL_GAME_TYPES, SPREADSHEET_URL
from utils.db import load_batting_data, load_pitching_data
from utils.players import get_active_players
from utils.ui import load_css

# 各ページ（View）の読み込み
from views import analysis, personal_stats, team_stats
from views.league_stats import show_league_stats

ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"

st.set_page_config(
    page_title="KAGUSTA",
    page_icon=ICON_URL,
    layout="wide"
)

st.markdown(f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True)

load_css()

# --- スマホ・タブレットでキーボードが出るのを防ぐ修正CSS ---
st.markdown(
    """
<style>
    div[data-baseweb="select"] input {
        caret-color: transparent !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 🔐 閲覧用ログイン機能（マルチチーム対応）
# ==========================================
if "is_logged_in" not in st.session_state:
    st.session_state["is_logged_in"] = False
    st.session_state["my_spreadsheet_url"] = SPREADSHEET_URL
    st.session_state["my_team_name"] = MY_TEAM
    st.session_state["my_team_id"] = None

def show_login_screen():
    _, center, _ = st.columns([1, 10, 1])
    with center:
        st.write("")
        st.write("")
        st.markdown(f"""
<div style="display: flex; justify-content: center; align-items: center; margin-bottom: 20px;">
    <img src="{ICON_URL}" style="width: 350px; height: 350px; object-fit: contain;">
</div>
""", unsafe_allow_html=True)

        with st.form("login_form_viewer"):
            input_team_id = st.text_input("👤 チームID (例: kagura, wish)")
            input_password = st.text_input("🔑 パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True)

            if submitted:
                conn = st.connection("gsheets", type=GSheetsConnection)
                try:
                    df_teams = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録")
                    matched = (
                        df_teams[df_teams["チームID"].astype(str) == input_team_id]
                        if "チームID" in df_teams.columns
                        else pd.DataFrame()
                    )

                    if not matched.empty:
                        target_row = matched.iloc[0]
                        admin_pass = str(target_row.get("管理パスワード", target_row.get("パスワード", "")))
                        viewer_pass = str(target_row.get("閲覧パスワード", ""))

                        if input_password in [admin_pass, viewer_pass] and input_password != "":
                            st.session_state["is_logged_in"] = True
                            st.session_state["my_team_id"] = input_team_id
                            st.session_state["my_team_name"] = target_row.get("チーム名", input_team_id)

                            url_col = next((c for c in ["spreadsheet_url", "スプレッドシートURL", "URL"] if c in df_teams.columns), None)
                            target_url = target_row.get(url_col) if url_col else None
                            if pd.notna(target_url) and str(target_url).strip() != "":
                                st.session_state["my_spreadsheet_url"] = str(target_url).strip()
                            else:
                                st.session_state["my_spreadsheet_url"] = SPREADSHEET_URL
                            st.success(f"{st.session_state['my_team_name']} としてログインしました！")
                            st.rerun()
                        else:
                            st.error("パスワードが違います。")
                    elif input_password == "kagura" and (input_team_id == "kagura" or not input_team_id):
                        st.session_state["is_logged_in"] = True
                        st.session_state["my_team_name"] = MY_TEAM
                        st.session_state["my_spreadsheet_url"] = SPREADSHEET_URL
                        st.success("ログイン成功！")
                        st.rerun()
                    else:
                        st.error("チームIDまたはパスワードが違います。")
                except Exception as e:
                    if input_password == "kagura":
                        st.session_state["is_logged_in"] = True
                        st.session_state["my_team_name"] = MY_TEAM
                        st.session_state["my_spreadsheet_url"] = SPREADSHEET_URL
                        st.rerun()
                    else:
                        st.error(f"ログイン処理中にエラーが発生しました: {e}")

if not st.session_state["is_logged_in"]:
    show_login_screen()
    st.stop()

# ==========================================
# 📊 データ動的読み込み
# ==========================================
MY_DB_URL = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)

df_batting = load_batting_data(spreadsheet_url=MY_DB_URL)
df_pitching = load_pitching_data(spreadsheet_url=MY_DB_URL)

ALL_PLAYERS, PLAYER_NUMBERS = get_active_players(spreadsheet_url=MY_DB_URL)
st.session_state["shared_player_numbers"] = PLAYER_NUMBERS

# ==========================================
# ✨ ヘッダーエリア
# ==========================================
col_title, col_space, col_logout = st.columns([3, 1, 1])
with col_title:
    st.markdown(f"### ⚾️ {st.session_state.get('my_team_name', 'KAGUSTA')}")
with col_logout:
    if st.button("🚪 ログアウト", key="logout_btn", use_container_width=True):
        st.session_state["is_logged_in"] = False
        st.rerun()

# ==========================================
# 🧭 ナビゲーション（横並びタブ）
# ==========================================
page = option_menu(
    menu_title=None,  
    options=["チーム成績", "個人成績", "データ分析", "リーグ戦績"], 
    icons=["trophy", "person-lines-fill", "graph-up", "globe"], 
    default_index=0,  
    orientation="horizontal",  
    styles={
        "container": {"padding": "0!important", "background-color": "#fafafa", "border-radius": "10px", "margin-bottom": "20px"},
        "icon": {"color": "#333", "font-size": "18px"}, 
        "nav-link": {"font-size": "15px", "text-align": "center", "margin":"0px", "--hover-color": "#eee"},
        "nav-link-selected": {"background-color": "#ff4b4b", "color": "white"},
    }
)

# ==========================================
# 💻 メイン画面表示
# ==========================================
if page == "チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)
elif page == "個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)
elif page == "データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)
elif page == "リーグ戦績":
    show_league_stats()