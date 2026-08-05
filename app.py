import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
from config.settings import MY_TEAM, OFFICIAL_GAME_TYPES, SPREADSHEET_URL
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css, fmt_player_name
from utils.players import get_active_players
from views import batting, pitching, team_stats, personal_stats, edit_data, analysis, ideal_order, player_management

ICON_URL = "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"

st.set_page_config(
    page_title="KAGUSTA",
    page_icon=ICON_URL,
    layout="wide"
)

st.markdown(f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True)

load_css()

# --- スマホ・タブレットでキーボードが出るのを防ぐ修正CSS ---
st.markdown("""
<style>
    div[data-baseweb="select"] input {
        caret-color: transparent !important;
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

ALL_PLAYERS, PLAYER_NUMBERS = get_active_players()
st.session_state["shared_player_numbers"] = PLAYER_NUMBERS
def local_fmt(name):
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))

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

    # 反映用設定の初期化（未反映・初期状態）
    if "applied_settings" not in st.session_state:
        st.session_state["applied_settings"] = {
            "date": datetime.date.today().strftime("%Y-%m-%d"),
            "scorer": None,
            "match_type": "",
            "ground": "",
            "opp": "",
            "order": ""
        }

    # ⚙️ 試合設定枠
    with st.expander("⚙️ 試合設定", expanded=True):
        url_date = st.query_params.get("date", datetime.date.today().strftime("%Y-%m-%d"))
        try:
            default_date = datetime.datetime.strptime(url_date, "%Y-%m-%d").date()
        except ValueError:
            default_date = datetime.date.today()

        c1, c2, c3 = st.columns(3)
        
        # --- 1列目：試合日 ---
        with c1:
            selected_date = st.date_input("試合日", value=default_date, key="main_selected_date")
            selected_date_str = selected_date.strftime("%Y-%m-%d")

        # --- 初期値のセット ---
        p_list = ALL_PLAYERS
        scorer_key = "scorer_name_ui"
        if scorer_key not in st.session_state:
            st.session_state[scorer_key] = None

        match_options = OFFICIAL_GAME_TYPES + ["練習試合", "その他"]
        match_key = f"main_match_type_{selected_date_str}"
        if match_key not in st.session_state:
            st.session_state[match_key] = None

        ground_options = GROUND_LIST if "その他" in GROUND_LIST else GROUND_LIST + ["その他"]
        ground_key = f"main_selected_ground_{selected_date_str}"
        if ground_key not in st.session_state:
            st.session_state[ground_key] = None

        opp_options = OPPONENTS_LIST if "その他" in OPPONENTS_LIST else OPPONENTS_LIST + ["その他"]
        opp_key = f"main_selected_opp_{selected_date_str}"
        if opp_key not in st.session_state:
            st.session_state[opp_key] = None

        order_list = ["先攻 (表)", "後攻 (裏)"]
        order_key = f"main_kagura_order_{selected_date_str}"
        if order_key not in st.session_state:
            st.session_state[order_key] = None

        # --- 各列へのタッチ式（ポップオーバー）配置 ---
        with c1:
            st.write("")  # 2段目の高さをグラウンド・攻守と揃えるための余白
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>スコアラー</div>", unsafe_allow_html=True)
            saved_scorer = st.session_state.get(scorer_key)
            scorer_label = f"🟢 {local_fmt(saved_scorer)} 🔽" if saved_scorer else "スコアラー選択 🔽"
            with st.popover(scorer_label, use_container_width=True):
                st.markdown("##### 👥 スコアラーを選択")
                st.pills(
                    "スコアラー選択",
                    p_list,
                    format_func=local_fmt,
                    key=scorer_key,
                    label_visibility="collapsed"
                )
            if saved_scorer:
                st.session_state["persistent_scorer"] = saved_scorer

        with c2:
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>試合区分</div>", unsafe_allow_html=True)
            cur_match = st.session_state.get(match_key)
            match_label = f"🟢 {cur_match} 🔽" if cur_match else "試合区分選択 🔽"
            with st.popover(match_label, use_container_width=True):
                st.markdown("##### ⚾ 試合区分を選択")
                st.pills(
                    "試合区分選択",
                    match_options,
                    key=match_key,
                    label_visibility="collapsed"
                )
            
            st.write("")
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>グラウンド</div>", unsafe_allow_html=True)
            cur_ground = st.session_state.get(ground_key)
            ground_label = f"🟢 {cur_ground} 🔽" if cur_ground else "グラウンド選択 🔽"
            with st.popover(ground_label, use_container_width=True):
                st.markdown("##### 🏟️ グラウンドを選択")
                st.pills(
                    "グラウンド選択",
                    ground_options,
                    key=ground_key,
                    label_visibility="collapsed"
                )
            
            if cur_ground == "Other" or cur_ground == "その他":
                ground_name_input = st.text_input("グラウンド名入力", value="その他グラウンド", key=f"main_custom_ground_{selected_date_str}")
            else:
                ground_name_input = cur_ground if cur_ground else ""

        with c3:
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>相手チーム</div>", unsafe_allow_html=True)
            cur_opp = st.session_state.get(opp_key)
            opp_label = f"🟢 {cur_opp} 🔽" if cur_opp else "相手チーム選択 🔽"
            with st.popover(opp_label, use_container_width=True):
                st.markdown("##### 🆚 相手チームを選択")
                st.pills(
                    "相手チーム選択",
                    opp_options,
                    key=opp_key,
                    label_visibility="collapsed"
                )
            
            if cur_opp == "Other" or cur_opp == "その他":
                opp_team_input = st.text_input("相手チーム名入力", value="相手チーム", key=f"main_custom_opp_{selected_date_str}")
            else:
                opp_team_input = cur_opp if cur_opp else ""

            st.write("")
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>攻守</div>", unsafe_allow_html=True)
            cur_order = st.session_state.get(order_key)
            order_label = f"🟢 {cur_order} 🔽" if cur_order else "攻守選択 🔽"
            with st.popover(order_label, use_container_width=True):
                st.markdown("##### 🔄 攻守を選択")
                st.pills(
                    "攻守選択",
                    order_list,
                    key=order_key,
                    label_visibility="collapsed"
                )
            kagura_order_input = cur_order if cur_order else ""

        match_type_input = st.session_state.get(match_key, "")

        st.write("")
        if st.button("⚙️ 試合設定を決定", use_container_width=True):
            st.session_state["applied_settings"] = {
                "date": selected_date_str,
                "scorer": saved_scorer,
                "match_type": match_type_input,
                "ground": ground_name_input,
                "opp": opp_team_input,
                "order": kagura_order_input
            }
            st.success("試合設定を反映しました！")
            st.rerun()

    applied = st.session_state["applied_settings"]
    current_date_str = applied["date"]
    match_type = applied["match_type"]
    ground_name = applied["ground"]
    opp_team = applied["opp"]
    kagura_order = applied["order"]

    st.write("")

    tab_batting, tab_pitching, tab_ideal, tab_edit = st.tabs([" 🏠 打撃成績入力", " 🔥 投手成績入力", " 🎯 理想オーダー作成", " 🔧 データ修正"])
    
    with tab_batting:
        batting.show_batting_page(
            df_batting, df_pitching, 
            current_date_str, match_type, ground_name, opp_team, kagura_order
        )
        
    with tab_pitching:
        pitching.show_pitching_page(
            df_batting, df_pitching, 
            current_date_str, match_type, ground_name, opp_team, kagura_order
        )

    with tab_ideal:
        ideal_order.show_ideal_order_tab(df_batting, df_pitching=df_pitching)
        
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