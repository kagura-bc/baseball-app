import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- 1. ページ設定と基本情報 ---
st.set_page_config(page_title="伝統的スコアブック", layout="wide")

# スプレッドシートのURL
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"

# スプレッドシート接続
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Googleスプレッドシートへの接続設定（Secrets）が必要です。")
    st.stop()

# --- 2. データ読み込み関数 ---
def load_data():
    try:
        # ttl=0 でキャッシュを無効化し、常に最新データを取得
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        return data.dropna(how="all")
    except:
        # 読み込めない場合は空のデータフレームを返す
        return pd.DataFrame(columns=["日付", "選手名", "結果"])

df = load_data()

# --- 3. 選手ごとの過去成績を取得 ---
def get_player_results(name, current_df):
    if current_df.empty:
        return "ー"
    results = current_df[current_df["選手名"] == name]["結果"].tolist()
    return " / ".join(results[-5:]) if results else "ー"

# --- 4. 選手マスター（最新オーダー順） ---
all_players = [
    "名執雅", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", 
    "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"
]

st.title("⚾ 伝統的スコアブック (KAGURA 5-5 SQUAD)")

# --- 5. メインレイアウト（2カラム） ---
left_col, right_col = st.columns([1.8, 2]) 

with left_col:
    st.subheader("📋 今日のオーダーと成績")
    
    positions = ["8", "4", "6", "5", "2", "9", "7", "5", "DH", "3"]
    
    # ヘッダー行
    h_cols = st.columns([1, 1, 3, 5])
    h_cols[0].write("**打順**")
    h_cols[1].write("**位置**")
    h_cols[2].write("**選手名**")
    h_cols[3].write("**直近5打席**")

    current_lineup_names = []
    
    # 10人分の行を作成
    for i in range(10):
        c1, c2, c3, c4 = st.columns([1, 1, 3, 5])
        c1.write(f"{i+1}")
        # 位置と名前の入力
        pos = c2.text_input(f"p_{i}", positions[i], key=f"pos_{i}", label_visibility="collapsed")
        name = c3.selectbox(f"n_{i}", all_players, index=i, key=f"name_{i}", label_visibility="collapsed")
        
        # 成績の表示
        res_text = get_player_results(name, df)
        c4.info(res_text)
        current_lineup_names.append(name)

with right_col:
    st.subheader("📝 成績入力")
    with st.form("input_form", clear_on_submit=True):
        selected_player = st.selectbox("選手を選択", current_lineup_names)
        selected_result = st.radio("結果を選択", ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退"], horizontal=True)
        
        submit = st.form_submit_button("スプレッドシートに登録")
        
        if submit:
            try:
                new_record = pd.DataFrame([{
                    "日付": datetime.date.today().strftime('%Y-%m-%d'), 
                    "選手名": selected_player, 
                    "結果": selected_result
                }])
                # 既存データと合体
                updated_df = pd.concat([df, new_record], ignore_index=True)
                # スプレッドシート更新
                conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
                st.toast(f"✅ {selected_player}：{selected_result} を保存！")
                st.rerun() 
            except Exception as e:
                st.error(f"保存に失敗しました。URLや権限を確認してください: {e}")

    st.markdown("---")
    st.write("### 📜 最新の登録データ (10件)")
    st.dataframe(df.tail(10), use_container_width=True)

# --- 6. スコアボード ---
st.markdown("---")
st.subheader("📊 スコアボード")
score_data = [
    ["KAGURA", 1, 0, 0, 0, 2, 0, 0, 2, "", 5, 7, 0],
    ["SQUAD", 2, 0, 0, 1, 0, 0, 2, 0, "", 5, 4, 0]
]
score_df = pd.DataFrame(score_data, columns=["チーム", "1", "2", "3", "4", "5", "6", "7", "8", "9", "R", "H", "E"])
st.table(score_df)