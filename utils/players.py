import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

@st.cache_data(ttl=60)
def _load_players_df():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="選手登録", ttl=0)
        if df.empty:
            return pd.DataFrame(columns=["選手名", "背番号", "成績非表示", "オーダー非表示"])
        return df
    except Exception as e:
        st.error(f"選手情報の読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=["選手名", "背番号", "成績非表示", "オーダー非表示"])

def _extract_lists(df):
    if df.empty or "選手名" not in df.columns:
        return [], {}
    
    # 欠損値を除外
    valid_df = df.dropna(subset=["選手名"]).copy()
    valid_df["選手名"] = valid_df["選手名"].astype(str).str.strip()
    
    # オーダー非表示・成績非表示の列が存在する場合の処理
    if "オーダー非表示" in valid_df.columns:
        active_order_df = valid_df[~valid_df["オーダー非表示"].astype(str).str.lower().isin(["true", "1", "yes"])]
    else:
        active_order_df = valid_df

    if "成績非表示" in valid_df.columns:
        active_stats_df = valid_df[~valid_df["成績非表示"].astype(str).str.lower().isin(["true", "1", "yes"])]
    else:
        active_stats_df = valid_df

    # 背番号の整形
    def fmt_num(num_val):
        if pd.isna(num_val) or str(num_val).strip() in ["nan", "None", ""]:
            return ""
        try:
            return str(int(float(num_val)))
        except:
            return str(num_val).strip()

    # 背番号付きの表示名リストを作成
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

def get_active_players():
    df = _load_players_df()
    return _extract_lists(df)

@st.cache_data(ttl=60)
def get_stats_active_players():
    df = _load_players_df()
    if df.empty or "選手名" not in df.columns:
        return [], {}
    
    valid_df = df.dropna(subset=["選手名"]).copy()
    valid_df["選手名"] = valid_df["選手名"].astype(str).str.strip()
    
    if "成績非表示" in valid_df.columns:
        stats_df = valid_df[~valid_df["成績非表示"].astype(str).str.lower().isin(["true", "1", "yes"])]
    else:
        stats_df = valid_df

    stats_players = stats_df["選手名"].tolist()
    
    def fmt_num(num_val):
        if pd.isna(num_val) or str(num_val).strip() in ["nan", "None", ""]:
            return ""
        try:
            return str(int(float(num_val)))
        except:
            return str(num_val).strip()

    player_numbers = {row["選手名"]: fmt_num(row.get("背番号", "")) for _, row in valid_df.iterrows()}
    
    return stats_players, player_numbers