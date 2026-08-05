import streamlit as st
import pandas as pd
from config.settings import MY_TEAM
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

def load_css():
    st.markdown("""
    <style>
    .stSelectbox div[data-baseweb="select"] { font-size: 18px !important; min-height: 40px !important; }
    .stButton button { width: 100%; padding: 0.2rem 0.2rem !important; font-size: 20px !important; }
    [data-testid="stTable"] table { border-collapse: collapse !important; border: 2px solid #000000 !important; }
    [data-testid="stTable"] th, [data-testid="stTable"] td { border: 1px solid #444444 !important; font-size: 20px !important; padding: 10px !important; text-align: center !important; color: #000000 !important; font-weight: bold !important; }
    [data-testid="stTable"] th { background-color: #e0e0e0 !important; border-bottom: 2px solid #000000 !important; }
    [data-testid="stMetricValue"] { font-size: 30px !important; font-weight: bold !important; color: #1e3a8a !important; }
    </style>
    """, unsafe_allow_html=True)

def fmt_player_name(name, player_numbers_dict):
    if not name: return ""
    num = player_numbers_dict.get(name, "")
    return f"{name} ({num})" if num else name

def render_scoreboard(b_df, p_df, date_txt, m_type, g_name, opp_name, is_top_first=True):
    st.markdown(f"### 📅 {date_txt} ({m_type}) &nbsp;&nbsp; 🏟️ {g_name}")
    st.subheader(f"⚾ {MY_TEAM} vs {opp_name}")
    
    # --- 該当する試合（日付・対戦相手・試合種別）のデータだけに厳密に絞り込む ---
    if not b_df.empty and "日付" in b_df.columns:
        b_df = b_df.copy()
        b_df["_date_str"] = pd.to_datetime(b_df["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        b_df = b_df[
            (b_df["_date_str"] == str(date_txt)) & 
            (b_df["対戦相手"].astype(str).str.strip() == str(opp_name).strip()) & 
            (b_df["試合種別"].astype(str).str.strip() == str(m_type).strip())
        ]
        
    if not p_df.empty and "日付" in p_df.columns:
        p_df = p_df.copy()
        p_df["_date_str"] = pd.to_datetime(p_df["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        p_df = p_df[
            (p_df["_date_str"] == str(date_txt)) & 
            (p_df["対戦相手"].astype(str).str.strip() == str(opp_name).strip()) & 
            (p_df["試合種別"].astype(str).str.strip() == str(m_type).strip())
        ]

    # --- 試合終了（勝敗確定）の判定 ---
    is_game_finished = False
    if not p_df.empty and "勝敗" in p_df.columns and p_df["勝敗"].astype(str).str.contains("勝利|敗戦|勝|負").any():
        is_game_finished = True
        
    # --- 最終イニング（データが存在する最大のイニング）を特定 ---
    max_inning_played = 0
    for i in range(1, 10):
        target_innings = [f"{i}回", f"{i}回表", f"{i}回裏"]
        b_has = not b_df.empty and not b_df[b_df["イニング"].isin(target_innings)].empty
        p_has = not p_df.empty and not p_df[p_df["イニング"].isin(target_innings)].empty
        if b_has or p_has:
            max_inning_played = i

    k_inning, opp_inning = [], []
    total_k, total_opp = 0, 0
    
    # 9回まで計算
    for i in range(1, 10):
        target_innings = [f"{i}回", f"{i}回表", f"{i}回裏"]
        
        inn_bat_data = b_df[b_df["イニング"].isin(target_innings)] if not b_df.empty else pd.DataFrame()
        inn_pit_data = p_df[p_df["イニング"].isin(target_innings)] if not p_df.empty else pd.DataFrame()

        if not inn_bat_data.empty and not inn_bat_data[inn_bat_data["結果"] == "✖"].empty:
            k_disp = "✖"
            k_runs = 0
        else:
            k_runs = int(pd.to_numeric(inn_bat_data["得点"], errors='coerce').sum()) if not inn_bat_data.empty else 0
            k_disp = str(k_runs)
        
        if not inn_pit_data.empty and not inn_pit_data[inn_pit_data["結果"] == "✖"].empty:
            opp_disp = "✖"
            opp_runs = 0
        else:
            opp_runs = int(pd.to_numeric(inn_pit_data["失点"], errors='coerce').fillna(0).sum()) if not inn_pit_data.empty else 0
            opp_disp = str(opp_runs)

        k_exists = not inn_bat_data.empty
        opp_exists = not inn_pit_data.empty
        
        total_k += k_runs
        total_opp += opp_runs
        
        # 試合終了時の「✖」追加ロジック (後攻チームの最終イニング)
        if is_game_finished and i == max_inning_played:
            if is_top_first:
                if not opp_exists:
                    opp_disp = "✖"
                    opp_exists = True
                elif total_opp > total_k:
                    opp_disp = f"{opp_disp}✖"
            else:
                if not k_exists:
                    k_disp = "✖"
                    k_exists = True
                elif total_k > total_opp:
                    k_disp = f"{k_disp}✖"

        k_inning.append(k_disp if k_exists else "")
        opp_inning.append(opp_disp if opp_exists else "")

    # --- 安打数 (H) の安全な集計 ---
    hit_list = ["単打", "二塁打", "三塁打", "本塁打", "安打"]
    k_h = b_df[b_df["結果"].isin(hit_list)].shape[0] if not b_df.empty and "結果" in b_df.columns else 0
    
    if not p_df.empty and "被安打" in p_df.columns:
        opp_h = int(pd.to_numeric(p_df["被安打"], errors='coerce').fillna(0).sum())
    else:
        opp_h = p_df[p_df["結果"].isin(hit_list)].shape[0] if not p_df.empty and "結果" in p_df.columns else 0

    # --- 失策数 (E) の安全な集計（爆発防止） ---
    k_e = int(pd.to_numeric(p_df["失策"], errors='coerce').fillna(0).sum()) if not p_df.empty and "失策" in p_df.columns else 0
    opp_e = int(pd.to_numeric(b_df["失策"], errors='coerce').fillna(0).sum()) if not b_df.empty and "失策" in b_df.columns else 0

    if is_top_first:
        names = [MY_TEAM, opp_name]
        scores = [k_inning, opp_inning]
        R = [int(total_k), int(total_opp)]
        H = [int(k_h), int(opp_h)]
        E = [int(k_e), int(opp_e)]
    else:
        names = [opp_name, MY_TEAM]
        scores = [opp_inning, k_inning]
        R = [int(total_opp), int(total_k)]
        H = [int(opp_h), int(k_h)]
        E = [int(opp_e), int(k_e)]

    # HTMLテーブルでレンダリング
    html_content = """
    <style>
    .clickable-scoreboard {
        border-collapse: collapse !important;
        border: 2px solid #000000 !important;
        width: 100%;
        margin-bottom: 20px;
        text-align: center;
        font-family: sans-serif;
    }
    .clickable-scoreboard th, .clickable-scoreboard td {
        border: 1px solid #444444 !important;
        font-size: 20px !important;
        padding: 10px !important;
        color: #000000 !important;
        font-weight: bold !important;
    }
    .clickable-scoreboard th {
        background-color: #e0e0e0 !important;
        border-bottom: 2px solid #000000 !important;
    }
    .clickable-scoreboard th a {
        color: #1e3a8a !important;
        text-decoration: none !important;
    }
    .clickable-scoreboard th a:hover {
        text-decoration: underline !important;
    }
    </style>
    <table class="clickable-scoreboard">
        <thead>
            <tr>
                <th>チーム</th>
    """
    for i in range(1, 10):
        html_content += f"<th><a href='#inning-{i}' title='{i}回詳細へジャンプ'>{i}</a></th>"
    html_content += "<th>R</th><th>H</th><th>E</th></tr></thead><tbody>"

    # 1行目（先攻または相手チーム）
    html_content += f"<tr><td>{names[0]}</td>"
    for i in range(9):
        html_content += f"<td>{scores[0][i]}</td>"
    html_content += f"<td>{R[0]}</td><td>{H[0]}</td><td>{E[0]}</td></tr>"

    # 2行目（後攻または自チーム）
    html_content += f"<tr><td>{names[1]}</td>"
    for i in range(9):
        html_content += f"<td>{scores[1][i]}</td>"
    html_content += f"<td>{R[1]}</td><td>{H[1]}</td><td>{E[1]}</td></tr>"

    html_content += "</tbody></table>"

    st.markdown(html_content, unsafe_allow_html=True)

def show_homerun_effect():
    st.markdown("""
    <style>
    @keyframes rainbow-text {
        0% { color: #ff0000; transform: scale(1); }
        14% { color: #ff7f00; }
        28% { color: #ffff00; transform: scale(1.2); }
        42% { color: #00ff00; }
        57% { color: #0000ff; transform: scale(1.2); }
        71% { color: #4b0082; }
        85% { color: #9400d3; transform: scale(1); }
        100% { color: #ff0000; }
    }
    .homerun-container {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        z-index: 9999;
        text-align: center;
        background-color: rgba(255, 255, 255, 0.8);
        padding: 20px 50px;
        border-radius: 15px;
        box-shadow: 0 0 20px rgba(0,0,0,0.5);
    }
    .homerun-text {
        font-family: 'Arial Black', sans-serif;
        font-size: 80px;
        font-weight: 900;
        animation: rainbow-text 1.5s infinite;
        text-shadow: 3px 3px 0px #000;
    }
    </style>
    <div class="homerun-container">
        <div class="homerun-text">HOMERUN!!</div>
        <div style="font-size: 30px; font-weight: bold;">NICE BATTING!</div>
    </div>
    """, unsafe_allow_html=True)
    st.balloons()

def render_out_indicator_3(count):
    color_on = "#ff2b2b"
    color_off = "#e0e0e0"
    
    html = """
    <div style='font-family:sans-serif; font-weight:bold; display:flex; align-items:center;'>
        <span style='font-size:30px; margin-right:15px;'>OUT</span>
    """
    for i in range(3):
        color = color_on if i < count else color_off
        html += f"<span style='color:{color}; font-size:50px; line-height:1; margin-right:5px;'>●</span>"
    
    html += "</div>"
    return html