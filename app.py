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


import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

st.set_page_config(page_title="伝統的スコアブック", layout="wide")

# --- 1. スプレッドシート接続 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. 最新データの読み込み関数 ---
def load_data():
    try:
        # ttl=0 でキャッシュを無効化し、常に最新データを取得
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "選手名", "結果"])

df = load_data()

# --- 3. 選手ごとの成績を取得する関数 ---
def get_player_results(name, current_df):
    # 名前が一致するデータを抽出
    results = current_df[current_df["選手名"] == name]["結果"].tolist()
    # 最新の5件を表示
    return " / ".join(results[-5:]) if results else "ー"

# --- 4. 選手マスター ---
all_players = ["名執雅", "名執雅楽", "古屋 翔", "助っ人", "濱瑠晟", "清水 智広", "小野拓朗", "渡邊 誠也", "荒木豊", "中尾建太"]

st.title("⚾ 伝統的スコアブック (完全修正版)")

# --- 5. 画面レイアウト ---
left_col, right_col = st.columns([1.6, 2]) 

with left_col:
    st.subheader("📋 今日のオーダーと成績")
    
    current_lineup = []
    positions = ["8", "4", "6", "5", "2", "9", "7", "5", "DH", "3"]
    
    # ヘッダー行
    cols = st.columns([1, 1, 3, 4])
    cols[0].write("**打順**")
    cols[1].write("**位**")
    cols[2].write("**選手名**")
    cols[3].write("**成績**")

    # 10人分の行をループで作成
    for i in range(10):
        c1, c2, c3, c4 = st.columns([1, 1, 3, 4])
        c1.write(f"{i+1}")
        pos = c2.text_input(f"p_{i}", positions[i], key=f"pos_input_{i}", label_visibility="collapsed")
        name = c3.selectbox(f"n_{i}", all_players, index=i, key=f"name_select_{i}", label_visibility="collapsed")
        
        # 取得した成績を表示
        res_text = get_player_results(name, df)
        c4.info(res_text)
        current_lineup.append({"氏名": name})

with right_col:
    st.subheader("📝 成績入力")
    with st.form("input_form", clear_on_submit=True):
        player = st.selectbox("選手を選択", [p["氏名"] for p in current_lineup])
        result = st.radio("結果を選択", ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退"], horizontal=True)
        
        if st.form_submit_button("スプレッドシートに登録"):
            try:
                new_record = pd.DataFrame([{
                    "日付": datetime.date.today().strftime('%Y-%m-%d'), 
                    "選手名": player, 
                    "結果": result
                }])
                # 更新
                updated_df = pd.concat([df, new_record], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
                st.toast(f"{player} 選手の記録を保存しました！")
                st.rerun() # 画面を再描画して成績を反映
            except Exception as e:
                st.error(f"エラー: {e}")

    st.markdown("---")
    st.write("### 📜 登録済みデータ（デバッグ用）")
    st.dataframe(df.tail(10), use_container_width=True)

# --- 6. スコアボード ---
st.markdown("---")
st.subheader("📊 スコアボード")
score_df = pd.DataFrame([
    ["KAGURA", 1, 0, 0, 0, 2, 0, 0, 2, "", 5, 7, 0],
    ["SQUAD", 2, 0, 0, 1, 0, 0, 2, 0, "", 5, 4, 0]
], columns=["チーム", "1", "2", "3", "4", "5", "6", "7", "8", "9", "R", "H", "E"])
st.table(score_df)