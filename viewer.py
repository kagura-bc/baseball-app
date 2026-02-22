import streamlit as st
import datetime
from config.settings import MY_TEAM, GROUND_LIST, OPPONENTS_LIST, OFFICIAL_GAME_TYPES
from utils.db import load_batting_data, load_pitching_data
from utils.ui import load_css
from streamlit_option_menu import option_menu

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
    """メイン画面を使った大きなログイン画面（吹き出し付き）"""
    
    _, center, _ = st.columns([1, 10, 1])

    with center:
        st.write("")
        st.write("")
        
        st.markdown(f"""
<div style="display: flex; align-items: center; justify-content: center; margin-bottom: 20px;">
    <img src="{ICON_URL}" style="width: 100px; height: 100px; object-fit: contain; margin-right: 15px;">
    <div style="
        position: relative;
        background: #ffffff;
        border: 3px solid #333;
        border-radius: 15px;
        padding: 15px;
        color: #333;
        font-weight: bold;
        box-shadow: 4px 4px 0px rgba(0,0,0,0.2);
        max-width: 250px;
    ">
        <div style="
            position: absolute;
            left: -16px;
            top: 25px;
            width: 0;
            height: 0;
            border-top: 8px solid transparent;
            border-bottom: 8px solid transparent; 
            border-right: 16px solid #333;
        "></div>
        ようこそ KAGUSTA へ！<br>
        おーい！合言葉を忘れちまったか？
    </div>
</div>
""", unsafe_allow_html=True)

        with st.form("login_form_v3"):
            password = st.text_input("🔑 合言葉", type="password")
            submitted = st.form_submit_button("入場する", use_container_width=True)
            
            if submitted:
                if password == "kagura":
                    st.session_state["is_logged_in"] = True
                    st.success("ログイン成功！")
                    st.rerun()
                else:
                    st.error("合言葉が違います")

# --- ログイン判定 ---
if not st.session_state["is_logged_in"]:
    show_login_screen()
    st.stop()

# --- データ読み込み ---
df_batting = load_batting_data()
df_pitching = load_pitching_data()

# ==========================================
# ✨ ヘッダーエリア（サイドバーの代わり）
# ==========================================
# 画面を3つのカラムに分けて、左にロゴ、右にログアウトボタンを配置します
col_logo, col_space, col_logout = st.columns([1, 2, 1])

with col_logo:
    # PCでもスマホでも丁度いいサイズ（幅80px）に指定
    st.image(ICON_URL, width=150) 

with col_logout:
    st.write("") # ボタンの縦位置をロゴと合わせるための微調整
    if st.button("ログアウト", key="logout_btn", use_container_width=True):
        st.session_state["is_logged_in"] = False
        st.rerun()

# ==========================================
# ページ切り替えメニュー（横並びタブ）
# ==========================================
page = option_menu(
    menu_title=None,  
    options=["チーム成績", "個人成績", "データ分析"], 
    icons=["trophy", "person-lines-fill", "graph-up"], 
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