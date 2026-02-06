import streamlit as st
import datetime
from config.settings import MY_TEAM, GROUND_LIST, OPPONENTS_LIST, OFFICIAL_GAME_TYPES
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
# 各ページ（View）の読み込み
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis

# 1. GitHub上の実際のファイル名 (logo-192.png) に合わせる
ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"

# 2. set_page_config の設定 (必ず一番最初に記述)
st.set_page_config(
    page_title="KAGUSTA",
    page_icon=ICON_URL,
    layout="wide"
)

# 3. Apple用アイコンの設定
st.markdown(f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True)

load_css() # CSS読み込み

# ==========================================
# 🔐 ログイン機能の実装
# ==========================================

# セッションステートの初期化（ログイン状態を管理）
if "is_logged_in" not in st.session_state:
    st.session_state["is_logged_in"] = False

def show_login_screen():
    """メイン画面を使った大きなログイン画面"""
    # スマホで見やすいよう、左右に少し余白を設けて中央寄せにする
    _, center, _ = st.columns([1, 8, 1])

    with center:
        st.write("") 
        st.write("") 
        
        # マスコット画像（アイコン）を大きく表示
        st.image(ICON_URL, width=180)
        
        st.markdown("### 選手専用ページ")
        st.info("合言葉を入力して入場してください")

        # フォームを使用（スマホで「Enter」キー送信ができるようになります）
        with st.form("login_form"):
            password = st.text_input("🔑 合言葉", type="password")
            submitted = st.form_submit_button("入場する", use_container_width=True)
            
            if submitted:
                if password == "kagura":  # ※パスワード判定
                    st.session_state["is_logged_in"] = True
                    st.success("ログイン成功！")
                    st.rerun()  # 画面をリロードしてメインアプリへ
                else:
                    st.error("合言葉が違います")

# --- ログイン判定 ---
if not st.session_state["is_logged_in"]:
    # 未ログイン時はログイン画面を表示して終了
    show_login_screen()
    st.stop()

# ==========================================
# 📱 ここから下がログイン後のメインアプリ
# ==========================================

# --- データ読み込み ---
df_batting = load_batting_data()
df_pitching = load_pitching_data()

# --- サイドバー設定 (共通) ---
st.sidebar.image(ICON_URL, use_container_width=True)

# ログアウトボタン（任意で追加）
if st.sidebar.button("ログアウト", key="logout_btn"):
    st.session_state["is_logged_in"] = False
    st.rerun()

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