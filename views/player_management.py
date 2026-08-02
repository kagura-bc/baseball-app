import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

def show_player_management():
    st.title("👥 選手登録・管理")
    st.markdown("選手の追加、背番号の変更、各種非表示設定ができます。")
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    ws_name = "選手登録"
    
    try:
        df_players = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws_name)
    except Exception:
        st.error("「選手登録」シートが見つかりません。スプレッドシートをご確認ください。")
        return

    # カラムが存在しない場合の初期化
    for col in ["選手名", "背番号", "成績非表示", "オーダー非表示"]:
        if col not in df_players.columns:
            df_players[col] = None

    # 非表示列をチェックボックス用にBoolean型に変換
    df_players["成績非表示"] = df_players["成績非表示"].fillna(False).astype(bool)
    df_players["オーダー非表示"] = df_players["オーダー非表示"].fillna(False).astype(bool)
    
    # 背番号を文字列に整形
    df_players["背番号"] = df_players["背番号"].astype(str).replace("nan", "").replace("None", "").str.replace(".0", "")

    # st.data_editor で表を作成
    edited_df = st.data_editor(
        df_players,
        num_rows="dynamic",
        column_config={
            "選手名": st.column_config.TextColumn("選手名", required=True),
            "背番号": st.column_config.TextColumn("背番号"),
            "成績非表示": st.column_config.CheckboxColumn("成績から隠す", default=False, help="チェックを入れるとチーム成績等のランキングから消えます（退団選手など）"),
            "オーダー非表示": st.column_config.CheckboxColumn("オーダーから隠す", default=False, help="チェックを入れると試合入力のプルダウンから消えます（休部中など）"),
        },
        use_container_width=True,
        key="player_editor"
    )

    if st.button("💾 変更をスプレッドシートに保存", type="primary"):
        try:
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_name, data=edited_df)
            st.cache_data.clear() # utils/players.py のキャッシュもクリアされる
            st.success("✅ 選手情報を更新しました！")
            import time
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"保存エラー: {e}")