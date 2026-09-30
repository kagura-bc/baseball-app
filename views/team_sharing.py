import re
import pandas as pd
from config.settings import SPREADSHEET_URL, TARGET_COLUMNS
from streamlit_gsheets import GSheetsConnection
import streamlit as st


def show_team_sharing_tab():
    """試合入力ページ内に埋め込むデータ共有タブ関数"""
    st.markdown("### 🤝 チーム間データ共有・連携")

    # 💡 ログイン中チームのスプレッドシートURLを取得（未設定時はデフォルト）
    my_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
    conn = st.connection("gsheets", type=GSheetsConnection)

    # 💡 新規チーム登録タブ(tab3)を削除し、2タブ構成に変更
    tab1, tab2 = st.tabs([
        "🎯 自チームの次戦オーダー登録",
        "📥 相手チームのオーダー取得・連携",
    ])

    # ==========================================
    # タブ1: 自チームの次戦オーダー登録・保存
    # ==========================================
    with tab1:
        st.info(
            "ここで登録・保存したスタメンおよびベンチ入り選手（控え）情報が、対戦時に相手チーム（ホスト）の画面へ共有されます。"
        )

        try:
            df_my_players = conn.read(
                spreadsheet=my_url, worksheet="選手登録", ttl=0
            )
            if "オーダー非表示" in df_my_players.columns:
                df_my_players = df_my_players[df_my_players["オーダー非表示"] != True]

            player_list = (
                df_my_players["選手名"].dropna().tolist()
                if "選手名" in df_my_players.columns
                else []
            )
            player_num_map = {}
            if "背番号" in df_my_players.columns:
                for _, r in df_my_players.iterrows():
                    num_str = str(int(r["背番号"])) if pd.notna(r["背番号"]) else ""
                    player_num_map[r["選手名"]] = num_str

        except Exception as e:
            st.error(f"「選手登録」シートの読み込みに失敗しました: {e}")
            player_list = []
            player_num_map = {}

        positions = [
            "投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控え"
        ]

        try:
            df_existing_order = conn.read(
                spreadsheet=my_url, worksheet="次戦オーダー", ttl=0
            )
        except Exception:
            df_existing_order = pd.DataFrame()

        existing_starter_map = {}
        existing_bench_players = []

        if not df_existing_order.empty:
            for _, r in df_existing_order.iterrows():
                order_val = str(r.get("打順", "")).strip()
                pos_val = str(r.get("守備位置", "")).strip()
                p_name = str(r.get("選手名", "")).strip()

                if p_name in player_list:
                    if order_val.isdigit() and 1 <= int(order_val) <= 9:
                        existing_starter_map[int(order_val)] = {
                            "pos": pos_val if pos_val in positions else "投",
                            "name": p_name
                        }
                    elif order_val == "控え" or pos_val == "控え":
                        if p_name not in existing_bench_players:
                            existing_bench_players.append(p_name)

        with st.form("next_order_form"):
            st.markdown("##### ⚾ 1番〜9番のスタメンを設定")
            new_order_data = []
            selected_starters = []

            for i in range(1, 10):
                def_pos = "投"
                def_player = player_list[0] if player_list else ""

                if i in existing_starter_map:
                    def_pos = existing_starter_map[i]["pos"]
                    def_player = existing_starter_map[i]["name"]

                c_num, c_pos, c_name = st.columns([1, 2, 4])
                with c_num:
                    st.write("")
                    st.markdown(f"**{i}番**")

                with c_pos:
                    pos_idx = positions.index(def_pos) if def_pos in positions else 0
                    pos_val = st.selectbox(
                        f"守備_{i}",
                        positions,
                        index=pos_idx,
                        key=f"my_pos_{i}",
                        label_visibility="collapsed",
                    )

                with c_name:
                    p_idx = (
                        player_list.index(def_player) if def_player in player_list else 0
                    )
                    player_val = st.selectbox(
                        f"選手_{i}",
                        player_list,
                        index=p_idx,
                        key=f"my_player_{i}",
                        label_visibility="collapsed",
                    )

                num_val = player_num_map.get(player_val, "")
                selected_starters.append(player_val)

                new_order_data.append({
                    "打順": i,
                    "守備位置": pos_val,
                    "選手名": player_val,
                    "背番号": num_val,
                })

            st.write("---")
            st.markdown("##### 🏃 ベンチ入り（控え）選手を設定")
            st.caption("スタメン以外のベンチ入り・控え選手を選択してください（複数選択可）。")

            available_bench_options = [p for p in player_list if p not in selected_starters]
            default_bench_selected = [p for p in existing_bench_players if p in available_bench_options]

            selected_bench = st.multiselect(
                "控え選手を選択",
                options=available_bench_options,
                default=default_bench_selected,
                key="my_bench_players",
                label_visibility="collapsed"
            )

            for b_player in selected_bench:
                num_val = player_num_map.get(b_player, "")
                new_order_data.append({
                    "打順": "控え",
                    "守備位置": "控え",
                    "選手名": b_player,
                    "背番号": num_val,
                })

            st.write("")
            submitted = st.form_submit_button(
                "💾 オーダー（スタメン＋控え）を「次戦オーダー」に保存する",
                use_container_width=True,
            )

            if submitted:
                df_save = pd.DataFrame(new_order_data)
                # 💡 PyArrowの型変換エラーを防ぐため「打順」カラムを文字列型(str)に統一
                if "打順" in df_save.columns:
                    df_save["打順"] = df_save["打順"].astype(str)

                try:
                    conn.update(
                        spreadsheet=my_url, worksheet="次戦オーダー", data=df_save
                    )
                    st.success("✅ 次戦オーダー（スタメン＋控え）を正常に保存しました！")
                    st.rerun()
                except Exception as e:
                    st.error(f"「次戦オーダー」シートの更新に失敗しました: {e}")

    # ==========================================
    # タブ2: 相手チームのオーダー取得・連携
    # ==========================================
    with tab2:
        st.info(
            "対戦相手のチームを選択し、相手のスプレッドシートにある「次戦オーダー」を取得して成績入力ページへ連携できます。"
        )

        try:
            df_opp_master = conn.read(
                spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録", ttl=0
            )
        except Exception as e:
            df_opp_master = pd.DataFrame()
            st.error(f"「相手チーム登録」シートの読み込みに失敗しました: {e}")

        if not df_opp_master.empty and "チーム名" in df_opp_master.columns:
            opp_names = df_opp_master["チーム名"].dropna().tolist()
            selected_opp = st.selectbox(
                "対戦相手（チーム）を選択", opp_names, key="select_opp_tab2"
            )

            if selected_opp:
                row_data = df_opp_master[
                    df_opp_master["チーム名"] == selected_opp
                ].iloc[0]

                url_col = None
                for col in ["spreadsheet_url", "スプレッドシートURL", "URL"]:
                    if col in df_opp_master.columns:
                        url_col = col
                        break

                if url_col and pd.notna(row_data[url_col]):
                    target_url = row_data[url_col]
                    st.success(
                        f"対戦相手 **{selected_opp}** のスプレッドシートURLを特定しました！"
                    )
                    st.code(target_url, language="text")

                    c_btn1, c_btn2 = st.columns(2)

                    with c_btn1:
                        if st.button(
                            "📥 相手の「次戦オーダー」を取得",
                            use_container_width=True,
                            key="btn_get_order",
                        ):
                            try:
                                with st.spinner(f"{selected_opp} のオーダーを取得中..."):
                                    df_opp_order = conn.read(
                                        spreadsheet=target_url,
                                        worksheet="次戦オーダー",
                                        ttl=0,
                                    )

                                st.session_state["fetched_opp_order"] = df_opp_order
                                st.session_state["fetched_opp_name"] = selected_opp
                                st.success(f"**{selected_opp}** の「次戦オーダー」取得成功！")

                            except Exception as e:
                                st.error(
                                    f"相手の「次戦オーダー」の取得に失敗しました。\n詳細: {e}"
                                )

                    with c_btn2:
                        if st.button(
                            "📋 相手の「全選手登録」を取得",
                            use_container_width=True,
                            key="btn_get_players",
                        ):
                            try:
                                with st.spinner(f"{selected_opp} の全選手名簿を取得中..."):
                                    df_opp_players = conn.read(
                                        spreadsheet=target_url, worksheet="選手登録", ttl=0
                                    )

                                st.session_state["fetched_opp_players"] = df_opp_players
                                st.success(
                                    f"**{selected_opp}** の「全選手登録」取得成功！"
                                )

                            except Exception as e:
                                st.error(
                                    f"相手の「全選手登録」の取得に失敗しました。\n詳細: {e}"
                                )

                    if "fetched_opp_order" in st.session_state and st.session_state.get(
                        "fetched_opp_name"
                    ) == selected_opp:
                        df_fetched = st.session_state["fetched_opp_order"]

                        st.write("---")
                        st.markdown(f"#### 📋 {selected_opp} の「次戦オーダー」")
                        st.dataframe(df_fetched, use_container_width=True)

                        if st.button(
                            "⚾️ このオーダー（スタメン＋控え）を試合成績入力画面（相手打順・ベンチ）に反映する",
                            type="primary",
                            use_container_width=True,
                            key="btn_apply_opp_order",
                        ):
                            valid_positions = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指"]

                            starters = []
                            bench_players = []

                            for i, row in df_fetched.iterrows():
                                order_str = str(row.get("打順", "")).strip()
                                pos_str = str(row.get("守備位置", "未選択")).strip()
                                name_str = str(row.get("選手名", "選手")).strip()

                                if order_str == "控え" or pos_str == "控え":
                                    if name_str not in bench_players:
                                        bench_players.append(name_str)
                                else:
                                    starters.append({
                                        "pos": pos_str if pos_str in valid_positions else "未選択",
                                        "name": name_str
                                    })

                            st.session_state["opp_batter_count"] = max(9, len(starters))

                            for idx, s in enumerate(starters):
                                st.session_state[f"opp_sp_{idx}"] = s["pos"]
                                st.session_state[f"opp_sn_{idx}"] = s["name"]

                            for idx in range(len(starters), 20):
                                st.session_state.pop(f"opp_sp_{idx}", None)
                                st.session_state.pop(f"opp_sn_{idx}", None)

                            st.session_state["persistent_opp_bench"] = bench_players
                            st.session_state["opp_bench_selection_widget"] = bench_players

                            st.success(
                                f"✅ {selected_opp} のオーダー（スタメン {len(starters)}名 ＋ ベンチ控え {len(bench_players)}名）を反映しました！控え選手は選手選択肢から選択可能です。"
                            )

                    if "fetched_opp_players" in st.session_state:
                        st.write("---")
                        st.markdown(f"#### 👥 {selected_opp} の「全選手登録」")
                        st.dataframe(
                            st.session_state["fetched_opp_players"],
                            use_container_width=True,
                        )

                else:
                    st.warning(
                        f"「相手チーム登録」シートに **{selected_opp}** のURLが設定されていません。"
                    )
        else:
            st.warning("「相手チーム登録」シートにデータが存在しません。")


# ==================================================
# 🤝 相手チームへの成績反転・共有処理関数
# ==================================================
def share_match_data_to_opponent(conn, host_team_name, target_opp, match_date_str, match_type, match_bat, match_pit):
    """
    ホストチームのスコアデータを相手チーム視点に反転させ、相手のスプレッドシートへ共有する関数
    """
    try:
        # 1. マスターシート（相手チーム登録）から相手チームのスプレッドシートURLを取得
        df_opp_master = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録", ttl=0)
        
        url_col = None
        for col in ["spreadsheet_url", "スプレッドシートURL", "URL"]:
            if col in df_opp_master.columns:
                url_col = col
                break

        if df_opp_master.empty or not url_col or target_opp not in df_opp_master["チーム名"].values:
            return False, f"「相手チーム登録」シートに **{target_opp}** のスプレッドシートURLが登録されていません。"

        opp_row = df_opp_master[df_opp_master["チーム名"] == target_opp].iloc[0]
        opp_sheet_url = opp_row[url_col]

        if not opp_sheet_url or pd.isna(opp_sheet_url):
            return False, f"**{target_opp}** のスプレッドシートURLが空欄です。"

        # 2. 相手チームのスプレッドシートから現在のデータ（打撃・投手）を取得
        df_opp_bat = conn.read(spreadsheet=opp_sheet_url, worksheet="打撃成績", ttl=0)
        df_opp_pit = conn.read(spreadsheet=opp_sheet_url, worksheet="投手成績", ttl=0)

        # 3. 相手シートの現在の最大IDを取得（ID列の自動採番用）
        max_bat_id = int(pd.to_numeric(df_opp_bat["ID"], errors='coerce').max()) if not df_opp_bat.empty and "ID" in df_opp_bat.columns and pd.notna(pd.to_numeric(df_opp_bat["ID"], errors='coerce').max()) else 0
        max_pit_id = int(pd.to_numeric(df_opp_pit["ID"], errors='coerce').max()) if not df_opp_pit.empty and "ID" in df_opp_pit.columns and pd.notna(pd.to_numeric(df_opp_pit["ID"], errors='coerce').max()) else 0

        # 4. 既存の同試合データが存在する場合は削除（二重送信・再送信時の上書き対策）
        if not df_opp_bat.empty and "日付" in df_opp_bat.columns:
            df_opp_bat["_d"] = pd.to_datetime(df_opp_bat["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            df_opp_bat = df_opp_bat[~((df_opp_bat["_d"] == match_date_str) & (df_opp_bat["対戦相手"] == host_team_name) & (df_opp_bat["試合種別"] == match_type))].drop(columns=["_d"])

        if not df_opp_pit.empty and "日付" in df_opp_pit.columns:
            df_opp_pit["_d"] = pd.to_datetime(df_opp_pit["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            df_opp_pit = df_opp_pit[~((df_opp_pit["_d"] == match_date_str) & (df_opp_pit["対戦相手"] == host_team_name) & (df_opp_pit["試合種別"] == match_type))].drop(columns=["_d"])

        # --------------------------------------------------
        # A. ホスト打撃成績 ➡ 相手の「投手成績」シートへ変換
        # --------------------------------------------------
        new_opp_pit_rows = match_bat.copy()
        if not new_opp_pit_rows.empty:
            new_opp_pit_rows["対戦相手"] = host_team_name  # 対戦相手を自チーム名に変更
            new_opp_pit_rows["ID"] = range(max_pit_id + 1, max_pit_id + 1 + len(new_opp_pit_rows))

        # --------------------------------------------------
        # B. ホスト投手成績 ➡ 相手の「打撃成績」シートへ変換
        # --------------------------------------------------
        new_opp_bat_rows = match_pit.copy()
        if not new_opp_bat_rows.empty:
            new_opp_bat_rows["対戦相手"] = host_team_name  # 対戦相手を自チーム名に変更
            new_opp_bat_rows["ID"] = range(max_bat_id + 1, max_bat_id + 1 + len(new_opp_bat_rows))

        # 5. データの結合
        updated_opp_bat = pd.concat([df_opp_bat, new_opp_bat_rows], ignore_index=True)
        updated_opp_pit = pd.concat([df_opp_pit, new_opp_pit_rows], ignore_index=True)

        # 💡 不要な内部用カラム（Year, _date_str, 日付_dt, _d 等）を除外して23列に固定
        valid_bat_cols = [c for c in TARGET_COLUMNS if c in updated_opp_bat.columns]
        valid_pit_cols = [c for c in TARGET_COLUMNS if c in updated_opp_pit.columns]

        updated_opp_bat = updated_opp_bat[valid_bat_cols]
        updated_opp_pit = updated_opp_pit[valid_pit_cols]

        conn.update(spreadsheet=opp_sheet_url, worksheet="打撃成績", data=updated_opp_bat)
        conn.update(spreadsheet=opp_sheet_url, worksheet="投手成績", data=updated_opp_pit)

        return True, f"🎉 **{target_opp}** のスプレッドシートへ試合データを正常に共有・登録しました！"

    except Exception as e:
        return False, f"共有処理中にエラーが発生しました: {e}"