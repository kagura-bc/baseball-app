import re
import pandas as pd
from config.settings import SPREADSHEET_URL
from streamlit_gsheets import GSheetsConnection
import streamlit as st


def show_team_sharing_page():
  st.markdown("### 🤝 チーム間データ共有・チーム管理機能")

  # 💡 ログイン中チームのスプレッドシートURLを取得（未設定時はデフォルト）
  my_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
  conn = st.connection("gsheets", type=GSheetsConnection)

  tab1, tab2, tab3 = st.tabs([
      "🎯 ① 自チームの次戦オーダー登録",
      "📥 ② 相手チームのオーダー取得・連携",
      "🆕 ③ 新規チーム登録（DB自動発行）",
  ])

  # ==========================================
  # タブ1: 自チームの次戦オーダー登録・保存
  # ==========================================
  with tab1:
    st.info(
        "ここで登録・保存したスタメン情報が、対戦時に相手チーム（ホスト）の画面へ共有されます。"
    )

    try:
      # 自チームの「選手登録」シートから読み込み
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
        "投",
        "捕",
        "一",
        "二",
        "三",
        "遊",
        "左",
        "中",
        "右",
        "指",
        "控え",
    ]

    try:
      # 自チームの「次戦オーダー」シートから既存設定を読み込み
      df_existing_order = conn.read(
          spreadsheet=my_url, worksheet="次戦オーダー", ttl=0
      )
    except Exception:
      df_existing_order = pd.DataFrame()

    with st.form("next_order_form"):
      st.markdown("##### ⚾ 1番〜9番のスタメンを設定")
      new_order_data = []

      for i in range(1, 10):
        def_pos = "投"
        def_player = player_list[0] if player_list else ""

        if not df_existing_order.empty and len(df_existing_order) >= i:
          row_ex = df_existing_order.iloc[i - 1]
          if "守備位置" in row_ex and row_ex["守備位置"] in positions:
            def_pos = row_ex["守備位置"]
          if "選手名" in row_ex and row_ex["選手名"] in player_list:
            def_player = row_ex["選手名"]

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
        new_order_data.append({
            "打順": i,
            "守備位置": pos_val,
            "選手名": player_val,
            "背番号": num_val,
        })

      st.write("")
      submitted = st.form_submit_button(
          "💾 このスタメンを「次戦オーダー」に保存する",
          use_container_width=True,
      )

      if submitted:
        df_save = pd.DataFrame(new_order_data)
        try:
          # 自チームの「次戦オーダー」シートへ保存
          conn.update(
              spreadsheet=my_url, worksheet="次戦オーダー", data=df_save
          )
          st.success("次戦オーダーを正常に保存しました！")
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
      # 全チームのリストが登録されているマスターシートから取得
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
                "⚾️ このオーダーを本日の試合成績入力画面（相手打順）に反映する",
                type="primary",
                use_container_width=True,
                key="btn_apply_opp_order",
            ):
              st.session_state["opp_batter_count"] = len(df_fetched)
              valid_positions = [
                  "投",
                  "捕",
                  "一",
                  "二",
                  "三",
                  "遊",
                  "左",
                  "中",
                  "右",
                  "指",
              ]
              for i, row in df_fetched.iterrows():
                pos = str(row.get("守備位置", "未選択"))
                name = str(row.get("選手名", "選手"))
                st.session_state[f"opp_sp_{i}"] = (
                    pos if pos in valid_positions else "未選択"
                )
                st.session_state[f"opp_sn_{i}"] = name

              st.success(
                  f"✅ {selected_opp} のオーダーを試合成績入力ページへ反映しました！「📝 試合データ入力」を開いて確認してください。"
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

  # ==========================================
  # タブ3: 新規チーム登録（マスターシートへの追加）
  # ==========================================
  with tab3:
    st.info("🔒 この機能はカグラ運営（管理者）専用です。")

    admin_pass = st.text_input(
        "🔑 運営用パスワードを入力してください",
        type="password",
        key="admin_lock_pass",
    )

    ADMIN_PASSWORD = "admin_kagura"

    if admin_pass == ADMIN_PASSWORD:
      st.success("🔓 運営認証が完了しました。")
      st.write("---")

      st.markdown("##### 💡 登録手順")
      st.caption(
          "1. Googleドライブで「ひな形スプレッドシート」を複製してください。\n"
          "2. 複製したシートのURLと、新しいチーム情報（名前・ID）を以下に入力して登録してください。"
      )

      with st.form("create_team_form"):
        new_team_name = st.text_input("チーム名（例: WISH）")
        new_team_id = st.text_input("希望するチームID（半角英数字 / 例: wish）")
        new_sheet_url = st.text_input(
            "複製したスプレッドシートのURL",
            placeholder="https://docs.google.com/spreadsheets/d/...",
        )
        admin_password_input = st.text_input(
            "発行する管理パスワード", value=f"{new_team_id}_admin"
        )
        viewer_password_input = st.text_input(
            "発行する閲覧パスワード", value=new_team_id
        )

        btn_create = st.form_submit_button(
            "🚀 新規チームをデータベースに登録する",
            use_container_width=True,
        )

        if btn_create:
          if not new_team_name or not new_team_id or not new_sheet_url:
            st.error("すべての項目を入力してください。")
          elif not re.match(r"^[a-zA-Z0-9_-]+$", new_team_id):
            st.error("チームIDは半角英数字で入力してください。")
          else:
            try:
              df_opp_check = conn.read(
                  spreadsheet=SPREADSHEET_URL,
                  worksheet="相手チーム登録",
                  ttl=0,
              )

              existing_ids = (
                  df_opp_check["チームID"].dropna().astype(str).tolist()
                  if "チームID" in df_opp_check.columns
                  else []
              )

              if new_team_id in existing_ids:
                st.error(
                    f"チームID '{new_team_id}'"
                    " はすでに使用されています。別のIDを指定してください。"
                )
              else:
                new_row = pd.DataFrame([{
                    "チーム名": new_team_name,
                    "チームID": new_team_id,
                    "スプレッドシートURL": new_sheet_url,
                    "管理パスワード": admin_password_input,
                    "閲覧パスワード": viewer_password_input,
                }])

                updated_opp_df = pd.concat(
                    [df_opp_check, new_row], ignore_index=True
                )
                conn.update(
                    spreadsheet=SPREADSHEET_URL,
                    worksheet="相手チーム登録",
                    data=updated_opp_df,
                )
                st.cache_data.clear()

                st.balloons()
                st.success(
                    f"🎉 新規チーム **【{new_team_name}】**"
                    " を正常に登録しました！"
                )
                st.code(
                    f"チームID: {new_team_id}\n"
                    f"管理パスワード: {admin_password_input}\n"
                    f"閲覧パスワード: {viewer_password_input}",
                    language="text",
                )

            except Exception as e:
              st.error(f"登録処理に失敗しました: {e}")
    elif admin_pass:
      st.error("運営用パスワードが違います。")