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
    _, center, _ = st.columns([1, 10, 1])
    with center:
        st.write("")
        st.write("")
        # ロゴのみを中央配置
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

# --- ログイン判定 ---
if not st.session_state["is_logged_in"]:
    # 未ログイン時はログイン画面を表示して終了
    show_login_screen()
    st.stop()

# ==========================================
# 📱 ここから下がログイン後のメインアプリ
# ==========================================

# 🧪 テストモードの設定（データ読み込みに必要）
is_test_mode = st.sidebar.toggle("🧪 テストモード", value=False)
if is_test_mode:
    st.sidebar.warning("現在テストモードです。")

# --- ★ここが抜けていました：データの読み込み---
df_batting = load_batting_data(is_test_mode=is_test_mode)
df_pitching = load_pitching_data(is_test_mode=is_test_mode)

st.sidebar.header("⚙️ 試合設定")

# 試合区分・大会名の選択
match_category = st.sidebar.radio("試合区分", ["公式戦", "練習試合", "その他"], horizontal=True)
if match_category == "公式戦":
    match_type = st.sidebar.selectbox("大会名を選択", OFFICIAL_GAME_TYPES)
else:
    match_type = match_category

# ==========================================
# 🔄 URLパラメータ保存用関数とサイドバー設定
# ==========================================
def sync_sidebar_state():
    st.query_params["game_date"] = str(st.session_state.app_date)
    st.query_params["ground"] = st.session_state.app_ground
    st.query_params["opp"] = st.session_state.app_opp
    st.query_params["order"] = st.session_state.app_order

def safe_index(lst, val):
    return lst.index(val) if val in lst else 0

# --- 1. 試合日 ---
url_date = st.query_params.get("game_date", str(datetime.date.today()))
try:
    default_date = datetime.datetime.strptime(url_date, "%Y-%m-%d").date()
except ValueError:
    default_date = datetime.date.today()

game_date = st.sidebar.date_input("試合日", value=default_date, key="app_date", on_change=sync_sidebar_state)
selected_date_str = game_date.strftime('%Y-%m-%d')

# --- 2. グラウンド ---
url_ground = st.query_params.get("ground", GROUND_LIST[0])
selected_ground_base = st.sidebar.selectbox("グラウンド", GROUND_LIST, index=safe_index(GROUND_LIST, url_ground), key="app_ground", on_change=sync_sidebar_state)
ground_name = st.sidebar.text_input("グラウンド名入力", value="グラウンド") if selected_ground_base == "その他" else selected_ground_base

# --- 3. 相手チーム ---
url_opp = st.query_params.get("opp", OPPONENTS_LIST[0])
selected_opp = st.sidebar.selectbox("相手チーム", OPPONENTS_LIST, index=safe_index(OPPONENTS_LIST, url_opp), key="app_opp", on_change=sync_sidebar_state)
opp_team = st.sidebar.text_input("相手名", value="相手チーム") if selected_opp == "その他" else selected_opp

# --- 4. 攻守 ---
order_list = ["先攻 (表)", "後攻 (裏)"]
url_order = st.query_params.get("order", order_list[0])
kagura_order = st.sidebar.radio("攻守", order_list, index=safe_index(order_list, url_order), horizontal=True, key="app_order", on_change=sync_sidebar_state)

# --- ページ切り替え ---
page = st.sidebar.radio("表示", [" 🏠 打撃成績入力", " 🔥 投手成績入力", " 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析", " 🔧 データ修正"])

# --- 画面表示 ---
if page == " 🏠 打撃成績入力":
    batting.show_batting_page(
        df_batting, df_pitching, 
        selected_date_str, match_type, ground_name, opp_team, kagura_order,
        is_test_mode=is_test_mode
    )
elif page == " 🔥 投手成績入力":
    pitching.show_pitching_page(
        df_batting, df_pitching,
        selected_date_str, match_type, ground_name, opp_team, kagura_order,
        is_test_mode=is_test_mode
    )
elif page == " 🏆 チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)
elif page == " 📊 個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)
elif page == " 📈 データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)
elif page == " 🔧 データ修正":
    edit_data.show_edit_page(df_batting, df_pitching, is_test_mode=is_test_mode)