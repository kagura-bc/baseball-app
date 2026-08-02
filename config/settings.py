# config/settings.py
import streamlit as st

# チーム名
MY_TEAM = "KAGURA"

# スプレッドシート情報 (Secretsから取得)
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]

# ポジションリスト
ALL_POSITIONS = ["", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"] 

# 公式戦リスト
OFFICIAL_GAME_TYPES = ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯", "公式戦"]