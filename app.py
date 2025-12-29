import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- ページ設定 ---
st.set_page_config(page_title="野球スコア管理システム", layout="wide")

# スタイルの設定
st.markdown("""
    <style>
    .stSelectbox div[data-baseweb="select"] { font-size: 18px !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

# スプレッドシート設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

all_players = ["名執雅叶", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"]

# --- データ読み込み関数 ---
def load_batting_data():
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "イニング", "選手名", "結果", "得点"])

df_batting = load_batting_data()

# ==========================================
# 自動集計ロジック（イニング別）
# ==========================================
today_str = datetime.date.today().strftime('%Y-%m-%d')
today_df = df_batting[df_batting["日付"] == today_str]

k_inning_display = []
total_runs = 0

for i in range(1, 10):
    inning_name = f"{i}回"
    inning_data = today_df[today_df["イニング"] == inning_name]
    
    if inning_data.empty:
        k_inning_display.append("") 
    else:
        run = inning_data["得点"].fillna(0).astype(int).sum()
        k_inning_display.append(run)
        total_runs += run

hits_list = ["単打", "二塁打", "三塁打", "本塁打"]
total_hits = today_df[today_df["結果"].isin(hits_list)].shape[0]

# ==========================================
# 共通：自動連携スコアボード表示
# ==========================================
st.title("⚾ リアルタイム試合速報")

score_data = {
    "チーム": ["KAGURA", "相手チーム"],
    "1": [k_inning_display[0], ""],
    "2": [k_inning_display[1], ""],
    "3": [k_inning_display[2], ""],
    "4": [k_inning_display[3], ""],
    "5": [k_inning_display[4], ""],
    "6": [k_inning_display[5], ""],
    "7": [k_inning_display[6], ""],
    "8": [k_inning_display[7], ""],
    "9": [k_inning_display[8], ""],
    "R": [total_runs, ""],
    "H": [total_hits, ""],
    "E": ["", ""]
}
st.table(pd.DataFrame(score_data))

st.divider()

# 【重要：ここが page 変数の定義場所です】
page = st.sidebar.radio("表示ページを選択", ["打撃成績入力", "投手成績入力"])

# ==========================================
# ページ1：打撃成績入力
# ==========================================
if page == "打撃成績入力":
    st.subheader("📋 今日のオーダーと成績")
    
    left_col, right_col = st.columns([2.2, 2])

    with left_col:
        all_positions = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
        default_positions = ["8", "4", "6", "5", "2", "9", "7", "5", "DH", "3"]
        h_cols = st.columns([0.8, 1.5, 3, 4.5])
        h_cols[0].write("**打順**")
        h_cols[1].write("**位置**")
        h_cols[2].write("**名前**")
        h_cols[3].write("**直近5打席**")

        current_lineup_names = []
        for i in range(10):
            c1, c2, c3, c4 = st.columns([0.8, 1.5, 3, 4.5])
            c1.write(f"**{i+1}**")
            pos_val = default_positions[i]
            pos_index = all_positions.index(pos_val) if pos_val in all_positions else 0
            pos = c2.selectbox(f"p_{i}", all_positions, index=pos_index, key=f"pos_{i}", label_visibility="collapsed")
            name = c3.selectbox(f"n_{i}", all_players, index=i, key=f"name_{i}", label_visibility="collapsed")
            
            p_res = df_batting[df_batting["選手名"] == name]["結果"].tolist()
            c4.info(" / ".join(p_res[-5:]) if p_res else "ー")
            current_lineup_names.append(name)

    with right_col:
        st.subheader("📝 記録入力")
        with st.form("batting_form", clear_on_submit=True):
            f_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)])
            f_player = st.selectbox("選手", current_lineup_names)
            f_result = st.radio("結果", ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退"], horizontal=True)
            f_run = st.number_input("入った得点 (この打席での生還数)", min_value=0, value=0)
            
            if st.form_submit_button("成績を登録"):
                new_record = pd.DataFrame([{
                    "日付": today_str,
                    "イニング": f_inning,
                    "選手名": f_player,
                    "結果": f_result,
                    "得点": f_run
                }])
                updated_df = pd.concat([df_batting, new_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
                st.toast("保存完了！")
                st.rerun()

# ==========================================
# ページ2：投手成績入力
# ==========================================
elif page == "投手成績入力":
    st.subheader("🔥 投手成績入力")

    def load_pitching_data():
        try:
            data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl=0)
            return data.dropna(how="all")
        except:
            return pd.DataFrame(columns=["日付", "投手名", "回数", "球数", "被安打", "奪三振", "自責点"])

    df_pitching = load_pitching_data()

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📝 記録")
        with st.form("pitching_form", clear_on_submit=True):
            p_name = st.selectbox("投手名", all_players)
            p_innings = st.text_input("投球回数", "0")
            p_pitches = st.number_input("球数", min_value=0, value=0)
            p_hits = st.number_input("被安打", min_value=0, value=0)
            p_so = st.number_input("奪三振", min_value=0, value=0)
            p_er = st.number_input("自責点", min_value=0, value=0)
            
            if st.form_submit_button("登録"):
                new_p_record = pd.DataFrame([{
                    "日付": today_str,
                    "投手名": p_name, "回数": p_innings, "球数": p_pitches,
                    "被安打": p_hits, "奪三振": p_so, "自責点": p_er
                }])
                updated_p_df = pd.concat([df_pitching, new_p_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_p_df)
                st.toast("保存完了！")
                st.rerun()

    with col2:
        st.subheader("📊 履歴")
        st.dataframe(df_pitching.tail(10), use_container_width=True)