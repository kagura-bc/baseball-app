import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

# --- ベースとなる全選手データ取得関数 ---
@st.cache_data(ttl=600)
def _get_base_players_df():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="選手登録")
        
        # カラムが存在しない場合の初期化（エラー回避）
        for col in ["成績非表示", "オーダー非表示"]:
            if col not in df.columns:
                df[col] = False
                
        # 空欄をFalseに変換し、真偽値として扱う
        df["成績非表示"] = df["成績非表示"].fillna(False).astype(bool)
        df["オーダー非表示"] = df["オーダー非表示"].fillna(False).astype(bool)
        
        return df
    except Exception as e:
        st.error(f"選手情報の読み込みに失敗しました: {e}")
        return pd.DataFrame(columns=["選手名", "背番号", "成績非表示", "オーダー非表示"])

# --- ヘルパー関数: DFからリストと辞書を生成 ---
def _extract_lists(df):
    all_players = df["選手名"].dropna().astype(str).tolist()
    player_numbers = {}
    for _, row in df.iterrows():
        name = str(row.get("選手名", "")).strip()
        num = str(row.get("背番号", "")).replace(".0", "").strip()
        if name and name != "nan" and num and num != "nan":
            player_numbers[name] = num
    return all_players, player_numbers

# ==========================================
# 1. オーダー選択（試合入力）用の選手リストを取得
# ==========================================
def get_active_players():
    df = _get_base_players_df()
    active_df = df[~df["オーダー非表示"]]
    return _extract_lists(active_df)

# ==========================================
# 2. 成績表示（ランキング等）用の選手リストを取得
# ==========================================
def get_stats_active_players():
    df = _get_base_players_df()
    stats_active_df = df[~df["成績非表示"]]
    return _extract_lists(stats_active_df)