import pandas as pd
from config.settings import SPREADSHEET_URL, TARGET_COLUMNS
from streamlit_gsheets import GSheetsConnection
import streamlit as st

def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_batting_data(spreadsheet_url=SPREADSHEET_URL):
    conn = get_connection()
    target_worksheet = "打撃成績"

    try:
        data = conn.read(spreadsheet=spreadsheet_url, worksheet=target_worksheet, ttl=0)
        if data.empty:
            return pd.DataFrame(columns=TARGET_COLUMNS + ["Year"])

        # 23列の不足分を補完
        for col in TARGET_COLUMNS:
            if col not in data.columns:
                data[col] = 0 if col in ["ID", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""

        data["日付"] = pd.to_datetime(data["日付"], errors="coerce")
        data["Year"] = data["日付"].dt.strftime("%Y").fillna("不明")
        data["日付"] = data["日付"].dt.date

        # カラム順をTARGET_COLUMNS + ["Year"]に統一
        data = data[TARGET_COLUMNS + ["Year"]]
        return data.dropna(how="all")
    except Exception as e:
        st.error(f"打撃データの読み込みに失敗しました ({target_worksheet}): {e}")
        return pd.DataFrame(columns=TARGET_COLUMNS + ["Year"])

@st.cache_data(ttl=60)
def load_pitching_data(spreadsheet_url=SPREADSHEET_URL):
    conn = get_connection()
    target_worksheet = "投手成績"

    try:
        data = conn.read(spreadsheet=spreadsheet_url, worksheet=target_worksheet, ttl=0)
        if data.empty:
            return pd.DataFrame(columns=TARGET_COLUMNS + ["Year"])

        # 23列の不足分を補完
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

        # カラム順をTARGET_COLUMNS + ["Year"]に統一
        data = data[TARGET_COLUMNS + ["Year"]]
        return data.dropna(how="all")
    except Exception as e:
        st.error(f"投手データの読み込みに失敗しました ({target_worksheet}): {e}")
        return pd.DataFrame(columns=TARGET_COLUMNS + ["Year"])