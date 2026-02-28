import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL, ALL_PLAYERS

def show_edit_page(df_batting, df_pitching, is_test_mode=False):
    st.title(" 🔧 データ修正")
    conn = st.connection("gsheets", type=GSheetsConnection)

    # 🧪 テストモード判定で書き込むシートを切り替え
    ws_batting = "打撃成績_テスト" if is_test_mode else "打撃成績"
    ws_pitching = "投手成績_テスト" if is_test_mode else "投手成績"
    
    # --- ★ 最終手段：Primaryボタンの色を「赤」に塗り替える ---
    st.markdown("""
        <style>
        div.stButton > button[data-testid="stBaseButton-primary"] {
            background-color: #ff4b4b !important;
            color: white !important;
            border: none !important;
            /* 高さを半分（3.5em → 1.8em）に変更 */
            height: 1.8em !important; 
            font-size: 20px !important;
            font-weight: bold !important;
            /* 文字が中央にくるように調整 */
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        /* ホバー時 */
        div.stButton > button[data-testid="stBaseButton-primary"]:hover {
            background-color: #ff3333 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.info("💡 **操作方法**：削除したい行にチェックを入れ、下の赤いボタンを押してください。")

    t1, t2 = st.tabs(["打撃成績", "投手成績"])
    
    with t1:
        st.subheader("打撃データの編集・削除")
        df_b_work = df_batting.copy()
        df_b_work.insert(0, "削除選択", False)
        
        edited_b = st.data_editor(
            df_b_work,
            column_config={"削除選択": st.column_config.CheckboxColumn("削除", default=False)},
            use_container_width=True, 
            key="bat_editor_final",
            hide_index=True
        )

        # ★ type="primary" を指定することで、CSSと確実に紐付けます
        if st.button("チェックした行を削除 ＆ 修正内容を保存", type="primary", use_container_width=True, key="del_bat_btn"):
            new_df = edited_b[edited_b["削除選択"] == False].drop(columns=["削除選択"])
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=new_df)
            st.cache_data.clear()
            st.success("更新しました")
            st.rerun()

    with t2:
        st.subheader("投手データの編集・削除")
        df_p_work = df_pitching.copy()
        df_p_work.insert(0, "削除選択", False)
        
        edited_p = st.data_editor(
            df_p_work,
            column_config={"削除選択": st.column_config.CheckboxColumn("削除", default=False)},
            use_container_width=True, 
            key="pitch_editor_final",
            hide_index=True
        )

        # ★ こちらも type="primary" にします
        if st.button("チェックした行を削除 ＆ 修正内容を保存 ", type="primary", use_container_width=True, key="del_pitch_btn"):
            new_df_p = edited_p[edited_p["削除選択"] == False].drop(columns=["削除選択"])
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=new_df_p)
            st.cache_data.clear()
            st.success("更新しました")
            st.rerun()