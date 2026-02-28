import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

# 接続オブジェクトの作成
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def load_batting_data(is_test_mode=False):
    conn = get_connection()
    # ▼ 末尾に "Year" を追加しました
    expected_cols = ["日付", "打点", "盗塁", "得点", "位置", "グラウンド", "対戦相手", "試合種別", "イニング", "選手名", "結果", "種別", "Year"]
    
    target_worksheet = "打撃成績_テスト" if is_test_mode else "打撃成績"
    
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=target_worksheet, ttl="10m")
        
        if data.empty:
             return pd.DataFrame(columns=expected_cols)
        
        for col in expected_cols:
            if col not in data.columns:
                data[col] = 0 if col in ["打点", "盗塁", "得点"] else ""

        # ▼ 日付から "Year" を自動生成する処理を追加（テスト入力時に年が抜けるのを防ぐため）
        data["日付"] = pd.to_datetime(data["日付"], errors='coerce')
        data["Year"] = data["日付"].dt.strftime('%Y').fillna("不明")
        data["日付"] = data["日付"].dt.date
        
        return data.dropna(how="all")
    except Exception as e:
        st.error(f"打撃データの読み込みに失敗しました ({target_worksheet}): {e}")
        return pd.DataFrame(columns=expected_cols)

def load_pitching_data(is_test_mode=False):
    conn = get_connection()
    # ▼ 末尾に "選手名" と "Year" を追加しました
    expected_cols = ["日付", "アウト数", "球数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "処理野手", "イニング", "投手名", "結果", "勝敗", "選手名", "Year"]
    
    target_worksheet = "投手成績_テスト" if is_test_mode else "投手成績"
    
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=target_worksheet, ttl="10m")
        if data.empty:
            return pd.DataFrame(columns=expected_cols)

        for col in expected_cols: 
            if col not in data.columns: 
                if col in ["グラウンド", "対戦相手", "試合種別", "処理野手", "投手名", "選手名", "結果", "イニング", "勝敗", "Year"]:
                    data[col] = ""
                else:
                    data[col] = 0
        
        # ▼ 投手データに「選手名」が欠けている場合は「投手名」をコピーする
        data.loc[data["選手名"] == "", "選手名"] = data["投手名"]
        
        # ▼ 日付から "Year" を自動生成する処理を追加
        data["日付"] = pd.to_datetime(data["日付"], errors='coerce')
        data["Year"] = data["日付"].dt.strftime('%Y').fillna("不明")
        data["日付"] = data["日付"].dt.date
        
        return data.dropna(how="all")
    except Exception as e:
        st.error(f"投手データの読み込みに失敗しました ({target_worksheet}): {e}")
        return pd.DataFrame(columns=expected_cols)

# ※ ここに delete_match_logic なども移動します