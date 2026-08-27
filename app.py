import datetime
import pandas as pd
from config.settings import (
    MY_TEAM,
    OFFICIAL_GAME_TYPES,
    SPREADSHEET_URL,
)
from streamlit_gsheets import GSheetsConnection
import streamlit as st
from utils.db import load_batting_data, load_pitching_data
from utils.players import get_active_players
from utils.ui import fmt_player_name, load_css
from views import (
    analysis,
    batting,
    edit_data,
    ideal_order,
    personal_stats,
    pitching,
    player_management,
    team_sharing,
    team_stats,
)

ICON_URL = (
    "https://raw.githubusercontent.com/kagura-bc/baseball-app/main/static/logo-192.png?v=3"
)

st.set_page_config(page_title="KAGUSTA", page_icon=ICON_URL, layout="wide")

st.markdown(
    f'<link rel="apple-touch-icon" href="{ICON_URL}">', unsafe_allow_html=True
)

load_css()

# --- スマホ・タブレットでキーボードが出るのを防ぐ修正CSS ---
st.markdown(
    """
<style>
    div[data-baseweb="select"] input {
        caret-color: transparent !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 🔐 ロール制御付きログイン機能（ID & パスワード認証）
# ==========================================
if "is_logged_in" not in st.session_state:
  st.session_state["is_logged_in"] = False
  st.session_state["user_role"] = "viewer"  # "admin" または "viewer"
  st.session_state["my_spreadsheet_url"] = SPREADSHEET_URL
  st.session_state["my_team_name"] = MY_TEAM
  st.session_state["my_team_id"] = None


def show_login_screen():
  _, center, _ = st.columns([1, 10, 1])
  with center:
    st.write("")
    st.write("")
    st.markdown(
        f"""
<div style="display: flex; justify-content: center; align-items: center; margin-bottom: 20px;">
    <img src="{ICON_URL}" style="width: 350px; height: 350px; object-fit: contain;">
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("login_form_v5"):
      input_team_id = st.text_input("👤 チームID (例: kagura, wish)")
      input_password = st.text_input("🔑 パスワード", type="password")
      submitted = st.form_submit_button("ログイン", use_container_width=True)

      if submitted:
        conn = st.connection("gsheets", type=GSheetsConnection)
        try:
          df_teams = conn.read(
              spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録", ttl=0
          )

          matched = (
              df_teams[df_teams["チームID"].astype(str) == input_team_id]
              if "チームID" in df_teams.columns
              else pd.DataFrame()
          )

          if not matched.empty:
            target_row = matched.iloc[0]

            # パスワード列の参照（既存の「パスワード」列にも対応）
            admin_pass = str(
                target_row.get(
                    "管理パスワード", target_row.get("パスワード", "")
                )
            )
            viewer_pass = str(target_row.get("閲覧パスワード", ""))

            # 判定ロジック
            if input_password == admin_pass and admin_pass != "":
              st.session_state["user_role"] = "admin"
            elif input_password == viewer_pass and viewer_pass != "":
              st.session_state["user_role"] = "viewer"
            elif input_password == "kagura" and input_team_id == "kagura":
              st.session_state["user_role"] = "admin"
            else:
              st.error("パスワードが違います。")
              st.stop()

            st.session_state["is_logged_in"] = True
            st.session_state["my_team_id"] = input_team_id
            st.session_state["my_team_name"] = target_row.get(
                "チーム名", input_team_id
            )

            # 専用スプレッドシートURLのセット
            url_col = next(
                (
                    c
                    for c in ["spreadsheet_url", "スプレッドシートURL", "URL"]
                    if c in df_teams.columns
                ),
                None,
            )
            if url_col and pd.notna(target_row.get(url_col)):
              st.session_state["my_spreadsheet_url"] = target_row[url_col]
            else:
              st.session_state["my_spreadsheet_url"] = SPREADSHEET_URL

            st.success(
                f"{st.session_state['my_team_name']} としてログインしました！"
            )
            st.rerun()
          else:
            st.error("チームIDが存在しません。")
        except Exception as e:
          st.error(f"ログイン中にエラーが発生しました: {e}")


if not st.session_state["is_logged_in"]:
  show_login_screen()
  st.stop()

# ==========================================
# 📊 データ動的読み込み
# ==========================================
MY_DB_URL = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)

# 💡 MY_DB_URL を引数として明示的に渡す
df_batting = load_batting_data(spreadsheet_url=MY_DB_URL)
df_pitching = load_pitching_data(spreadsheet_url=MY_DB_URL)

ALL_PLAYERS, PLAYER_NUMBERS = get_active_players(spreadsheet_url=MY_DB_URL)
st.session_state["shared_player_numbers"] = PLAYER_NUMBERS


def local_fmt(name):
  return fmt_player_name(
      name, st.session_state.get("shared_player_numbers", {})
  )


@st.cache_data(ttl=60)
def get_cached_grounds(target_url):
  conn = st.connection("gsheets", type=GSheetsConnection)
  try:
    df_ground = conn.read(
        spreadsheet=target_url, worksheet="グラウンド登録", ttl=0
    )
    return (
        df_ground["グラウンド名"].dropna().tolist()
        if "グラウンド名" in df_ground.columns
        else ["その他"]
    )
  except Exception:
    return ["その他"]


@st.cache_data(ttl=60)
def get_cached_opponents(target_url):
  conn = st.connection("gsheets", type=GSheetsConnection)
  try:
    df_opp = conn.read(
        spreadsheet=target_url, worksheet="相手チーム登録", ttl=0
    )
    return (
        df_opp["チーム名"].dropna().tolist()
        if "チーム名" in df_opp.columns
        else ["その他"]
    )
  except Exception:
    return ["その他"]


GROUND_LIST = get_cached_grounds(MY_DB_URL)
OPPONENTS_LIST = get_cached_opponents(MY_DB_URL)


def safe_index(lst, val):
  try:
    return lst.index(val)
  except ValueError:
    return 0


# ==========================================
# 🧭 ナビゲーション（権限に応じたメニューの切り替え）
# ==========================================
st.sidebar.markdown(f"### ⚾️ {st.session_state.get('my_team_name', 'KAGUSTA')}")

# ログイン権限に応じて表示メニューを変更
if st.session_state.get("user_role") == "admin":
  # 管理者権限：入力・編集含む全メニュー
  menu_options = [
      " 📝 試合データ入力",
      " 🏆 チーム成績",
      " 📊 個人成績",
      " 📈 データ分析",
      " 🔧 データ修正",
      " 👥 選手管理",
      " 🤝 チーム間共有（テスト）",
  ]
else:
  # 閲覧モード：viewer.pyと同様の閲覧機能のみ
  menu_options = [" 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析"]

page = st.sidebar.radio("メニュー", menu_options)

# サイドバー下部にログアウトボタンを設置
if st.sidebar.button("🚪 ログアウト", use_container_width=True):
  st.session_state["is_logged_in"] = False
  st.rerun()

# ==========================================
# 💻 メイン画面の表示制御
# ==========================================
if page == " 📝 試合データ入力":

  st.markdown("### 📝 試合データ入力")

  # --- URLパラメータからの基本復元 ---
  query_date = st.query_params.get(
      "date", datetime.date.today().strftime("%Y-%m-%d")
  )
  query_opp = st.query_params.get("opp", "")
  query_match = st.query_params.get("match", "")
  query_ground = st.query_params.get("ground", "")
  query_order = st.query_params.get("order", "")
  query_scorer = st.query_params.get("scorer", "")

  # ⚙️ 試合設定枠
  with st.expander("⚙️ 試合設定", expanded=True):
    try:
      default_date = datetime.datetime.strptime(query_date, "%Y-%m-%d").date()
    except ValueError:
      default_date = datetime.date.today()

    c1, c2, c3 = st.columns(3)

    # --- 1列目：試合日 ---
    with c1:
      selected_date = st.date_input(
          "試合日", value=default_date, key="main_selected_date"
      )
      selected_date_str = selected_date.strftime("%Y-%m-%d")

    # 🌟 【自動復元 & データベース存在確認ロジック】
    auto_opp = ""
    auto_match = ""
    auto_ground = ""
    auto_scorer = ""
    auto_order = ""
    has_data_for_date = False

    if not df_batting.empty and "日付" in df_batting.columns:
      df_batting["_date_str"] = pd.to_datetime(
          df_batting["日付"], errors="coerce"
      ).dt.strftime("%Y-%m-%d")
      date_matched = df_batting[df_batting["_date_str"] == selected_date_str]
      if not date_matched.empty:
        has_data_for_date = True
        latest_r = date_matched.iloc[-1]
        auto_opp = (
            str(latest_r.get("対戦相手", ""))
            if pd.notna(latest_r.get("対戦相手", ""))
            else ""
        )
        auto_match = (
            str(latest_r.get("試合種別", ""))
            if pd.notna(latest_r.get("試合種別", ""))
            else ""
        )
        auto_ground = (
            str(latest_r.get("グラウンド", ""))
            if pd.notna(latest_r.get("グラウンド", ""))
            else ""
        )
        auto_scorer = (
            str(latest_r.get("スコアラー", ""))
            if pd.notna(latest_r.get("スコアラー", ""))
            else ""
        )
        auto_order = (
            str(latest_r.get("攻守", ""))
            if pd.notna(latest_r.get("攻守", ""))
            else ""
        )

    if has_data_for_date:
      res_opp = auto_opp
      res_match = auto_match
      res_ground = auto_ground
      res_scorer = auto_scorer
      res_order = auto_order
    else:
      res_opp = ""
      res_match = ""
      res_ground = ""
      res_scorer = ""
      res_order = ""
      for q_key in ["opp", "match", "ground", "order", "scorer"]:
        if q_key in st.query_params:
          del st.query_params[q_key]

    p_list = ALL_PLAYERS
    scorer_key = "scorer_name_ui"
    if scorer_key not in st.session_state:
      st.session_state[scorer_key] = res_scorer if res_scorer else None

    match_options = OFFICIAL_GAME_TYPES + ["練習試合", "その他"]
    match_key = f"main_match_type_{selected_date_str}"
    if match_key not in st.session_state:
      st.session_state[match_key] = res_match if res_match else None

    ground_options = (
        GROUND_LIST if "その他" in GROUND_LIST else GROUND_LIST + ["その他"]
    )
    ground_key = f"main_selected_ground_{selected_date_str}"
    if ground_key not in st.session_state:
      st.session_state[ground_key] = res_ground if res_ground else None

    opp_options = (
        OPPONENTS_LIST if "その他" in OPPONENTS_LIST else OPPONENTS_LIST + ["その他"]
    )
    opp_key = f"main_selected_opp_{selected_date_str}"
    if opp_key not in st.session_state:
      st.session_state[opp_key] = res_opp if res_opp else None

    order_list = ["先攻 (表)", "後攻 (裏)"]
    order_key = f"main_kagura_order_{selected_date_str}"
    if order_key not in st.session_state:
      st.session_state[order_key] = res_order if res_order else None

    with c1:
      st.write("")
      st.markdown(
          "<div style='font-size:14px; font-weight:bold;"
          " margin-bottom:4px;'>スコアラー</div>",
          unsafe_allow_html=True,
      )
      saved_scorer = st.session_state.get(scorer_key)
      scorer_label = (
          f"🟢 {local_fmt(saved_scorer)} 🔽"
          if saved_scorer
          else "スコアラー選択 🔽"
      )
      with st.popover(scorer_label, use_container_width=True):
        st.markdown("##### 👥 スコアラーを選択")
        st.pills(
            "スコアラー選択",
            p_list,
            format_func=local_fmt,
            key=scorer_key,
            label_visibility="collapsed",
        )
      if saved_scorer:
        st.session_state["persistent_scorer"] = saved_scorer

    with c2:
      st.markdown(
          "<div style='font-size:14px; font-weight:bold;"
          " margin-bottom:4px;'>試合区分</div>",
          unsafe_allow_html=True,
      )
      cur_match = st.session_state.get(match_key)
      match_label = f"🟢 {cur_match} 🔽" if cur_match else "試合区分選択 🔽"
      with st.popover(match_label, use_container_width=True):
        st.markdown("##### ⚾ 試合区分を選択")
        st.pills(
            "試合区分選択",
            match_options,
            key=match_key,
            label_visibility="collapsed",
        )

      st.write("")
      st.markdown(
          "<div style='font-size:14px; font-weight:bold;"
          " margin-bottom:4px;'>グラウンド</div>",
          unsafe_allow_html=True,
      )
      cur_ground = st.session_state.get(ground_key)
      ground_label = f"🟢 {cur_ground} 🔽" if cur_ground else "グラウンド選択 🔽"
      with st.popover(ground_label, use_container_width=True):
        st.markdown("##### 🏟️ グラウンドを選択")
        st.pills(
            "グラウンド選択",
            ground_options,
            key=ground_key,
            label_visibility="collapsed",
        )

      if cur_ground == "Other" or cur_ground == "その他":
        ground_name_input = st.text_input(
            "グラウンド名入力",
            value=res_ground if res_ground else "その他グラウンド",
            key=f"main_custom_ground_{selected_date_str}",
        )
      else:
        ground_name_input = cur_ground if cur_ground else ""

    with c3:
      st.markdown(
          "<div style='font-size:14px; font-weight:bold;"
          " margin-bottom:4px;'>相手チーム</div>",
          unsafe_allow_html=True,
      )
      cur_opp = st.session_state.get(opp_key)
      opp_label = f"🟢 {cur_opp} 🔽" if cur_opp else "相手チーム選択 🔽"
      with st.popover(opp_label, use_container_width=True):
        st.markdown("##### 🆚 相手チームを選択")
        st.pills(
            "相手チーム選択",
            opp_options,
            key=opp_key,
            label_visibility="collapsed",
        )

      if cur_opp == "Other" or cur_opp == "その他":
        opp_team_input = st.text_input(
            "相手チーム名入力",
            value=res_opp if res_opp else "相手チーム",
            key=f"main_custom_opp_{selected_date_str}",
        )
      else:
        opp_team_input = cur_opp if cur_opp else ""

      st.write("")
      st.markdown(
          "<div style='font-size:14px; font-weight:bold;"
          " margin-bottom:4px;'>攻守</div>",
          unsafe_allow_html=True,
      )
      cur_order = st.session_state.get(order_key)
      order_label = f"🟢 {cur_order} 🔽" if cur_order else "攻守選択 🔽"
      with st.popover(order_label, use_container_width=True):
        st.markdown("##### 🔄 攻守を選択")
        st.pills(
            "攻守選択", order_list, key=order_key, label_visibility="collapsed"
        )
      kagura_order_input = cur_order if cur_order else ""

    match_type_input = st.session_state.get(match_key, "")

    st.write("")
    if st.button("⚙️ 試合設定を決定", use_container_width=True):
      st.query_params["date"] = selected_date_str
      st.query_params["opp"] = opp_team_input
      st.query_params["match"] = match_type_input
      st.query_params["ground"] = ground_name_input
      st.query_params["order"] = kagura_order_input
      st.query_params["scorer"] = saved_scorer if saved_scorer else ""

      st.session_state["applied_settings"] = {
          "date": selected_date_str,
          "scorer": saved_scorer,
          "match_type": match_type_input,
          "ground": ground_name_input,
          "opp": opp_team_input,
          "order": kagura_order_input,
      }
      st.success("試合設定を反映しました！")
      st.rerun()

  if (
      "applied_settings" not in st.session_state
      or st.session_state["applied_settings"]["date"] != selected_date_str
  ):
    st.session_state["applied_settings"] = {
        "date": selected_date_str,
        "scorer": st.session_state.get(scorer_key),
        "match_type": st.session_state.get(match_key, ""),
        "ground": ground_name_input,
        "opp": opp_team_input,
        "order": st.session_state.get(order_key, ""),
    }

  applied = st.session_state["applied_settings"]
  current_date_str = applied["date"]
  match_type = applied["match_type"]
  ground_name = applied["ground"]
  opp_team = applied["opp"]
  kagura_order = applied["order"]

  st.write("")

  tab_batting, tab_pitching, tab_ideal, tab_edit = st.tabs([
      " 🏠 打撃成績入力",
      " 🔥 投手成績入力",
      " 🎯 理想オーダー作成",
      " 🔧 データ修正",
  ])

  with tab_batting:
    batting.show_batting_page(
        df_batting,
        df_pitching,
        current_date_str,
        match_type,
        ground_name,
        opp_team,
        kagura_order,
    )

  with tab_pitching:
    pitching.show_pitching_page(
        df_batting,
        df_pitching,
        current_date_str,
        match_type,
        ground_name,
        opp_team,
        kagura_order,
    )

  with tab_ideal:
    ideal_order.show_ideal_order_tab(df_batting, df_pitching=df_pitching)

  with tab_edit:
    edit_data.show_edit_page(df_batting, df_pitching)

elif page == " 🏆 チーム成績":
  team_stats.show_team_stats(df_batting, df_pitching)

elif page == " 📊 個人成績":
  personal_stats.show_personal_stats(df_batting, df_pitching)

elif page == " 📈 データ分析":
  analysis.show_analysis_page(df_batting, df_pitching)

elif page == " 🔧 データ修正":
  edit_data.show_edit_page(df_batting, df_pitching)

elif page == " 👥 選手管理":
  player_management.show_player_management()

elif page == " 🤝 チーム間共有（テスト）":
  team_sharing.show_team_sharing_page()