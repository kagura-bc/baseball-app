import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL

def show_player_management():
    st.title("👥 登録・管理")
    st.markdown("選手、相手チーム、グラウンドの追加、情報の変更、非表示設定ができます。")
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 🌟 タブで「選手管理」「相手チーム管理」「グラウンド管理」を切り替え
    tab_player, tab_opponent, tab_ground = st.tabs(["👤 選手管理", "🏟️ 相手チーム管理", "📍 グラウンド管理"])

    # ========================================================
    # Tab 1: 選手管理
    # ========================================================
    with tab_player:
        ws_name = "選手登録"
        
        try:
            df_players = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws_name)
        except Exception:
            st.error("「選手登録」シートが見つかりません。スプレッドシートをご確認ください。")
            return

        for col in ["選手名", "背番号", "成績非表示", "オーダー非表示"]:
            if col not in df_players.columns:
                df_players[col] = None

        df_players["成績非表示"] = df_players["成績非表示"].fillna(False).astype(bool)
        df_players["オーダー非表示"] = df_players["オーダー非表示"].fillna(False).astype(bool)
        df_players["背番号"] = df_players["背番号"].astype(str).replace("nan", "").replace("None", "").str.replace(".0", "")

        with st.form(key="add_player_form", clear_on_submit=True):
            st.subheader("➕ 新規選手の追加")
            col_name, col_num, col_btn = st.columns([2, 1, 1])
            with col_name:
                new_name = st.text_input("選手名", placeholder="例：山田 太郎")
            with col_num:
                new_num = st.text_input("背番号", placeholder="例：10")
            with col_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                add_submitted = st.form_submit_button("追加する", type="secondary", use_container_width=True)

            if add_submitted:
                if new_name.strip():
                    if not df_players.empty and new_name.strip() in df_players["選手名"].values:
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

        edited_df = st.data_editor(
            df_players,
            num_rows="dynamic",
            column_config={
                "選手名": st.column_config.TextColumn("選手名", required=True),
                "背番号": st.column_config.TextColumn("背番号"),
                "成績非表示": st.column_config.CheckboxColumn("成績非表示", default=False, help="チェックを入れるとチーム成績等のランキングから消えます"),
                "オーダー非表示": st.column_config.CheckboxColumn("オーダー非表示", default=False, help="チェックを入れると試合入力のプルダウンから消えます"),
            },
            use_container_width=True,
            key="player_editor"
        )

        if st.button("💾 選手情報の変更を保存", type="primary", key="save_player_btn"):
            try:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_name, data=edited_df)
                st.cache_data.clear()
                st.success("✅ 選手情報を更新しました！")
                import time
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {e}")

    # ========================================================
    # Tab 2: 相手チーム管理
    # ========================================================
    with tab_opponent:
        ws_opp_name = "相手チーム登録"
        
        try:
            df_opponents = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws_opp_name)
        except Exception:
            df_opponents = pd.DataFrame(columns=["チーム名"])

        if "チーム名" not in df_opponents.columns:
            df_opponents["チーム名"] = None

        with st.form(key="add_opp_form", clear_on_submit=True):
            st.subheader("➕ 新規相手チームの追加")
            col_opp_name, col_opp_btn = st.columns([3, 1])
            with col_opp_name:
                new_opp_name = st.text_input("チーム名", placeholder="例：〇〇クラブ")
            with col_opp_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                opp_submitted = st.form_submit_button("追加する", type="secondary", use_container_width=True)

            if opp_submitted:
                if new_opp_name.strip():
                    if not df_opponents.empty and new_opp_name.strip() in df_opponents["チーム名"].values:
                        st.warning(f"「{new_opp_name.strip()}」は既に登録されています。")
                    else:
                        new_opp_row = pd.DataFrame([{"チーム名": new_opp_name.strip()}])
                        updated_opp_df = pd.concat([df_opponents, new_opp_row], ignore_index=True)
                        try:
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_opp_name, data=updated_opp_df)
                            st.cache_data.clear()
                            st.success(f"✅ 相手チーム「{new_opp_name.strip()}」を追加しました！")
                            import time
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"追加エラー: {e}")
                else:
                    st.warning("チーム名を入力してください。")

        st.divider()
        st.subheader("📋 相手チーム一覧・編集")

        edited_opp_df = st.data_editor(
            df_opponents,
            num_rows="dynamic",
            column_config={
                "チーム名": st.column_config.TextColumn("チーム名", required=True),
            },
            use_container_width=True,
            key="opponent_editor"
        )

        if st.button("💾 相手チームの変更を保存", type="primary", key="save_opp_btn"):
            try:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_opp_name, data=edited_opp_df)
                st.cache_data.clear()
                st.success("✅ 相手チーム情報を更新しました！")
                import time
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {e}")

    # ========================================================
    # Tab 3: グラウンド管理
    # ========================================================
    with tab_ground:
        ws_ground_name = "グラウンド登録"
        
        try:
            df_grounds = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=ws_ground_name)
        except Exception:
            df_grounds = pd.DataFrame(columns=["グラウンド名"])

        if "グラウンド名" not in df_grounds.columns:
            df_grounds["グラウンド名"] = None

        with st.form(key="add_ground_form", clear_on_submit=True):
            st.subheader("➕ 新規グラウンドの追加")
            col_g_name, col_g_btn = st.columns([3, 1])
            with col_g_name:
                new_ground_name = st.text_input("グラウンド名", placeholder="例：〇〇球場")
            with col_g_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                ground_submitted = st.form_submit_button("追加する", type="secondary", use_container_width=True)

            if ground_submitted:
                if new_ground_name.strip():
                    if not df_grounds.empty and new_ground_name.strip() in df_grounds["グラウンド名"].values:
                        st.warning(f"「{new_ground_name.strip()}」は既に登録されています。")
                    else:
                        new_g_row = pd.DataFrame([{"グラウンド名": new_ground_name.strip()}])
                        updated_g_df = pd.concat([df_grounds, new_g_row], ignore_index=True)
                        try:
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_ground_name, data=updated_g_df)
                            st.cache_data.clear()
                            st.success(f"✅ グラウンド「{new_ground_name.strip()}」を追加しました！")
                            import time
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"追加エラー: {e}")
                else:
                    st.warning("グラウンド名を入力してください。")

        st.divider()
        st.subheader("📋 グラウンド一覧・編集")

        edited_g_df = st.data_editor(
            df_grounds,
            num_rows="dynamic",
            column_config={
                "グラウンド名": st.column_config.TextColumn("グラウンド名", required=True),
            },
            use_container_width=True,
            key="ground_editor"
        )

        if st.button("💾 グラウンドの変更を保存", type="primary", key="save_ground_btn"):
            try:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_ground_name, data=edited_g_df)
                st.cache_data.clear()
                st.success("✅ グラウンド情報を更新しました！")
                import time
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"保存エラー: {e}")