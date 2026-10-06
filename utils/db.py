import pandas as pd
from config.settings import SPREADSHEET_URL, TARGET_COLUMNS
from streamlit_gsheets import GSheetsConnection
import streamlit as st

def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

# 💡 キャッシュ時間を60秒から600秒(10分)に延長し、API通信エラー時はセッション内の既存データをフォールバックとして返す
@st.cache_data(ttl=600, show_spinner=False)
def load_batting_data(spreadsheet_url=SPREADSHEET_URL):
    target_worksheet = "打撃成績"
    try:
        conn = get_connection()
        # ttl=0 を削除してコネクション側のキャッシュも有効化
        data = conn.read(spreadsheet=spreadsheet_url, worksheet=target_worksheet)
        if data is None or data.empty:
            return st.session_state.get("cached_df_batting", pd.DataFrame(columns=TARGET_COLUMNS + ["Year"]))

        # 23列の不足分を補完
        for col in TARGET_COLUMNS:
            if col not in data.columns:
                data[col] = 0 if col in ["ID", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""

        data["日付"] = pd.to_datetime(data["日付"], errors="coerce")
        data["Year"] = data["日付"].dt.strftime("%Y").fillna("不明")
        data["日付"] = data["日付"].dt.date

        data = data[TARGET_COLUMNS + ["Year"]].dropna(how="all")
        
        # 正常取得できた場合はセッションに退避
        st.session_state["cached_df_batting"] = data
        return data
    except Exception as e:
        # 💡 通信エラーやAPI上限エラー(429)時もログアウトさせず、セッション内の前回の正常データを返す
        if "cached_df_batting" in st.session_state:
            return st.session_state["cached_df_batting"]
        return pd.DataFrame(columns=TARGET_COLUMNS + ["Year"])

@st.cache_data(ttl=600, show_spinner=False)
def load_pitching_data(spreadsheet_url=SPREADSHEET_URL):
    target_worksheet = "投手成績"
    try:
        conn = get_connection()
        data = conn.read(spreadsheet=spreadsheet_url, worksheet=target_worksheet)
        if data is None or data.empty:
            return st.session_state.get("cached_df_pitching", pd.DataFrame(columns=TARGET_COLUMNS + ["Year"]))

        for col in TARGET_COLUMNS:
            if col not in data.columns:
                if col in ["ID", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"]:
                    data[col] = 0
                else:
                    data[col] = ""

        data["投手名"] = data["投手名"].fillna("")
        data["日付"] = pd.to_datetime(data["日付"], errors="coerce")
        data["Year"] = data["日付"].dt.strftime("%Y").fillna("不明")
        data["日付"] = data["日付"].dt.date

        data = data[TARGET_COLUMNS + ["Year"]].dropna(how="all")
        
        # 正常取得できた場合はセッションに退避
        st.session_state["cached_df_pitching"] = data
        return data
    except Exception as e:
        if "cached_df_pitching" in st.session_state:
            return st.session_state["cached_df_pitching"]
        return pd.DataFrame(columns=TARGET_COLUMNS + ["Year"])