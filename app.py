import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- ページ設定 ---
st.set_page_config(page_title="野球スコア管理", layout="wide")

# 【視認性アップ！】文字を大きく、枠を見やすくする設定
st.markdown("""
    <style>
    /* セレクトボックスの文字を大きく */
    .stSelectbox div[data-baseweb="select"] {
        font-size: 18px !important;
        font-weight: bold !important;
    }
    /* 入力欄の高さを調整 */
    div[data-testid="stVerticalBlock"] div[data-testid="column"] {
        padding: 0px 1px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# スプレッドシート設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

all_players = ["名執雅叶", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"]

# サイドバー
page = st.sidebar.selectbox("表示ページを選択", ["打撃成績入力", "投手成績入力"])

# --- 打撃成績ページ ---
if page == "打撃成績入力":
    st.title("⚾ 打撃スコアブック")

    def load_batting_data():
        try:
            # 「シート1」または「打撃成績」タブを読み込み
            data = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
            return data.dropna(how="all")
        except:
            return pd.DataFrame(columns=["日付", "選手名", "結果"])

    df_batting = load_batting_data()

    def get_player_results(name, current_df):
        if current_df.empty: return "ー"
        results = current_df[current_df["選手名"] == name]["結果"].tolist()
        return " / ".join(results[-5:]) if results else "ー"

    left_col, right_col = st.columns([2.2, 2]) # 左側の幅をさらに広げました

    with left_col:
        st.subheader("📋 今日のオーダー")
        # 守備位置のリスト（数字の横にスペースを入れて見やすく）
        all_positions = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
        default_positions = ["8", "4", "6", "5", "2", "9", "7", "5", "DH", "3"]
        
        # ヘッダー（幅の比率を調整 [打順, 位置, 名前, 成績]）
        h_cols = st.columns([0.8, 1.5, 3, 4.5])
        h_cols[0].write("**打順**")
        h_cols[1].write("**位置**")
        h_cols[2].write("**名前**")
        h_cols[3].write("**直近5打席**")

        current_lineup_names = []
        for i in range(10):
            c1, c2, c3, c4 = st.columns([0.8, 1.5, 3, 4.5])
            c1.write(f"**{i+1}**")
            
            # 守備位置選択
            pos_val = default_positions[i]
            pos_index = all_positions.index(pos_val) if pos_val in all_positions else 0
            pos = c2.selectbox(f"p_{i}", all_positions, index=pos_index, key=f"pos_{i}", label_visibility="collapsed")
            
            # 名前選択
            name = c3.selectbox(f"n_{i}", all_players, index=i, key=f"name_{i}", label_visibility="collapsed")
            
            # 成績表示
            res_text = get_player_results(name, df_batting)
            c4.info(res_text) # infoの方が枠があってスマホでは見やすい場合があります
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

# --- 投手成績ページ ---
elif page == "投手成績入力":
    st.title("🔥 投手成績入力")

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
            p_innings = st.text_input("投球回数 (例: 5 2/3)", "0")
            p_pitches = st.number_input("球数", min_value=0, value=0)
            p_hits = st.number_input("被安打", min_value=0, value=0)
            p_so = st.number_input("奪三振", min_value=0, value=0)
            p_er = st.number_input("自責点", min_value=0, value=0)
            
            if st.form_submit_button("登録"):
                new_p_record = pd.DataFrame([{
                    "日付": datetime.date.today().strftime('%Y-%m-%d'),
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