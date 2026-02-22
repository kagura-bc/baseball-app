import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

# 接続オブジェクトの作成
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def load_batting_data():
    conn = get_connection()
    # エラー時にも返す必要があるので、期待するカラムを先に定義します
    expected_cols = ["日付", "打点", "盗塁", "得点", "位置", "グラウンド", "対戦相手", "試合種別", "イニング", "選手名", "結果", "種別"]
    
    try:
        # worksheet="打撃成績" を追加してシートを明示的に指定します
        # ※実際のシート名と異なる場合は書き換えてください
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="打撃成績", ttl="10m")
        
        if data.empty:
             return pd.DataFrame(columns=expected_cols)
        
        for col in expected_cols:
            if col not in data.columns:
                data[col] = 0 if col in ["打点", "盗塁", "得点"] else ""

        data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
        return data.dropna(how="all")
    except Exception as e:
        # エラーが発生してもアプリが落ちないよう、画面にエラーを表示しつつ枠組みだけのデータを返します
        st.error(f"打撃データの読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=expected_cols)

def load_pitching_data():
    conn = get_connection()
    expected_cols = ["日付", "アウト数", "球数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "処理野手", "イニング", "投手名", "結果", "勝敗"]
    
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl="10m")
        if data.empty:
            return pd.DataFrame(columns=expected_cols)

        for col in expected_cols: 
            if col not in data.columns: 
                if col in ["グラウンド", "対戦相手", "試合種別", "処理野手", "投手名", "結果", "イニング", "勝敗"]:
                    data[col] = ""
                else:
                    data[col] = 0
        
        data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
        return data.dropna(how="all")
    except Exception as e:
        # こちらも同様にエラー処理を修正します
        st.error(f"投手データの読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=expected_cols)

# ※ ここに delete_match_logic なども移動します