import streamlit as st
import datetime
from config.settings import MY_TEAM, GROUND_LIST, OPPONENTS_LIST, OFFICIAL_GAME_TYPES
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
# 各ページ（View）の読み込み
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis
# --- ページ設定 ---
st.set_page_config(page_title=f"{MY_TEAM} スコア管理システム", layout="wide")
load_css() # CSS読み込み

df_batting = load_batting_data()
df_pitching = load_pitching_data()

# --- ページ切り替え ---
page = st.sidebar.radio("表示", [" 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析"])

# --- 画面表示 ---

if page == " 🏆 チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)

elif page == " 📊 個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)

elif page == " 📈 データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)