import streamlit as st
import datetime
from config.settings import MY_TEAM, GROUND_LIST, OPPONENTS_LIST, OFFICIAL_GAME_TYPES
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
# 各ページ（View）の読み込み
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis

# GitHubのRaw URL（ご自身のリポジトリのものに書き換えてください）
# 例: "https://raw.githubusercontent.com/your-name/your-repo/main/static/icon-192.png"
# --- app.py の修正箇所 ---

# 1. 新しいファイル名に変更し、末尾に ?v=2 をつける
ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/kagura-logo.png?v=2"

# 2. set_page_config の page_icon を URL にする
st.set_page_config(
    page_title="KAGURA 成績管理",
    page_icon=ICON_URL,
    layout="wide"
)

# 3. HTMLインジェクションを「上書き」ではなく「新規追加」の形式にする
st.markdown(
    f"""
    <head>
        <link rel="apple-touch-icon" sizes="192x192" href="{ICON_URL}">
        <link rel="icon" type="image/png" sizes="192x192" href="{ICON_URL}">
        <link rel="shortcut icon" href="{ICON_URL}">
    </head>
    """,
    unsafe_allow_html=True
)

load_css() # CSS読み込み

def check_password():
    """簡易ログイン機能"""
    password = st.sidebar.text_input("🔑 合言葉を入力", type="password")
    if password == "kagura":  # ※入力用パスワード
        return True
    return False

if not check_password():
    st.sidebar.error("ログインが必要です")
    st.stop() # ここで処理を強制終了

# --- データ読み込み ---
df_batting = load_batting_data()
df_pitching = load_pitching_data()

# --- サイドバー設定 (共通) ---
st.sidebar.image(ICON_URL, use_container_width=True)
st.sidebar.markdown("<h2 style='text-align: center;'>KAGURA</h2>", unsafe_allow_html=True)
st.sidebar.divider() # 区切り線を入れてスッキリさせる
st.sidebar.header("⚙️ 試合設定")

match_category = st.sidebar.radio("試合区分", ["公式戦", "練習試合", "その他"], horizontal=True)
if match_category == "公式戦":
    match_type = st.sidebar.selectbox("大会名を選択", ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯"])
else:
    match_type = match_category

game_date = st.sidebar.date_input("試合日", datetime.date.today())
selected_date_str = game_date.strftime('%Y-%m-%d')

selected_ground_base = st.sidebar.selectbox("グラウンド", GROUND_LIST)
ground_name = st.sidebar.text_input("グラウンド名入力", value="グラウンド") if selected_ground_base == "その他" else selected_ground_base

selected_opp = st.sidebar.selectbox("相手チーム", OPPONENTS_LIST)
opp_team = st.sidebar.text_input("相手名", value="相手チーム") if selected_opp == "その他" else selected_opp

kagura_order = st.sidebar.radio(f"攻守", ["先攻 (表)", "後攻 (裏)"], horizontal=True)

# --- ページ切り替え ---
page = st.sidebar.radio("表示", [" 🏠 打撃成績入力", " 🔥 投手成績入力", " 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析", " 🔧 データ修正"])

# --- 画面表示 ---
if page == " 🏠 打撃成績入力":
    batting.show_batting_page(
        df_batting, df_pitching, 
        selected_date_str, match_type, ground_name, opp_team, kagura_order
    )

elif page == " 🔥 投手成績入力":
    pitching.show_pitching_page(
        df_batting, df_pitching,
        selected_date_str, match_type, ground_name, opp_team, kagura_order
    )

elif page == " 🏆 チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)

elif page == " 📊 個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)

elif page == " 📈 データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)

elif page == " 🔧 データ修正":
    edit_data.show_edit_page(df_batting, df_pitching)