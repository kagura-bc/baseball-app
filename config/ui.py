import streamlit as st
import pandas as pd
from config.settings import MY_TEAM

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
    
    k_inning, opp_inning = [], []
    total_k, total_opp = 0, 0
    
    # 9回まで計算
    for i in range(1, 10):
        inn = f"{i}回"
        
        inn_bat_data = b_df[b_df["イニング"] == inn]
        inn_pit_data = p_df[p_df["イニング"] == inn]

        # データ内に「結果: ✖」が含まれていれば、表示を "✖" にする 
        if not inn_bat_data[inn_bat_data["結果"] == "✖"].empty:
            k_disp = "✖"
            k_runs = 0
        else:
            k_runs = int(pd.to_numeric(inn_bat_data["得点"], errors='coerce').sum())
            k_disp = str(k_runs)
        
        if not inn_pit_data[inn_pit_data["結果"] == "✖"].empty:
            opp_disp = "✖"
            opp_runs = 0
        else:
            opp_runs = int(inn_pit_data["失点"].sum())
            opp_disp = str(opp_runs)

        # データが存在するイニングだけ数字を表示、なければ空文字
        k_exists = not inn_bat_data.empty
        opp_exists = not inn_pit_data.empty
        
        # 計算した k_disp / opp_disp を使う 
        k_inning.append(k_disp if k_exists else "")
        opp_inning.append(opp_disp if opp_exists else "")
        
        total_k += k_runs
        total_opp += opp_runs

    hit_list = ["単打", "二塁打", "三塁打", "本塁打", "安打"]
    k_h = b_df[b_df["結果"].isin(hit_list)].shape[0]
    k_e = p_df[p_df["結果"] == "失策"].shape[0]
    opp_h = p_df[p_df["結果"].isin(hit_list)].shape[0]
    opp_e = b_df[b_df["結果"] == "失策"].shape[0]

    # KAGURAが先攻か後攻かで表示順を入れ替え
    # my_team_fixed を MY_TEAM に変更
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

    score_dict = {"チーム": names}
    for i in range(9):
        score_dict[str(i+1)] = [scores[0][i], scores[1][i]]
    
    score_dict.update({"R": R, "H": H, "E": E})
    
    st.table(pd.DataFrame(score_dict).set_index("チーム"))

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
    st.balloons() # 風船も飛ばす

def render_out_indicator_3(count):
    color_on = "#ff2b2b"   # 点灯色（赤）
    color_off = "#e0e0e0"  # 消灯色（グレー）
    
    html = """
    <div style='font-family:sans-serif; font-weight:bold; display:flex; align-items:center;'>
        <span style='font-size:30px; margin-right:15px;'>OUT</span>
    """
    for i in range(3):
        color = color_on if i < count else color_off
        html += f"<span style='color:{color}; font-size:50px; line-height:1; margin-right:5px;'>●</span>"
    
    html += "</div>"
    return html