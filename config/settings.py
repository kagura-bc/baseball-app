# config/settings.py
import streamlit as st

# チーム名
MY_TEAM = "KAGURA"

# スプレッドシート情報 (Secretsから取得)
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]

# ポジションリスト
ALL_POSITIONS = ["", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"] 

# 公式戦リスト
OFFICIAL_GAME_TYPES = ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯", "甲府市杯", "公式戦"]

TARGET_COLUMNS = [
    "ID", "日付", "イニング", "打順", "打者名", "守備位置", "結果", "打球方向", 
    "処理野手", "エラー野手", "ランナー状況", "打点", "投手名", "自責点", "球数", 
    "ストライク", "ファールボール", "ボール", "グラウンド", "対戦相手", "試合種別", "勝敗", "スコアラー"
]