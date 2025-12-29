import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- ページ設定 ---
st.set_page_config(page_title="完全自動連携スコアブック", layout="wide")

# スタイル設定
st.markdown("""
    <style>
    .stSelectbox div[data-baseweb="select"] { font-size: 18px !important; font-weight: bold !important; }
    .score-table { font-size: 20px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# スプレッドシート設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

all_players = ["名執雅叶", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"]

# --- データ読み込み ---
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

# 1回〜9回までの得点をリスト化
k_inning_runs = []
for i in range(1, 10):
    # そのイニングの「得点」列を合計
    run = today_df[today_df["イニング"] == f"{i}回"]["得点"].fillna(0).astype(int).sum()
    k_inning_runs.append(run)

# 安打数（H）の自動計算
hits_list = ["単打", "二塁打", "三塁打", "本塁打"]
total_hits = today_df[today_df["結果"].isin(hits_list)].shape[0]
total_runs = sum(k_inning_runs)

# ==========================================
# 共通：完全自動スコアボード
# ==========================================
st.title("⚾ リアルタイム試合速報")

score_data = {
    "チーム": ["KAGURA", "相手チーム"],
    "1": [k_inning_runs[0], 0],
    "2": [k_inning_runs[1], 0],
    "3": [k_inning_runs[2], 0],
    "4": [k_inning_runs[3], 0],
    "5": [k_inning_runs[4], 0],
    "6": [k_inning_runs[5], 0],
    "7": [k_inning_runs[6], 0],
    "8": [k_inning_runs[7], 0],
    "9": [k_inning_runs[8], 0],
    "R": [total_runs, 0],
    "H": [total_hits, 0],
    "E": [0, 0]
}
st.table(pd.DataFrame(score_data))

st.divider()

page = st.sidebar.radio("ページ切替", ["打撃成績入力", "投手成績入力"])

# ==========================================
# 打撃成績入力（イニング選択を追加）
# ==========================================
if page == "打撃成績入力":
    left_col, right_col = st.columns([2.2, 2])

    with left_col:
        st.subheader("📋 オーダー")
        all_positions = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
        default_positions = ["8", "4", "6", "5", "2", "9", "7", "5", "DH", "3"]
        h_cols = st.columns([0.8, 1.5, 3, 4.5])
        current_lineup_names = []
        for i in range(10):
            c1, c2, c3, c4 = st.columns([0.8, 1.5, 3, 4.5])
            c1.write(f"**{i+1}**")
            pos = c2.selectbox(f"p_{i}", all_positions, index=all_positions.index(default_positions[i]), key=f"pos_{i}", label_visibility="collapsed")
            name = c3.selectbox(f"n_{i}", all_players, index=i, key=f"name_{i}", label_visibility="collapsed")
            p_res = df_batting[df_batting["選手名"] == name]["結果"].tolist()
            c4.info(" / ".join(p_res[-5:]) if p_res else "ー")
            current_lineup_names.append(name)

    with right_col:
        st.subheader("📝 記録入力（スコア自動連動）")
        with st.form("batting_form", clear_on_submit=True):
            # 今何回かを選択
            f_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)])
            f_player = st.selectbox("選手", current_lineup_names)
            f_result = st.radio("結果", ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退"], horizontal=True)
            f_run = st.number_input("入った得点 (この打席でのランナー生還数)", min_value=0, value=0)
            
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
                st.toast(f"{f_inning}のスコアを更新しました！")
                st.rerun()

# (投手ページは前回と同じのため省略可。必要ならそのまま残してください)
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