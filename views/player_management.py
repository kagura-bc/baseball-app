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

    # ========================================================
    # ➕ 新規選手・背番号の追加フォーム
    # ========================================================
    with st.form(key="add_player_form", clear_on_submit=True):
        st.subheader("➕ 新規選手の追加")
        col_name, col_num, col_btn = st.columns([2, 1, 1])
        with col_name:
            new_name = st.text_input("選手名", placeholder="例：山田 太郎")
        with col_num:
            new_num = st.text_input("背番号", placeholder="例：10")
        with col_btn:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True) # 位置合わせ用
            add_submitted = st.form_submit_button("追加する", type="secondary", use_container_width=True)

        if add_submitted:
            if new_name.strip():
                # 既に同じ名前の選手がいないかチェック
                if new_name.strip() in df_players["選手名"].values:
                    st.warning(f"「{new_name.strip()}」は既に登録されています。")
                else:
                    new_row = pd.DataFrame([{
                        "選手名": new_name.strip(),
                        "背番号": new_num.strip(),
                        "成績非表示": False,
                        "オーダー非表示": False
                    }])
                    updated_df = pd.concat([df_players, new_row], ignore_index=True)
                    try:
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_name, data=updated_df)
                        st.cache_data.clear()
                        st.success(f"✅ 選手「{new_name.strip()}」(背番号: {new_num.strip()}) を追加しました！")
                        import time
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"追加エラー: {e}")
            else:
                st.warning("選手名を入力してください。")

    st.divider()
    st.subheader("📋 選手一覧・編集・非表示設定")

    # st.data_editor で表を作成（既存の編集・削除用）
    edited_df = st.data_editor(
        df_players,
        num_rows="dynamic",
        column_config={
            "選手名": st.column_config.TextColumn("選手名", required=True),
            "背番号": st.column_config.TextColumn("背番号"),
            "成績非表示": st.column_config.CheckboxColumn("成績非表示", default=False, help="チェックを入れるとチーム成績等のランキングから消えます（退団選手など）"),
            "オーダー非表示": st.column_config.CheckboxColumn("オーダー非表示", default=False, help="チェックを入れると試合入力のプルダウンから消えます（休部中など）"),
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