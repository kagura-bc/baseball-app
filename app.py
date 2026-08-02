import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
from config.settings import MY_TEAM, OFFICIAL_GAME_TYPES, SPREADSHEET_URL
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis, ideal_order, player_management

ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"

st.set_page_config(
    page_title="KAGUSTA",
    page_icon=ICON_URL,
    layout="wide"
)

st.markdown(f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True)

load_css()

# --- スマホ・タブレットでセレクトボックスをタッチした時にキーボードが出るのを防ぐ共通CSS ---
st.markdown("""
<style>
    div[data-baseweb="select"] input {
        pointer-events: none !important;
    }
</style>
""", unsafe_allow_html=True)

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

# ==========================================
# 📊 データ読み込み
# ==========================================
df_batting = load_batting_data()
df_pitching = load_pitching_data()

@st.cache_data(ttl=60)
def get_cached_grounds():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_ground = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="グラウンド登録", ttl=0)
        return df_ground["グラウンド名"].dropna().tolist() if "グラウンド名" in df_ground.columns else ["その他"]
    except Exception:
        return ["その他"]

@st.cache_data(ttl=60)
def get_cached_opponents():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_opp = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録", ttl=0)
        return df_opp["チーム名"].dropna().tolist() if "チーム名" in df_opp.columns else ["その他"]
    except Exception:
        return ["その他"]

GROUND_LIST = get_cached_grounds()
OPPONENTS_LIST = get_cached_opponents()

def safe_index(lst, val):
    try:
        return lst.index(val)
    except ValueError:
        return 0

# ==========================================
# 🧭 ナビゲーション（サイドバー）
# ==========================================
st.sidebar.markdown("### ⚾️ KAGUSTA")

page = st.sidebar.radio(
    "メニュー", 
    [" 📝 試合データ入力", " 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析", " 🔧 データ修正", " 👥 選手管理"]
)

# ==========================================
# 💻 メイン画面の表示制御
# ==========================================
if page == " 📝 試合データ入力":
    
    st.markdown("### 📝 試合データ入力")
    
    # 🌟 日付を最優先で取得（デフォルトは今日）
    url_date = st.query_params.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    try:
        default_date = datetime.datetime.strptime(url_date, "%Y-%m-%d").date()
    except ValueError:
        default_date = datetime.date.today()
    
    # 先に日付入力ボックスを配置
    selected_date = st.date_input("試合日 (日付を選択すると設定が連動します)", value=default_date, key="main_selected_date")
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    # 🌟 選択された日付に紐づく既存データをスプレッドシートから自動検索
    def_match_type = ""
    def_ground_name = ""
    def_opp_team = ""
    def_order = ""

    if not df_batting.empty:
        date_matched_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
        if not date_matched_df.empty:
            first_row = date_matched_df.iloc[0]
            if pd.notna(first_row.get("試合種別")):
                def_match_type = str(first_row["試合種別"])
            if pd.notna(first_row.get("グラウンド")):
                def_ground_name = str(first_row["グラウンド"])
            if pd.notna(first_row.get("対戦相手")):
                def_opp_team = str(first_row["対戦相手"])
            
            innings = date_matched_df["イニング"].astype(str).tolist()
            if any("表" in inn for inn in innings if inn not in ["試合前", "まとめ入力", "試合終了", "nan", ""]):
                def_order = "先攻 (表)"
            elif any("裏" in inn for inn in innings if inn not in ["試合前", "まとめ入力", "試合終了", "nan", ""]):
                def_order = "後攻 (裏)"

    with st.expander("⚙️ 試合設定 (日付連動・クリックで開閉)", expanded=True):
        c1, c2, c3 = st.columns(3)
        
        with c1:
            match_options = [""] + OFFICIAL_GAME_TYPES + ["練習試合", "その他"]
            initial_match = def_match_type if def_match_type in match_options else st.query_params.get("match", "")
            match_type = st.selectbox(
                "試合区分", 
                match_options, 
                index=safe_index(match_options, initial_match),
                key="main_match_type"
            )
            
            order_list = ["", "先攻 (表)", "後攻 (裏)"]
            initial_order = def_order if def_order in order_list else st.query_params.get("order", "")
            kagura_order = st.selectbox(
                "攻守", 
                order_list, 
                index=safe_index(order_list, initial_order),
                key="main_kagura_order"
            )
            
        with c2:
            st.info(f"📅 選択中の日付: **{selected_date_str}**\n\n※日付を変更すると、過去に登録がある場合は設定が自動で呼び出されます。")
            
        with c3:
            ground_options = [""] + GROUND_LIST
            initial_ground = def_ground_name if def_ground_name in ground_options else ("その他" if def_ground_name else st.query_params.get("ground", ""))
            selected_ground = st.selectbox(
                "グラウンド", 
                ground_options, 
                index=safe_index(ground_options, initial_ground),
                key="main_selected_ground"
            )
            ground_name = st.text_input("グラウンド名入力", value=def_ground_name if def_ground_name not in ground_options and def_ground_name else "その他グラウンド", key="main_custom_ground") if selected_ground == "その他" else selected_ground
            
            opp_options = [""] + OPPONENTS_LIST
            initial_opp = def_opp_team if def_opp_team in opp_options else ("その他" if def_opp_team else st.query_params.get("opp", ""))
            selected_opp = st.selectbox(
                "相手チーム", 
                opp_options, 
                index=safe_index(opp_options, initial_opp),
                key="main_selected_opp"
            )
            opp_team = st.text_input("相手チーム名入力", value=def_opp_team if def_opp_team not in opp_options and def_opp_team else "相手チーム", key="main_custom_opp") if selected_opp == "その他" else selected_opp

    st.write("")

    tab_batting, tab_pitching, tab_ideal, tab_edit = st.tabs([" 🏠 打撃成績入力", " 🔥 投手成績入力", " 🎯 理想オーダー作成", " 🔧 データ修正"])
    
    with tab_batting:
        batting.show_batting_page(
            df_batting, df_pitching, 
            selected_date_str, match_type, ground_name, opp_team, kagura_order
        )
        
    with tab_pitching:
        pitching.show_pitching_page(
            df_batting, df_pitching, 
            selected_date_str, match_type, ground_name, opp_team, kagura_order
        )

    with tab_ideal:
        ideal_order.show_ideal_order_tab(df_batting)
        
    with tab_edit:
        edit_data.show_edit_page(df_batting, df_pitching)

elif page == " 🏆 チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)

elif page == " 📊 個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)

elif page == " 📈 データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)

elif page == " 🔧 データ修正":
    edit_data.show_edit_page(df_batting, df_pitching)

elif page == " 👥 選手管理":
    player_management.show_player_management()