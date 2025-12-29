import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- ページ設定 ---
st.set_page_config(page_title="野球スコア管理", layout="wide")

# スタイルの設定
st.markdown("""
    <style>
    .stSelectbox div[data-baseweb="select"] {
        font-size: 18px !important;
        font-weight: bold !important;
    }
    .score-board {
        font-family: 'Courier New', Courier, monospace;
        background-color: #002200;
        color: #00FF00;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# スプレッドシート設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

all_players = ["名執雅叶", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"]

# ==========================================
# 共通：本格スコアボード表示（最上部）
# ==========================================
st.title("⚾ 試合速報")

# サイドバーで各回の得点を入力
st.sidebar.header("🏆 スコア詳細入力")

with st.sidebar.expander("KAGURA 得点入力"):
    k_runs = [st.number_input(f"KAGURA {i+1}回", min_value=0, value=0, key=f"k{i}") for i in range(9)]
    k_h = st.number_input("KAGURA 安打数", min_value=0, value=0)
    k_e = st.number_input("KAGURA 失策数", min_value=0, value=0)

with st.sidebar.expander("SQUAD 得点入力"):
    s_runs = [st.number_input(f"SQUAD {i+1}回", min_value=0, value=0, key=f"s{i}") for i in range(9)]
    s_h = st.number_input("SQUAD 安打数", min_value=0, value=0)
    s_e = st.number_input("SQUAD 失策数", min_value=0, value=0)

# スコア表の作成
score_data = {
    "チーム": ["KAGURA", "SQUAD"],
    "1": [k_runs[0], s_runs[0]],
    "2": [k_runs[1], s_runs[1]],
    "3": [k_runs[2], s_runs[2]],
    "4": [k_runs[3], s_runs[3]],
    "5": [k_runs[4], s_runs[4]],
    "6": [k_runs[5], s_runs[5]],
    "7": [k_runs[6], s_runs[6]],
    "8": [k_runs[7], s_runs[7]],
    "9": [k_runs[8], s_runs[8]],
    "R": [sum(k_runs), sum(s_runs)],
    "H": [k_h, s_h],
    "E": [k_e, s_e]
}
df_score = pd.DataFrame(score_data)

# スコアボードを表示
st.table(df_score)

st.divider()

# サイドバーでページ切り替え
page = st.sidebar.radio("表示ページを選択", ["打撃成績入力", "投手成績入力"])

# ==========================================
# ページ1：打撃成績入力（以下、前回のロジックと同じ）
# ==========================================
if page == "打撃成績入力":
    st.subheader("📋 今日のオーダーと成績")
    def load_batting_data():
        try:
            data = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
            return data.dropna(how="all")
        except:
            return pd.DataFrame(columns=["日付", "選手名", "結果"])
    df_batting = load_batting_data()

    def get_player_results(name, current_df):
        if current_df.empty: return "ー"
        results = current_df[current_df["選手名"] == name]["結果"].tolist()
        return " / ".join(results[-5:]) if results else "ー"

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
            res_text = get_player_results(name, df_batting)
            c4.info(res_text)
            current_lineup_names.append(name)
    with right_col:
        st.subheader("📝 打撃結果入力")
        with st.form("batting_form", clear_on_submit=True):
            selected_player = st.selectbox("選手を選択", current_lineup_names)
            selected_result = st.radio("結果", ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退"], horizontal=True)
            if st.form_submit_button("打撃成績を登録"):
                new_record = pd.DataFrame([{"日付": datetime.date.today().strftime('%Y-%m-%d'), "選手名": selected_player, "結果": selected_result}])
                updated_df = pd.concat([df_batting, new_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
                st.toast("保存完了！")
                st.rerun()

# ==========================================
# ページ2：投手成績入力（以下、前回のロジックと同じ）
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
        st.subheader("📝 投球内容を記録")
        with st.form("pitching_form", clear_on_submit=True):
            p_name = st.selectbox("投手名", all_players)
            p_innings = st.text_input("投球回数 (例: 5 2/3)", "0")
            p_pitches = st.number_input("球数", min_value=0, value=0)
            p_hits = st.number_input("被安打", min_value=0, value=0)
            p_so = st.number_input("奪三振", min_value=0, value=0)
            p_er = st.number_input("自責点", min_value=0, value=0)
            if st.form_submit_button("投手成績を登録"):
                new_p_record = pd.DataFrame([{
                    "日付": datetime.date.today().strftime('%Y-%m-%d'),
                    "投手名": p_name, "回数": p_innings, "球数": p_pitches,
                    "被安打": p_hits, "奪三振": p_so, "自責点": p_er
                }])
                updated_p_df = pd.concat([df_pitching, new_p_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_p_df)
                st.toast("投手成績を保存しました！")
                st.rerun()
    with col2:
        st.subheader("📊 投手成績ログ")
        st.dataframe(df_pitching.tail(10), use_container_width=True)