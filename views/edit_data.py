import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
# ★ 追加: GROUND_LIST と OPPONENTS_LIST をインポート
from config.settings import SPREADSHEET_URL, ALL_PLAYERS, GROUND_LIST, OPPONENTS_LIST

# --- 各種プルダウン用の選択肢を定義 ---
RESULT_OPTIONS = [
    "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打", 
    "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "振り逃げ三振", 
    "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "ボーク", "暴投", "捕逸", 
    "牽制死", "盗塁死", "盗塁", "走塁死", "ー"
]
INNING_OPTIONS = [f"{i}回表" for i in range(1, 15)] + [f"{i}回裏" for i in range(1, 15)] + ["延長表", "延長裏", "まとめ入力"]
MATCH_TYPES = ["公式戦", "練習試合", "その他"]
POSITIONS = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "DH", "代打", "代走", ""]
WIN_LOSE_OPTIONS = ["ー", "勝利", "敗戦", "セーブ", "ホールド"]

def show_edit_page(df_batting, df_pitching, is_test_mode=False):
    st.title(" 🔧 データ修正")
    conn = st.connection("gsheets", type=GSheetsConnection)

    # 🧪 テストモード判定で書き込むシートを切り替え
    ws_batting = "打撃成績_テスト" if is_test_mode else "打撃成績"
    ws_pitching = "投手成績_テスト" if is_test_mode else "投手成績"
    
    # --- Primaryボタンの色を「赤」に塗り替えるCSS ---
    st.markdown("""
        <style>
        div.stButton > button[data-testid="stBaseButton-primary"] {
            background-color: #ff4b4b !important;
            color: white !important;
            border: none !important;
            height: 1.8em !important; 
            font-size: 20px !important;
            font-weight: bold !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        div.stButton > button[data-testid="stBaseButton-primary"]:hover {
            background-color: #ff3333 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    t1, t2 = st.tabs(["🏏 打撃データの修正", "⚾️ 投手データの修正"])

    # ========================================================
    # 打撃データ修正タブ
    # ========================================================
    with t1:
        st.subheader("打撃データの編集・削除")
        df_b_work = df_batting.copy()
        df_b_work.insert(0, "削除選択", False)
        
        # 🌟 指定された項目をプルダウン化
        batting_config = {
            "削除選択": st.column_config.CheckboxColumn("削除", default=False),
            # ▼ プルダウン（選択式）項目
            "試合種別": st.column_config.SelectboxColumn("試合種別", options=MATCH_TYPES),
            "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=GROUND_LIST),
            "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=OPPONENTS_LIST),
            "守備位置": st.column_config.SelectboxColumn("守備位置", options=POSITIONS),
            "打球方向": st.column_config.SelectboxColumn("打球方向", options=POSITIONS),
            "位置": st.column_config.SelectboxColumn("位置", options=POSITIONS),
            "結果": st.column_config.SelectboxColumn("結果", options=RESULT_OPTIONS),
            "スコアラー": st.column_config.SelectboxColumn("スコアラー", options=ALL_PLAYERS),
            
            # ▼ 数値制限項目
            "打順": st.column_config.NumberColumn("打順", min_value=1, max_value=30, step=1),
            "打点": st.column_config.NumberColumn("打点", min_value=0, max_value=10, step=1),
            "得点": st.column_config.NumberColumn("得点", min_value=0, max_value=10, step=1),
            "盗塁": st.column_config.NumberColumn("盗塁", min_value=0, max_value=10, step=1),
        }
        
        edited_b = st.data_editor(
            df_b_work,
            column_config=batting_config,
            use_container_width=True, 
            key="bat_editor_final",
            hide_index=True
        )

        if st.button("チェックした行を削除 ＆ 修正内容を保存", type="primary", use_container_width=True, key="del_bat_btn"):
            new_df = edited_b[edited_b["削除選択"] == False].drop(columns=["削除選択"])
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=new_df)
            st.cache_data.clear()
            st.success("更新しました")
            import time
            time.sleep(0.5)
            st.rerun()

    # ========================================================
    # 投手データ修正タブ
    # ========================================================
    with t2:
        st.subheader("投手データの編集・削除")
        df_p_work = df_pitching.copy()
        df_p_work.insert(0, "削除選択", False)
        
        # 🌟 指定された項目をプルダウン化
        pitching_config = {
            "削除選択": st.column_config.CheckboxColumn("削除", default=False),
            # ▼ プルダウン（選択式）項目
            "試合種別": st.column_config.SelectboxColumn("試合種別", options=MATCH_TYPES),
            "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=GROUND_LIST),
            "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=OPPONENTS_LIST),
            "守備位置": st.column_config.SelectboxColumn("守備位置", options=POSITIONS),
            "打球方向": st.column_config.SelectboxColumn("打球方向", options=POSITIONS),
            "位置": st.column_config.SelectboxColumn("位置", options=POSITIONS),
            "結果": st.column_config.SelectboxColumn("結果", options=RESULT_OPTIONS),
            "スコアラー": st.column_config.SelectboxColumn("スコアラー", options=ALL_PLAYERS),
            "勝敗": st.column_config.SelectboxColumn("勝敗", options=WIN_LOSE_OPTIONS),
            
            # ▼ 数値制限項目
            "失点": st.column_config.NumberColumn("失点", min_value=0, step=1),
            "自責点": st.column_config.NumberColumn("自責点", min_value=0, step=1),
            "被安打": st.column_config.NumberColumn("被安打", min_value=0, step=1),
            "奪三振": st.column_config.NumberColumn("奪三振", min_value=0, step=1),
            "アウト数": st.column_config.NumberColumn("アウト数", min_value=0, step=1),
        }
        
        edited_p = st.data_editor(
            df_p_work,
            column_config=pitching_config,
            use_container_width=True, 
            key="pitch_editor_final",
            hide_index=True
        )

        if st.button("チェックした行を削除 ＆ 修正内容を保存 ", type="primary", use_container_width=True, key="del_pitch_btn"):
            new_df = edited_p[edited_p["削除選択"] == False].drop(columns=["削除選択"])
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=new_df)
            st.cache_data.clear()
            st.success("更新しました")
            import time
            time.sleep(0.5)
            st.rerun()