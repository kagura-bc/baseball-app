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

            admin_pass = str(
                target_row.get(
                    "管理パスワード", target_row.get("パスワード", "")
                )
            )
            viewer_pass = str(target_row.get("閲覧パスワード", ""))

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
# 📊 当日投手成績・球数分析表示用ヘルパー関数
# ==========================================
def render_today_pitching_analysis(df_batting, df_pitching, target_date_str, match_type, opp_team, all_players):
    st.markdown("#### 📊 投手成績分析")

    target_dt_str = pd.to_datetime(target_date_str, errors='coerce').strftime('%Y-%m-%d')

    today_p_df = pd.DataFrame()
    if not df_pitching.empty and "日付" in df_pitching.columns:
        df_pitching["_date_str"] = pd.to_datetime(df_pitching["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        today_p_df = df_pitching[
            (df_pitching["_date_str"] == target_dt_str) &
            (df_pitching["対戦相手"].astype(str).str.strip() == str(opp_team).strip()) &
            (df_pitching["試合種別"].astype(str).str.strip() == str(match_type).strip())
        ].copy()

    today_b_df = pd.DataFrame()
    if not df_batting.empty and "日付" in df_batting.columns:
        df_batting["_date_str"] = pd.to_datetime(df_batting["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        today_b_df = df_batting[
            (df_batting["_date_str"] == target_dt_str) &
            (df_batting["対戦相手"].astype(str).str.strip() == str(opp_team).strip()) &
            (df_batting["試合種別"].astype(str).str.strip() == str(match_type).strip())
        ].copy()

    if today_p_df.empty and today_b_df.empty:
        st.info("本日の試合データがまだ登録されていません。")
        return

    clean_all_players = set([p.split(" (")[0].strip() for p in all_players if p])

    p_pitchers = []
    if not today_p_df.empty and "投手名" in today_p_df.columns:
        p_pitchers = today_p_df["投手名"].dropna().astype(str).str.strip().tolist()

    b_pitchers = []
    if not today_b_df.empty and "投手名" in today_b_df.columns:
        b_pitchers = today_b_df["投手名"].dropna().astype(str).str.strip().tolist()

    all_pitcher_names = [p for p in dict.fromkeys(p_pitchers + b_pitchers) if p not in ["", "nan", "None", "不明"]]

    my_team_pitchers = []
    opp_team_pitchers = []

    for p in all_pitcher_names:
        clean_p = p.split(" (")[0].strip()
        if (p in p_pitchers) or (clean_p in clean_all_players):
            if p not in my_team_pitchers:
                my_team_pitchers.append(p)
        else:
            if p not in opp_team_pitchers:
                opp_team_pitchers.append(p)

    tab_my, tab_opp = st.tabs(["🏠 自チーム", "🆚 相手チーム"])

    def display_pitcher_group(pitcher_list, is_my_team=True):
        if not pitcher_list:
            team_label = "自チーム" if is_my_team else "相手チーム"
            st.info(f"{team_label}の登板投手データが見つかりません。")
            return

        summary_rows = []
        for p_name in pitcher_list:
            p_sub = today_p_df[today_p_df["投手名"].astype(str).str.strip() == p_name] if not today_p_df.empty else pd.DataFrame()
            
            outs = pd.to_numeric(p_sub.get("アウト数", 0), errors='coerce').sum() if not p_sub.empty else 0
            hits = pd.to_numeric(p_sub.get("被安打", 0), errors='coerce').sum() if not p_sub.empty else 0
            so = pd.to_numeric(p_sub.get("奪三振", 0), errors='coerce').sum() if not p_sub.empty else 0
            runs = pd.to_numeric(p_sub.get("失点", 0), errors='coerce').sum() if not p_sub.empty else 0
            er = pd.to_numeric(p_sub.get("自責点", 0), errors='coerce').sum() if not p_sub.empty else 0

            bb_hbp = 0
            if not p_sub.empty and "結果" in p_sub.columns:
                bb_hbp += len(p_sub[p_sub["結果"].astype(str).isin(["四球", "死球", "四死球"])])

            b_sub = today_b_df[today_b_df["投手名"].astype(str).str.strip() == p_name] if not today_b_df.empty else pd.DataFrame()
            
            if not b_sub.empty and "結果" in b_sub.columns:
                if p_sub.empty:
                    bb_hbp += len(b_sub[b_sub["結果"].astype(str).isin(["四球", "死球", "四死球"])])
                    hits += len(b_sub[b_sub["結果"].astype(str).isin(["単打", "二塁打", "三塁打", "本塁打"])])
                    so += len(b_sub[b_sub["結果"].astype(str).isin(["三振", "振り逃げ三振"])])
                    runs += pd.to_numeric(b_sub.get("得点", 0), errors='coerce').sum()

            pitches = 0
            strikes = 0
            balls = 0
            
            if not b_sub.empty:
                pitches = pd.to_numeric(b_sub.get("球数", 0), errors='coerce').sum()
                strikes = pd.to_numeric(b_sub.get("ストライク", 0), errors='coerce').sum()
                balls = pd.to_numeric(b_sub.get("ボール", 0), errors='coerce').sum()

            inn_full = int(outs // 3)
            inn_rem = int(outs % 3)
            inn_str = f"{inn_full}" if inn_rem == 0 else f"{inn_full}.{inn_rem}"

            strike_rate = (strikes / pitches * 100) if pitches > 0 else 0.0

            summary_rows.append({
                "投手名": local_fmt(p_name) if is_my_team else p_name,
                "投球回": f"{inn_str} 回",
                "総球数": int(pitches),
                "ストライク": int(strikes),
                "ボール": int(balls),
                "ストライク率": f"{strike_rate:.1f}%",
                "被安打": int(hits),
                "奪三振": int(so),
                "四死球": int(bb_hbp),
                "失点": int(runs),
                "自責点": int(er)
            })

        df_summary = pd.DataFrame(summary_rows)

        for row in summary_rows:
            with st.container(border=True):
                st.markdown(f"#### ⚾ **{row['投手名']}**")
                m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
                m1.metric("投球回", row["投球回"])
                m2.metric("総球数", f"{row['総球数']} 球")
                m3.metric("ストライク (S/B)", f"{row['ストライク']} / {row['ボール']}")
                m4.metric("ストライク率 (S%)", row["ストライク率"])
                m5.metric("被安打 / 奪三振", f"{row['被安打']} / {row['奪三振']}")
                m6.metric("四死球", f"{row['四死球']} 個")
                m7.metric("失点 (自責)", f"{row['失点']} ({row['自責点']})")

        st.write("")
        st.markdown(f"##### 📋 {'自チーム' if is_my_team else '相手チーム'} 登板投手サマリー")
        st.dataframe(df_summary, use_container_width=True, hide_index=True)

    with tab_my:
        display_pitcher_group(my_team_pitchers, is_my_team=True)

    with tab_opp:
        display_pitcher_group(opp_team_pitchers, is_my_team=False)


# ==========================================
# 🧭 ナビゲーション
# ==========================================
st.sidebar.markdown(f"### ⚾️ {st.session_state.get('my_team_name', 'KAGUSTA')}")

if st.session_state.get("user_role") == "admin":
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
  menu_options = [" 🏆 チーム成績", " 📊 個人成績", " 📈 データ分析"]

page = st.sidebar.radio("メニュー", menu_options)

if st.sidebar.button("🚪 ログアウト", use_container_width=True):
  st.session_state["is_logged_in"] = False
  st.rerun()

# ==========================================
# 💻 メイン画面の表示制御
# ==========================================
if page == " 📝 試合データ入力":

  st.markdown("### 📝 試合データ入力")

  query_date = st.query_params.get(
      "date", datetime.date.today().strftime("%Y-%m-%d")
  )
  query_opp = st.query_params.get("opp", "")
  query_match = st.query_params.get("match", "")
  query_ground = st.query_params.get("ground", "")
  query_order = st.query_params.get("order", "")
  query_scorer = st.query_params.get("scorer", "")

  with st.expander("⚙️ 試合設定", expanded=True):
    try:
      default_date = datetime.datetime.strptime(query_date, "%Y-%m-%d").date()
    except ValueError:
      default_date = datetime.date.today()

    c1, c2, c3 = st.columns(3)

    with c1:
      selected_date = st.date_input(
          "試合日", value=default_date, key="main_selected_date"
      )
      selected_date_str = selected_date.strftime("%Y-%m-%d")

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
    
    # 🌟【修正ポイント】選択肢リスト (p_list) に存在する文字列に変換・検証するロジック
    target_scorer_val = st.session_state.get(scorer_key) or res_scorer
    matched_scorer = None
    if target_scorer_val:
        clean_target_scorer = str(target_scorer_val).split(" (")[0].strip()
        matched_scorer = next(
            (p for p in p_list if p == target_scorer_val or p.split(" (")[0].strip() == clean_target_scorer),
            None
        )
    st.session_state[scorer_key] = matched_scorer

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

  tab_batting, tab_pitching, tab_game_pitching, tab_ideal, tab_edit = st.tabs([
      " 🏠 打撃成績入力",
      " 🔥 投手成績入力",
      " 📊 投手成績分析",
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

  with tab_game_pitching:
    render_today_pitching_analysis(
        df_batting,
        df_pitching,
        current_date_str,
        match_type,
        opp_team,
        ALL_PLAYERS
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