import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

st.set_page_config(page_title="野球成績入力 (クラウド版)", layout="wide")
st.title("⚾ 野球成績入力アプリ (Googleスプレッドシート連携)")

# --- 1. スプレッドシートへの接続設定 ---
# 作成したスプレッドシートのURLをここに貼り付けてください
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"

# st.connection が secrets.toml の [connections.gsheets] を自動で見に行きます
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. 入力エリア ---
st.write("### 1. 試合結果を入力してください")
col1, col2, col3 = st.columns(3)

with col1:
    date = st.date_input("試合日", datetime.date.today())
with col2:
    player = st.selectbox("選手名", ["田中", "中尾", "佐藤", "鈴木", "高橋"])
with col3:
    result = st.radio("結果", ["安打", "二塁打", "三塁打", "本塁打", "四球", "三振", "凡退"])

# --- 3. 登録ボタンの処理 ---
if st.button("データを登録する"):
    try:
        # 現在のデータを取得（既存のデータがあれば読み込む）
        existing_data = conn.read(spreadsheet=SPREADSHEET_URL)
        existing_data = existing_data.dropna(how="all") 
        
        # 新しいレコードを作成
        new_record = pd.DataFrame([{
            "日付": date.strftime('%Y-%m-%d'),
            "選手名": player,
            "結果": result
        }])
        
        # 既存データと新規データを合体
        updated_df = pd.concat([existing_data, new_record], ignore_index=True)
        
        # スプレッドシートを更新
        conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
        
        st.success(f"【クラウド保存完了】 {date}：{player} 選手の {result} を記録しました！")
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

# --- 4. 表示エリア ---
st.markdown("---")
st.write("### 2. 現在の登録データ（Googleスプレッドシート）")

# 最新のデータを読み込んで表示
try:
    df = conn.read(spreadsheet=SPREADSHEET_URL)
    st.dataframe(df, width="stretch")
except:
    st.info("まだデータがないか、読み込みに失敗しました。")

