import pandas as pd
from config.settings import SPREADSHEET_URL
from streamlit_gsheets import GSheetsConnection
import streamlit as st


# 接続オブジェクトの作成
def get_connection():
  return st.connection("gsheets", type=GSheetsConnection)


@st.cache_data(ttl=60)
def load_batting_data(spreadsheet_url=SPREADSHEET_URL):
  conn = get_connection()
  expected_cols = [
      "日付",
      "打点",
      "位置",
      "グラウンド",
      "対戦相手",
      "試合種別",
      "イニング",
      "結果",
      "スコアラー",
  ]

  target_worksheet = "打撃成績"

  try:
    data = conn.read(
        spreadsheet=spreadsheet_url, worksheet=target_worksheet, ttl=0
    )

    if data.empty:
      return pd.DataFrame(columns=expected_cols + ["Year"])

    for col in expected_cols:
      if col not in data.columns:
        data[col] = 0 if col in ["打点", "得点"] else ""

    # 日付から "Year" を自動生成する処理を追加
    data["日付"] = pd.to_datetime(data["日付"], errors="coerce")
    data["Year"] = data["日付"].dt.strftime("%Y").fillna("不明")
    data["日付"] = data["日付"].dt.date

    return data.dropna(how="all")
  except Exception as e:
    st.error(f"打撃データの読み込みに失敗しました ({target_worksheet}): {e}")
    return pd.DataFrame(columns=expected_cols + ["Year"])


@st.cache_data(ttl=60)
def load_pitching_data(spreadsheet_url=SPREADSHEET_URL):
  conn = get_connection()
  expected_cols = [
      "日付",
      "アウト数",
      "球数",
      "失点",
      "自責点",
      "グラウンド",
      "対戦相手",
      "試合種別",
      "処理野手",
      "イニング",
      "投手名",
      "結果",
      "勝敗",
      "スコアラー",
  ]

  target_worksheet = "投手成績"

  try:
    data = conn.read(
        spreadsheet=spreadsheet_url, worksheet=target_worksheet, ttl=0
    )
    if data.empty:
      return pd.DataFrame(columns=expected_cols + ["Year"])

    for col in expected_cols:
      if col not in data.columns:
        if col in [
            "グラウンド",
            "対戦相手",
            "試合種別",
            "処理野手",
            "投手名",
            "結果",
            "イニング",
            "勝敗",
            "スコアラー",
        ]:
          data[col] = ""
        else:
          data[col] = 0

    # 投手名の欠損値を補正
    data["投手名"] = data["投手名"].fillna("")

    # 日付から "Year" を自動生成する処理
    data["日付"] = pd.to_datetime(data["日付"], errors="coerce")
    data["Year"] = data["日付"].dt.strftime("%Y").fillna("不明")
    data["日付"] = data["日付"].dt.date

    return data.dropna(how="all")
  except Exception as e:
    st.error(f"投手データの読み込みに失敗しました ({target_worksheet}): {e}")
    return pd.DataFrame(columns=expected_cols + ["Year"])