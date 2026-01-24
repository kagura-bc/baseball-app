import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL, ALL_PLAYERS, GROUND_LIST, OPPONENTS_LIST

def show_edit_page(df_batting, df_pitching):
    st.title(" 🔧 データ修正")
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    t1, t2 = st.tabs(["打撃成績", "投手成績"])

    # 共通選択肢
    inns = [f"{i}回" for i in range(1, 10)] + ["延長", "試合終了", "まとめ入力"]
    
    with t1:
        st.write("▼ 打撃データの編集")
        ed_b = st.data_editor(
            df_batting,
            column_config={
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD", required=True),
                "選手名": st.column_config.SelectboxColumn("選手名", options=ALL_PLAYERS, required=True),
                "イニング": st.column_config.SelectboxColumn("イニング", options=inns),
                "結果": st.column_config.SelectboxColumn("結果", options=["単打", "二塁打", "本塁打", "三振", "四球", "凡退", "失策"])
            },
            num_rows="dynamic", use_container_width=True, key="ed_bat"
        )
        if st.button("打撃保存", type="primary"):
            conn.update(spreadsheet=SPREADSHEET_URL, data=ed_b)
            st.cache_data.clear()
            st.success("更新しました")
            st.rerun()

    with t2:
        st.write("▼ 投手データの編集")
        ed_p = st.data_editor(
            df_pitching,
            column_config={
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD", required=True),
                "投手名": st.column_config.SelectboxColumn("投手名", options=ALL_PLAYERS),
                "イニング": st.column_config.SelectboxColumn("イニング", options=inns),
            },
            num_rows="dynamic", use_container_width=True, key="ed_pit"
        )
        if st.button("投手保存", type="primary"):
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=ed_p)
            st.cache_data.clear()
            st.success("更新しました")
            st.rerun()