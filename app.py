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

# ==========================================
# 📊 データ読み込み
# ==========================================
df_batting = load_batting_data()
df_pitching = load_pitching_data()

# --- ヘルパー関数 (URLクエリパラメータとの同期用) ---
def safe_index(lst, val):
    try:
        return lst.index(val)
    except ValueError:
        return 0

# ==========================================
# 🧭 ナビゲーション（サイドバー）
# ==========================================
st.sidebar.markdown("### ⚾️ KAGUSTA")

# サイドバーにはメニューのみを配置（試合設定は削除）
page = st.sidebar.radio(
    "メニュー", 
    [" 📝 試合データ入力", " 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析", " 🔧 データ修正"]
)

# ==========================================
# 💻 メイン画面の表示制御
# ==========================================
if page == " 📝 試合データ入力":
    
    st.markdown("### 📝 試合データ入力")
    
    # 🌟 試合設定をメイン画面上部にプルダウン(横並び3列)で配置
    with st.container(border=True):
        st.markdown("##### ⚙️ 試合設定")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            # 1. 試合区分
            url_match = st.query_params.get("match", OFFICIAL_GAME_TYPES[0])
            match_options = OFFICIAL_GAME_TYPES + ["練習試合", "その他"]
            match_type = st.selectbox(
                "試合区分", 
                match_options, 
                index=safe_index(match_options, url_match),
                key="main_match_type"
            )
            
            # 2. 攻守
            order_list = ["先攻 (表)", "後攻 (裏)"]
            url_order = st.query_params.get("order", order_list[0])
            kagura_order = st.selectbox(
                "攻守", 
                order_list, 
                index=safe_index(order_list, url_order),
                key="main_kagura_order"
            )
            
        with c2:
            # 3. 試合日
            url_date = st.query_params.get("date", datetime.date.today().strftime("%Y-%m-%d"))
            try:
                default_date = datetime.datetime.strptime(url_date, "%Y-%m-%d").date()
            except ValueError:
                default_date = datetime.date.today()
            selected_date = st.date_input("試合日", value=default_date, key="main_selected_date")
            selected_date_str = selected_date.strftime("%Y-%m-%d")
            
        with c3:
            # 4. グラウンド
            url_ground = st.query_params.get("ground", GROUND_LIST[0])
            selected_ground = st.selectbox(
                "グラウンド", 
                GROUND_LIST, 
                index=safe_index(GROUND_LIST, url_ground),
                key="main_selected_ground"
            )
            ground_name = st.text_input("グラウンド名入力", value="その他グラウンド", key="main_custom_ground") if selected_ground == "その他" else selected_ground
            
            # 5. 相手チーム
            url_opp = st.query_params.get("opp", OPPONENTS_LIST[0])
            selected_opp = st.selectbox(
                "相手チーム", 
                OPPONENTS_LIST, 
                index=safe_index(OPPONENTS_LIST, url_opp),
                key="main_selected_opp"
            )
            opp_team = st.text_input("相手チーム名入力", value="相手チーム", key="main_custom_opp") if selected_opp == "その他" else selected_opp

    st.write("") # 少し余白を空ける

    # 🌟 画面上部で打撃と投手を切り替えるタブ
    tab_batting, tab_pitching = st.tabs([" 🏠 打撃成績入力", " 🔥 投手成績入力"])
    
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

elif page == " 🏆 チーム成績":
    team_stats.show_team_stats(df_batting, df_pitching)

elif page == " 📊 個人成績":
    personal_stats.show_personal_stats(df_batting, df_pitching)

elif page == " 📈 データ分析":
    analysis.show_analysis_page(df_batting, df_pitching)

elif page == " 🔧 データ修正":
    edit_data.show_edit_page(df_batting, df_pitching)