# config/settings.py
import streamlit as st
# チーム名
MY_TEAM = "KAGURA"

# スプレッドシート情報 (Secretsから取得)
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]

# 選手データ (Secretsから取得)
PLAYER_NUMBERS = dict(st.secrets["PLAYER_NUMBERS"])

# リスト生成
ALL_PLAYERS = list(PLAYER_NUMBERS.keys())

# ポジションリスト
ALL_POSITIONS = ["", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

# グラウンドリスト
GROUND_LIST = [
    "小瀬スポーツ公園", "緑が丘スポーツ公園", "飯田球場", "ふじでん球場",
    "中巨摩第二公園", "スコレーセンター", "花鳥の里スポーツ広場", "春日居スポーツ広場",
    "山梨大学", "双葉スポーツ公園", "釜無川スポーツ公園", "八田野球場", "北麓公園",
    "その他"
]

# 対戦相手リスト
OPPONENTS_LIST = [
    "ミッピーズ", "WISH", "NATSUME", "92ears", "球遊会", "プリティーボーイズ",
    "DREAM", "リベリオン", "KING STAR", "甲府市役所", "SQUAD", "CRAZY",
    "桜華", "甲府ドラゴンズ", "南アルプス市役所", "風間自工", "凪", "フェノーメノ", "その他"
]

# 公式戦リスト
OFFICIAL_GAME_TYPES = ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯", "公式戦"]