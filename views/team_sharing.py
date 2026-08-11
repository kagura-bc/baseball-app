import pandas as pd
from config.settings import SPREADSHEET_URL
from streamlit_gsheets import GSheetsConnection
import streamlit as st


def show_team_sharing_page():
  st.markdown("### 🤝 チーム間データ共有・スタメン取得テスト")
  st.info(
      "このページでは、別チームのGoogleスプレッドシート（URL）にアクセスし、"
      "相手チームの「選手登録」を自分のアプリ画面に読み込めるかをテストできます。"
  )

  conn = st.connection("gsheets", type=GSheetsConnection)

  # 1. 「相手チーム登録」シートの内容を取得
  try:
    df_opp_master = conn.read(
        spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録", ttl=0
    )
  except Exception as e:
    df_opp_master = pd.DataFrame()
    st.error(f"「相手チーム登録」シートの読み込みに失敗しました: {e}")

  if not df_opp_master.empty and "チーム名" in df_opp_master.columns:
    opp_names = df_opp_master["チーム名"].dropna().tolist()
    selected_opp = st.selectbox("対戦相手（チーム）を選択", opp_names)

    if selected_opp:
      row_data = df_opp_master[
          df_opp_master["チーム名"] == selected_opp
      ].iloc[0]

      # スプレッドシートURLが格納されているカラムを探す
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

        # 2. 相手のスプレッドシートにアクセスして「選手登録」を読み込む
        if st.button(
            "📥 相手チームの「選手登録」をこの画面に取得する",
            use_container_width=True,
        ):
          try:
            with st.spinner(
                f"{selected_opp} のデータベースにアクセス中..."
            ):
              # 💡 シート名を「選手一覧」から「選手登録」に修正
              df_opp_players = conn.read(
                  spreadsheet=target_url, worksheet="選手登録", ttl=0
              )

            st.success(
                f"取得成功！以下は **{selected_opp}** の「選手登録」の内容です。"
            )
            st.dataframe(df_opp_players, use_container_width=True)

            st.info(
                "💡 **今後できること:** このように相手の選手データを取得できれば、"
                "ホスト側のスタメン選択画面で「相手チームの選手」をプルダウンから直接選んで"
                "オーダーを組むことができるようになります。"
            )

          except Exception as e:
            st.error(
                f"相手のスプレッドシートから「選手登録」の読み込みに失敗しました。"
                f"サービスアカウントの共有権限やシート名が正しいか確認してください。\n詳細: {e}"
            )
      else:
        st.warning(
            f"「相手チーム登録」シートに **{selected_opp}** のスプレッドシートURL（列名: `spreadsheet_url` 等）が登録されていません。"
            "スプレッドシート側に対象チームのURLを入力してください。"
        )
  else:
    st.warning(
        "「相手チーム登録」シートにデータが見つからないか、「チーム名」列が存在しません。"
    )