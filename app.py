import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- ページ設定 ---
st.set_page_config(page_title="野球スコア管理システム", layout="wide")

# スプレッドシート設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# 共通の選手リスト
all_players = ["名執雅叶", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"]

# --- サイドバーでページ切り替え ---
page = st.sidebar.selectbox("表示ページを選択", ["打撃成績入力", "投手成績入力"])

# ==========================================
# ページ1：打撃成績入力
# ==========================================
if page == "打撃成績入力":
    st.title("⚾ 打撃スコアブック")

    def load_batting_data():
        try:
            # 「シート1」または「打撃成績」など適切なシート名を指定
            data = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
            return data.dropna(how="all")
        except:
            return pd.DataFrame(columns=["日付", "選手名", "結果"])

    df_batting = load_batting_data()

    def get_player_results(name, current_df):
        if current_df.empty: return "ー"
        results = current_df[current_df["選手名"] == name]["結果"].tolist()
        return " / ".join(results[-5:]) if results else "ー"

    left_col, right_col = st.columns([1.8, 2])

    with left_col:
        st.subheader("📋 今日のオーダー")
        all_positions = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
        default_positions = ["8", "4", "6", "5", "2", "9", "7", "5", "DH", "3"]
        
        current_lineup_names = []
        for i in range(10):
            c1, c2, c3, c4 = st.columns([1, 1.5, 3, 5])
            c1.write(f"{i+1}")
            pos = c2.selectbox(f"p_{i}", all_positions, index=all_positions.index(default_positions[i]) if default_positions[i] in all_positions else 0, key=f"pos_{i}", label_visibility="collapsed")
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
                st.toast("打撃成績を保存しました！")
                st.rerun()

# ==========================================
# ページ2：投手成績入力
# ==========================================
elif page == "投手成績入力":
    st.title("🔥 投手成績入力")

    def load_pitching_data():
        try:
            # ワークシート名を指定（スプレッドシート側に「投手成績」というタブを作ってください）
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
                    "投手名": p_name,
                    "回数": p_innings,
                    "球数": p_pitches,
                    "被安打": p_hits,
                    "奪三振": p_so,
                    "自責点": p_er
                }])
                updated_p_df = pd.concat([df_pitching, new_p_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_p_df)
                st.toast("投手成績を保存しました！")
                st.rerun()

    with col2:
        st.subheader("📊 投手成績ログ")
        st.dataframe(df_pitching.tail(10), use_container_width=True)