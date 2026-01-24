import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

# 接続オブジェクトの作成
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def load_batting_data():
    conn = get_connection()
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl="10m")
        if data.empty:
             return pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])
        
        expected_cols = ["日付", "打点", "盗塁", "得点", "位置", "グラウンド", "対戦相手", "試合種別", "イニング", "選手名", "結果", "種別"]
        for col in expected_cols:
            if col not in data.columns:
                data[col] = 0 if col in ["打点", "盗塁", "得点"] else ""

        data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
        return data.dropna(how="all")
    except:
        return pd.DataFrame()

def load_pitching_data():
    conn = get_connection()
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl="10m")
        if data.empty:
            return pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "処理野手", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "勝敗"])

        expected_cols = ["日付", "アウト数", "球数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "処理野手", "イニング", "投手名", "結果", "勝敗"]
        for col in expected_cols: 
            if col not in data.columns: 
                if col in ["グラウンド", "対戦相手", "試合種別", "処理野手", "投手名", "結果", "イニング", "勝敗"]:
                    data[col] = ""
                else:
                    data[col] = 0
        
        data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
        return data.dropna(how="all")
    except:
        return pd.DataFrame()

# ※ ここに delete_match_logic なども移動します