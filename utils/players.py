import pandas as pd
from config.settings import SPREADSHEET_URL
from streamlit_gsheets import GSheetsConnection
import streamlit as st


# 💡 ログイン中のDB URLを動的に取得するヘルパー関数
def _get_target_url(spreadsheet_url=None):
  return spreadsheet_url or st.session_state.get(
      "my_spreadsheet_url", SPREADSHEET_URL
  )


@st.cache_data(ttl=60)
def _load_players_df(spreadsheet_url=None):
  target_url = _get_target_url(spreadsheet_url)
  conn = st.connection("gsheets", type=GSheetsConnection)
  try:
    df = conn.read(spreadsheet=target_url, worksheet="選手登録", ttl=0)
    if df.empty:
      return pd.DataFrame(
          columns=["選手名", "背番号", "成績非表示", "オーダー非表示"]
      )
    return df
  except Exception as e:
    st.error(f"選手情報の読み込みに失敗しました: {e}")
    return pd.DataFrame(
        columns=["選手名", "背番号", "成績非表示", "オーダー非表示"]
    )


def _parse_bool(val):
  if pd.isna(val):
    return False
  if isinstance(val, bool):
    return val
  if isinstance(val, (int, float)):
    return val == 1

  s = str(val).strip().lower()
  if s in ["false", "f", "no", "n", "0", "none", "nan", ""]:
    return False
  return s in ["true", "1", "yes", "t", "y", "checked", "on"]


def _extract_lists(df):
  if df.empty or "選手名" not in df.columns:
    return [], {}

  valid_df = df.dropna(subset=["選手名"]).copy()
  valid_df["選手名"] = valid_df["選手名"].astype(str).str.strip()

  valid_df["オーダー非表示_bool"] = (
      valid_df["オーダー非表示"].apply(_parse_bool)
      if "オーダー非表示" in valid_df.columns
      else False
  )
  valid_df["成績非表示_bool"] = (
      valid_df["成績非表示"].apply(_parse_bool)
      if "成績非表示" in valid_df.columns
      else False
  )

  active_order_df = valid_df[~valid_df["オーダー非表示_bool"]]

  def fmt_num(num_val):
    if pd.isna(num_val) or str(num_val).strip() in ["nan", "None", ""]:
      return ""
    try:
      return str(int(float(num_val)))
    except:
      return str(num_val).strip()

  all_players = []
  player_numbers = {}
  for _, row in active_order_df.iterrows():
    name = row["選手名"]
    num = fmt_num(row.get("背番号", ""))
    player_numbers[name] = num
    if num:
      all_players.append(f"{name} ({num})")
    else:
      all_players.append(name)

  return all_players, player_numbers


def get_active_players(spreadsheet_url=None):
  df = _load_players_df(spreadsheet_url=spreadsheet_url)
  return _extract_lists(df)


@st.cache_data(ttl=60)
def get_stats_active_players(spreadsheet_url=None):
  df = _load_players_df(spreadsheet_url=spreadsheet_url)
  if df.empty or "選手名" not in df.columns:
    return [], {}

  valid_df = df.dropna(subset=["選手名"]).copy()
  valid_df["選手名"] = valid_df["選手名"].astype(str).str.strip()

  valid_df["成績非表示_bool"] = (
      valid_df["成績非表示"].apply(_parse_bool)
      if "成績非表示" in valid_df.columns
      else False
  )

  stats_df = valid_df[~valid_df["成績非表示_bool"]]
  stats_players = stats_df["選手名"].tolist()

  def fmt_num(num_val):
    if pd.isna(num_val) or str(num_val).strip() in ["nan", "None", ""]:
      return ""
    try:
      return str(int(float(num_val)))
    except:
      return str(num_val).strip()

  player_numbers = {
      row["選手名"]: fmt_num(row.get("背番号", "")) for _, row in valid_df.iterrows()
  }

  return stats_players, player_numbers