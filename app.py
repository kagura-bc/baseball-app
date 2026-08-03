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

    # ⚙️ 試合設定枠（ご指定の3列×2段の配置に修正）
    with st.expander("⚙️ 試合設定 (日付連動・クリックで開閉)", expanded=True):
        url_date = st.query_params.get("date", datetime.date.today().strftime("%Y-%m-%d"))
        try:
            default_date = datetime.datetime.strptime(url_date, "%Y-%m-%d").date()
        except ValueError:
            default_date = datetime.date.today()

        # 3列を作成
        c1, c2, c3 = st.columns(3)
        
        # --- 1列目：試合日 ---
        with c1:
            selected_date = st.date_input("試合日", value=default_date, key="main_selected_date")
            selected_date_str = selected_date.strftime("%Y-%m-%d")

        # 選択された日付に紐づく既存データを検索
        def_match_type = ""
        def_ground_name = ""
        def_opp_team = ""
        def_order = ""
        def_scorer = ""  # 🌟 追加

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
                
                # 🌟 修正: 「チーム記録」行から正確に攻守（先攻・後攻）を取得する
                team_rec_rows = date_matched_df[date_matched_df["選手名"] == "チーム記録"]
                if not team_rec_rows.empty:
                    def_order = str(team_rec_rows.iloc[-1]["位置"])
                else:
                    innings = date_matched_df["イニング"].astype(str).tolist()
                    if any("表" in inn for inn in innings if inn not in ["試合前", "まとめ入力", "試合終了", "nan", ""]):
                        def_order = "先攻 (表)"
                    elif any("裏" in inn for inn in innings if inn not in ["試合前", "まとめ入力", "試合終了", "nan", ""]):
                        def_order = "後攻 (裏)"
                
                # 🌟 過去データからスコアラーを取得（ただしユーザー操作を優先するため、初期値としてのみ使用）
                valid_scorer_rows = date_matched_df[
                    date_matched_df["スコアラー"].astype(str).str.strip().ne("") & 
                    date_matched_df["スコアラー"].astype(str).str.strip().ne("nan") &
                    date_matched_df["スコアラー"].astype(str).str.strip().ne("0")
                ]
                if not valid_scorer_rows.empty:
                    def_scorer = str(valid_scorer_rows.iloc[-1]["スコアラー"])
                
                innings = date_matched_df["イニング"].astype(str).tolist()
                if any("表" in inn for inn in innings if inn not in ["試合前", "まとめ入力", "試合終了", "nan", ""]):
                    def_order = "先攻 (表)"
                elif any("裏" in inn for inn in innings if inn not in ["試合前", "まとめ入力", "試合終了", "nan", ""]):
                    def_order = "後攻 (裏)"

        # --- 各列に上段・下段の要素を配置 ---
        with c1:
            # 1列目・下段：スコアラー
            p_list = ALL_PLAYERS
            
            # 🌟 修正: セッションステートに値がない場合のみ、過去データのスコアラーを初期値としてセット
            if "scorer_name_ui" not in st.session_state or not st.session_state["scorer_name_ui"]:
                if def_scorer and def_scorer in p_list:
                    st.session_state["scorer_name_ui"] = def_scorer
                elif "persistent_scorer" in st.session_state and st.session_state["persistent_scorer"] in p_list:
                    st.session_state["scorer_name_ui"] = st.session_state["persistent_scorer"]

            saved_scorer = st.session_state.get("scorer_name_ui", "")
            scorer_idx = p_list.index(saved_scorer) if saved_scorer in p_list else None
            
            selected_scorer = st.selectbox(
                "スコアラー",
                p_list,
                key="scorer_name_ui",
                format_func=local_fmt,
                index=scorer_idx,
                placeholder="選択してください"
            )
            if selected_scorer:
                st.session_state["persistent_scorer"] = selected_scorer

        with c2:
            # 2列目・上段：試合区分
            match_options = OFFICIAL_GAME_TYPES + ["練習試合", "その他"]
            initial_match = def_match_type if def_match_type in match_options else None
            match_idx = match_options.index(initial_match) if initial_match in match_options else None
            match_type = st.selectbox(
                "試合区分", 
                match_options, 
                index=match_idx,
                placeholder="選択してください",
                key=f"main_match_type_{selected_date_str}"  # 🌟 変更: keyに日付を追加
            )
            if match_type is None: match_type = ""
            
            # 2列目・下段：グラウンド
            # 🌟 修正: 選択肢に「その他」を確実に含める
            ground_options = GROUND_LIST if "その他" in GROUND_LIST else GROUND_LIST + ["その他"]
            initial_ground = def_ground_name if def_ground_name in ground_options else None
            ground_idx = ground_options.index(initial_ground) if initial_ground in ground_options else None
            selected_ground = st.selectbox(
                "グラウンド", 
                ground_options, 
                index=ground_idx,
                placeholder="選択してください",
                key=f"main_selected_ground_{selected_date_str}"  # 🌟 変更: keyに日付を追加
            )
            
            if selected_ground == "その他":
                ground_name = st.text_input("グラウンド名入力", value=def_ground_name if def_ground_name not in ground_options and def_ground_name else "その他グラウンド", key=f"main_custom_ground_{selected_date_str}")
            else:
                ground_name = selected_ground if selected_ground else ""

        with c3:
            # 3列目・上段：相手チーム
            # 🌟 修正: 選択肢に「その他」を確実に含める
            opp_options = OPPONENTS_LIST if "その他" in OPPONENTS_LIST else OPPONENTS_LIST + ["その他"]
            initial_opp = def_opp_team if def_opp_team in opp_options else None
            opp_idx = opp_options.index(initial_opp) if initial_opp in opp_options else None
            selected_opp = st.selectbox(
                "相手チーム", 
                opp_options, 
                index=opp_idx,
                placeholder="選択してください",
                key=f"main_selected_opp_{selected_date_str}"  # 🌟 変更: keyに日付を追加
            )
            
            if selected_opp == "その他":
                opp_team = st.text_input("相手チーム名入力", value=def_opp_team if def_opp_team not in opp_options and def_opp_team else "相手チーム", key=f"main_custom_opp_{selected_date_str}")
            else:
                opp_team = selected_opp if selected_opp else ""

            # 3列目・下段：攻守
            order_list = ["先攻 (表)", "後攻 (裏)"]
            initial_order = def_order if def_order in order_list else None
            order_idx = order_list.index(initial_order) if initial_order in order_list else None
            kagura_order = st.selectbox(
                "攻守", 
                order_list, 
                index=order_idx,
                placeholder="選択してください",
                key=f"main_kagura_order_{selected_date_str}"  # 🌟 変更: keyに日付を追加
            )
            if kagura_order is None: kagura_order = ""

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