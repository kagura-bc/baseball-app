import streamlit as st
import datetime
from config.settings import MY_TEAM, GROUND_LIST, OPPONENTS_LIST, OFFICIAL_GAME_TYPES
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
# 各ページ（View）の読み込み
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis

# --- ページ設定 ---
# 1. 新しいファイル名に変更し、末尾に ?v=2 をつける
# 1. GitHub上の実際のファイル名 (logo-192.png) に合わせる
ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"

# 2. set_page_config の設定
st.set_page_config(
    page_title="KAGUSTA",
    page_icon=ICON_URL,
    layout="wide"
)

# 3. Apple用アイコンの設定
st.markdown(f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True)

load_css() # CSS読み込み

def check_password():
    """簡易ログイン機能"""
    password = st.sidebar.text_input("🔑 合言葉を入力", type="password")
    if password == "kagura":  # ※メンバー共有用パスワード
        return True
    return False

if not check_password():
    st.sidebar.warning("閲覧には合言葉が必要です")
    st.stop() # ここで処理を強制終了

df_batting = load_batting_data()
df_pitching = load_pitching_data()

# --- ページ切り替え ---
st.sidebar.image(ICON_URL, use_container_width=True)
page = st.sidebar.radio("表示", [" 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析"])

# --- 画面表示 ---

if page == " 🏆 チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)

elif page == " 📊 個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)

elif page == " 📈 データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)