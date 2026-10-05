import streamlit as st
import datetime
from config.settings import MY_TEAM, OFFICIAL_GAME_TYPES
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
from streamlit_option_menu import option_menu

# 各ページ（View）の読み込み
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis
from views.league_stats import show_league_stats

ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"

st.set_page_config(
    page_title="KAGUSTA",
    page_icon=ICON_URL,
    layout="wide"
)

st.markdown(f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True)

load_css()

# ==========================================
# 🔐 ログイン機能の実装
# ==========================================
if "is_logged_in" not in st.session_state:
    st.session_state["is_logged_in"] = False

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

        with st.form("login_form_v3"):
            password = st.text_input("🔑 パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True)
            if submitted:
                if password == "kagura":
                    st.session_state["is_logged_in"] = True
                    st.success("ログイン成功！")
                    st.rerun()
                else:
                    st.error("パスワードが違います")

if not st.session_state["is_logged_in"]:
    show_login_screen()
    st.stop()

# --- データ読み込み ---
df_batting = load_batting_data()
df_pitching = load_pitching_data()

# ==========================================
# ✨ ヘッダーエリア
# ==========================================
col_logo, col_space, col_logout = st.columns([1, 2, 1])
with col_logo:
    st.image(ICON_URL, width=350) 
with col_logout:
    st.write("") 
    if st.button("ログアウト", key="logout_btn", use_container_width=True):
        st.session_state["is_logged_in"] = False
        st.rerun()

# ==========================================
# ページ切り替えメニュー（横並びタブ）
# ==========================================
page = option_menu(
    menu_title=None,  
    options=["チーム成績", "個人成績", "データ分析", "🌐 リーグ戦績"], 
    icons=["trophy", "person-lines-fill", "graph-up", "globe"], 
    default_index=0,  
    orientation="horizontal",  
    styles={
        "container": {"padding": "0!important", "background-color": "#fafafa", "border-radius": "10px"},
        "icon": {"color": "black", "font-size": "20px"}, 
        "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#eee"},
        "nav-link-selected": {"background-color": "#ff4b4b", "color": "white"},
    }
)

# --- 画面表示 ---
if page == "チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)
elif page == "個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)
elif page == "データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)
elif page == "リーグ戦績":
    show_league_stats()