import re
import unicodedata
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from config.settings import OFFICIAL_GAME_TYPES, SPREADSHEET_URL
from utils.players import get_stats_active_players
from utils.ui import fmt_player_name
# 🌟 ideal_order ビューの読み込み
from views.ideal_order import show_ideal_order_tab

# =========================================================
# 共通関数
# =========================================================

def normalize_name(name):
    """名前からスペースを除去する"""
    return str(name).replace(" ", "").replace(" ", "").strip()


def get_exclude_set():
    """Secretsから除外リストを読み込み、集合(set)にして返す"""
    raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
    return {normalize_name(n) for n in raw_hidden}


def filter_players(df, exclude_set):
    """データフレームから除外対象を除去する関数"""
    if "選手名" not in df.columns:
        return df

    is_team_record = df["選手名"].astype(str).str.contains("チーム記録", na=False)
    clean_names = df["選手名"].apply(normalize_name)
    mask = is_team_record | (~clean_names.isin(exclude_set))

    return df[mask]

# =========================================================
# メインの表示関数
# =========================================================


def show_analysis_page(df_batting, df_pitching):
    st.title("📈 データ分析 & 傾向")

    # --- 1. カラム名の標準化・安全補完 ---
    if not df_batting.empty:
        df_batting = df_batting.copy()
        if "選手名" not in df_batting.columns:
            if "打者名" in df_batting.columns:
                df_batting["選手名"] = df_batting["打者名"]
            else:
                df_batting["選手名"] = ""
        else:
            if "打者名" in df_batting.columns:
                df_batting["選手名"] = df_batting["選手名"].replace("", pd.NA).fillna(df_batting["打者名"])

    if not df_pitching.empty:
        df_pitching = df_pitching.copy()
        if "選手名" not in df_pitching.columns:
            if "投手名" in df_pitching.columns:
                df_pitching["選手名"] = df_pitching["投手名"]
            else:
                df_pitching["選手名"] = ""
        else:
            if "投手名" in df_pitching.columns:
                df_pitching["選手名"] = df_pitching["選手名"].replace("", pd.NA).fillna(df_pitching["投手名"])

    # 背番号表示用マップの取得 ＆ 非表示設定反映済み選手リストの取得
    STATS_PLAYERS, STATS_NUMBERS = get_stats_active_players()
    def local_fmt(name):
        return fmt_player_name(name, STATS_NUMBERS)

    allowed_names = STATS_PLAYERS + ["チーム記録"]
    
    if not df_batting.empty:
        df_batting = df_batting[df_batting["選手名"].isin(allowed_names)].copy()
    
    if not df_pitching.empty:
        df_pitching = df_pitching[df_pitching["選手名"].isin(allowed_names)].copy()

    exclude_set = get_exclude_set()

    if df_batting.empty and df_pitching.empty:
        st.info("分析するデータがありません。")
        return

    df_b_detail = pd.DataFrame()
    df_p_detail = pd.DataFrame()

    df_b_all = df_batting.copy()
    df_p_all = df_pitching.copy()

    required_columns = ["is_hit", "is_ab", "is_hr", "is_so", "is_1b",
                        "is_2b", "is_3b", "is_bb", "is_sf", "is_sh", "is_int", "is_pa", "bases", "打点", "盗塁", "得点"]
    for col in required_columns:
        if col not in df_b_all.columns:
            df_b_all[col] = 0

    if not df_b_all.empty and "結果" in df_b_all.columns:
        df_b_all["結果"] = df_b_all["結果"].astype(str).str.replace(r"\s+", "", regex=True)

        df_b_all["is_hit"] = df_b_all["結果"].str.contains(
            "単打|二塁打|三塁打|本塁打", na=False).astype(int)

        non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
        is_valid = ~df_b_all["結果"].isin(["", "nan", "None", "-"])
        is_not_excluded = ~df_b_all["結果"].str.contains(non_ab_pattern, na=False)
        df_b_all["is_ab"] = (is_valid & is_not_excluded).astype(int)

        df_b_all["is_hr"] = df_b_all["結果"].str.contains("本塁打", na=False).astype(int)
        df_b_all["is_so"] = df_b_all["結果"].str.contains("三振", na=False).astype(int)
        df_b_all["is_1b"] = df_b_all["結果"].str.contains("単打", na=False).astype(int)
        df_b_all["is_2b"] = df_b_all["結果"].str.contains("二塁打", na=False).astype(int)
        df_b_all["is_3b"] = df_b_all["結果"].str.contains("三塁打", na=False).astype(int)
        
        df_b_all["is_bb"] = df_b_all["結果"].str.contains("四球|死球|四死球", na=False).astype(int)
        df_b_all["is_sf"] = df_b_all["結果"].str.contains("犠飛", na=False).astype(int)
        df_b_all["is_sh"] = df_b_all["結果"].str.contains("犠打|バント", na=False).astype(int)
        df_b_all["is_int"] = df_b_all["結果"].str.contains("妨害", na=False).astype(int)

        df_b_all["is_pa"] = ((df_b_all["is_ab"] > 0) | 
                             (df_b_all["is_bb"] > 0) | 
                             (df_b_all["is_sf"] > 0) | 
                             (df_b_all["is_sh"] > 0) | 
                             (df_b_all["is_int"] > 0)).astype(int)

        df_b_all["bases"] = (
            df_b_all["is_1b"] * 1 + df_b_all["is_2b"] * 2 +
            df_b_all["is_3b"] * 3 + df_b_all["is_hr"] * 4
        )

        for c in ["打点", "盗塁", "得点"]:
            df_b_all[c] = pd.to_numeric(df_b_all[c], errors='coerce').fillna(0)

    if "選手名" in df_b_all.columns:
        df_b_all["選手名"] = df_b_all["選手名"].astype(str).str.replace(" ", "").str.replace(" ", "").str.strip()

    if "日付" in df_b_all.columns:
        df_b_all["Date"] = pd.to_datetime(df_b_all["日付"], errors='coerce')
        df_b_all["Year"] = df_b_all["Date"].dt.year.astype(str).str.replace('.0', '', regex=False).fillna("不明")
    else:
        df_b_all["Date"] = pd.NaT
        df_b_all["Year"] = "不明"

    if not df_p_all.empty and "日付" in df_p_all.columns:
        df_p_all["Date"] = pd.to_datetime(df_p_all["日付"], errors='coerce')
        df_p_all["Year"] = df_p_all["Date"].dt.year.astype(str).str.replace('.0', '', regex=False).fillna("不明")
    else:
        df_p_all["Date"] = pd.NaT
        df_p_all["Year"] = "不明"

    df_b_unfiltered = df_b_all.copy()

    df_b = filter_players(df_b_all, exclude_set)
    df_p = filter_players(df_p_all, exclude_set)

    df_p_total_base = df_p.copy()

    years = sorted([y for y in df_b["Year"].unique()
                   if y not in ['nan', 'NaT', '不明']], reverse=True)
    c1, c2 = st.columns(2)
    selected_year = c1.selectbox("対象年度", ["全期間"] + list(years))

    game_types = ["すべて", "公式戦のみ", "練習試合のみ"]
    selected_type = c2.selectbox("試合種別", game_types)

    if selected_year != "全期間":
        df_b = df_b[df_b["Year"] == selected_year]
        df_p = df_p[df_p["Year"] == selected_year]

    if selected_type == "公式戦のみ" and "試合種別" in df_b.columns:
        df_b = df_b[df_b["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        df_p = df_p[df_p["試合種別"].isin(OFFICIAL_GAME_TYPES)] if "試合種別" in df_p.columns else df_p
    elif selected_type == "練習試合のみ" and "試合種別" in df_b.columns:
        df_b = df_b[df_b["試合種別"] == "練習試合"]
        df_p = df_p[df_p["試合種別"] == "練習試合"] if "試合種別" in df_p.columns else df_p

    games_list = []
    if "Date" in df_b.columns and "対戦相手" in df_b.columns and "試合種別" in df_b.columns:
        for (d, opp, m_type), g_b in df_b.groupby(["Date", "対戦相手", "試合種別"]):
            g_p = df_p[(df_p["Date"] == d) & (df_p["対戦相手"] == opp)
                       & (df_p["試合種別"] == m_type)] if not df_p.empty and "対戦相手" in df_p.columns and "試合種別" in df_p.columns else pd.DataFrame()

            # --- 1. 先攻・後攻の判別（自チームが先攻か後攻か） ---
            bat_order = "不明"
            
            # ① 攻守列が存在する場合の判定（旧データ互換）
            if "攻守" in g_b.columns:
                val = g_b["攻守"].dropna().astype(str).str.strip()
                val = val[~val.isin(["", "nan", "None"])]
                if not val.empty:
                    raw_order = val.iloc[0]
                    if "先攻" in raw_order or "表" in raw_order:
                        bat_order = "先攻"
                    elif "後攻" in raw_order or "裏" in raw_order:
                        bat_order = "後攻"

            # ② イニング文字列（1回表 / 1回裏など）からの判定
            if bat_order == "不明" and "イニング" in g_b.columns:
                inn_series = g_b["イニング"].dropna().astype(str)
                valid_inns = inn_series[inn_series.str.contains("回")]
                if not valid_inns.empty:
                    omote_cnt = valid_inns.str.contains("表").sum()
                    ura_cnt = valid_inns.str.contains("裏").sum()
                    if omote_cnt > ura_cnt:
                        bat_order = "先攻"
                    elif ura_cnt > omote_cnt:
                        bat_order = "後攻"

            # --- 2. 自チーム得点・相手チーム失点（スコア）の集計 ---
            is_team_rec = g_b["選手名"].astype(str).str.contains("チーム記録", na=False)
            team_rows = g_b[is_team_rec]
            indiv_rows = g_b[~is_team_rec]

            if not team_rows.empty and "得点" in team_rows.columns:
                my_score = pd.to_numeric(team_rows["得点"], errors='coerce').fillna(0).sum()
            elif "得点" in indiv_rows.columns:
                my_score = pd.to_numeric(indiv_rows["得点"], errors='coerce').fillna(0).sum()
            else:
                my_score = 0

            opp_score = 0
            if not g_p.empty:
                is_p_team_rec = g_p["選手名"].astype(str).str.contains("チーム記録", na=False)
                p_team_rows = g_p[is_p_team_rec]
                p_indiv_rows = g_p[~is_p_team_rec]

                if not p_team_rows.empty and "失点" in p_team_rows.columns:
                    opp_score = pd.to_numeric(p_team_rows["失点"], errors='coerce').fillna(0).sum()
                elif "失点" in p_indiv_rows.columns:
                    opp_score = pd.to_numeric(p_indiv_rows["失点"], errors='coerce').fillna(0).sum()

            # --- 3. 勝敗判定（① 投手成績の勝敗列を優先 → ② 得失点差で判定） ---
            res = None
            if not g_p.empty and "勝敗" in g_p.columns:
                p_col = "選手名" if "選手名" in g_p.columns else ("投手名" if "投手名" in g_p.columns else None)
                if p_col:
                    # 自チーム投手の責任投手記録を判定
                    my_p_rows = g_p[g_p[p_col].isin(STATS_PLAYERS)]
                    if not my_p_rows.empty:
                        decisions = my_p_rows["勝敗"].dropna().astype(str).str.strip().tolist()
                        if any(d in ["勝利", "勝", "○"] for d in decisions):
                            res = "Win"
                        elif any(d in ["敗戦", "敗", "●"] for d in decisions):
                            res = "Lose"

                    # 自チーム側で未判定の場合、相手投手の記録から判定
                    if res is None:
                        opp_p_rows = g_p[~g_p[p_col].isin(STATS_PLAYERS) & ~g_p[p_col].astype(str).str.contains("チーム記録", na=False)]
                        if not opp_p_rows.empty:
                            opp_decisions = opp_p_rows["勝敗"].dropna().astype(str).str.strip().tolist()
                            if any(d in ["勝利", "勝", "○"] for d in opp_decisions):
                                res = "Lose"
                            elif any(d in ["敗戦", "敗", "●"] for d in opp_decisions):
                                res = "Win"

            # 投手成績から判定できなかった場合は得失点（スコア）で判定
            if res is None:
                if my_score > opp_score:
                    res = "Win"
                elif my_score < opp_score:
                    res = "Lose"
                else:
                    res = "Draw"

            # --- 4. 先制チームの判定 ---
            def get_inn_num(t):
                t = str(t).replace("回", "").replace("表", "").replace("裏", "")
                return int(t) if t.isdigit() else 99

            min_my_inn = 99
            if "イニング" in g_b.columns and "得点" in g_b.columns:
                my_inn_scores = g_b[g_b["イニング"].astype(str).str.contains("回")].copy()
                if not my_inn_scores.empty:
                    my_inn_scores["InnNum"] = my_inn_scores["イニング"].apply(get_inn_num)
                    my_score_inns = my_inn_scores[pd.to_numeric(my_inn_scores["得点"], errors='coerce') > 0].sort_values("InnNum")
                    min_my_inn = my_score_inns["InnNum"].iloc[0] if not my_score_inns.empty else 99

            min_opp_inn = 99
            if not g_p.empty and "イニング" in g_p.columns and "失点" in g_p.columns:
                opp_inn_scores = g_p[g_p["イニング"].astype(str).str.contains("回")].copy()
                if not opp_inn_scores.empty:
                    opp_inn_scores["InnNum"] = opp_inn_scores["イニング"].apply(get_inn_num)
                    opp_score_inns = opp_inn_scores[pd.to_numeric(opp_inn_scores["失点"], errors='coerce') > 0].sort_values("InnNum")
                    min_opp_inn = opp_score_inns["InnNum"].iloc[0] if not opp_score_inns.empty else 99

            first_score_team = "自チーム" if min_my_inn < min_opp_inn else (
                "相手" if min_opp_inn < min_my_inn else "なし(0-0)")

            games_list.append({
                "Date": d, "Opponent": opp, "MyScore": my_score,
                "OppScore": opp_score, "Result": res, "FirstScore": first_score_team,
                "BatOrder": bat_order
            })

    df_games = pd.DataFrame(games_list)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 チーム傾向", "🆚 対戦相手別", "🔍 詳細投打分析", "🧠 理想オーダー"])

    # =========================================================
    # Tab 1: チーム傾向
    # =========================================================
    with tab1:
        if df_games.empty:
            st.warning("データ不足のため表示できません")
        else:
            st.markdown("### 📈 チーム傾向")

            total_runs = df_games["MyScore"].sum()
            total_lost = df_games["OppScore"].sum()
            wins = len(df_games[df_games["Result"] == "Win"])
            total_g = len(df_games)
            actual_rate = wins / total_g if total_g > 0 else 0

            pyth_rate = 0.0
            if (total_runs + total_lost) > 0:
                pyth_rate = (total_runs**2) / \
                    ((total_runs**2) + (total_lost**2))

            luck_diff = actual_rate - pyth_rate

            if luck_diff > 0.1:
                luck_msg = "🌟 豪運！接戦に強い！"
            elif luck_diff > 0.05:
                luck_msg = "🍀 勝ち運あり"
            elif luck_diff > -0.05:
                luck_msg = "⚖️ 実力通り"
            elif luck_diff > -0.1:
                luck_msg = "☁️ 少しツキがないかも"
            else:
                luck_msg = "☔ 不運...次は勝てる！"

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("試合数", f"{total_g} 試合", f"{wins}勝")
            k2.metric("勝率", f"{actual_rate:.3f}",
                      f"貯金 {wins - (total_g - wins - len(df_games[df_games['Result']=='Draw']))}")
            k3.metric("平均得点", f"{df_games['MyScore'].mean():.1f}",
                      delta=f"失点 {df_games['OppScore'].mean():.1f}", delta_color="normal")
            k4.metric("チームの運勢", luck_msg, f"期待勝率 {pyth_rate:.3f}")

            st.write("")
            st.markdown("**📅 直近5試合の勝敗**")
            recent = df_games.sort_values("Date", ascending=False).head(5)
            cols = st.columns(5)
            for i, (_, r) in enumerate(recent.iterrows()):
                icon = "🔴" if r["Result"] == "Win" else "🔵" if r["Result"] == "Lose" else "⚪"
                cols[i].markdown(
                    f"<div style='text-align:center; font-size:24px;'>{icon}</div>", unsafe_allow_html=True)
                date_str = r['Date'].strftime('%m/%d') if pd.notna(r['Date']) else ""
                cols[i].caption(
                    f"<div style='text-align:center;'>{date_str}</div>", unsafe_allow_html=True)

            st.divider()

            st.markdown("### 🔥 勝利の法則とマジックナンバー")
            st.caption("得点ごとの試合回数（棒）と勝率（折れ線）")

            score_bins = df_games.copy()
            score_win_rate = (
                score_bins.groupby("MyScore")
                .agg(
                    GameCount=("Result", "count"),
                    WinCount=("Result", lambda x: (x == "Win").sum()),
                )
                .reset_index()
            )
            score_win_rate["WinRate"] = (
                score_win_rate["WinCount"] / score_win_rate["GameCount"]
            )

            base_chart = alt.Chart(score_win_rate).encode(
                x=alt.X("MyScore:O", title="得点"))

            bar_c = base_chart.mark_bar(opacity=0.3, color="#64748b").encode(
                y=alt.Y("GameCount", title="試合回数")
            )

            line_c = base_chart.mark_line(point=True, color="#e11d48").encode(
                y=alt.Y("WinRate", title="勝率", axis=alt.Axis(format="%")),
                tooltip=[
                    "MyScore",
                    "GameCount",
                    alt.Tooltip("WinRate", format=".0%"),
                ],
            )

            st.altair_chart(
                (bar_c + line_c).resolve_scale(y="independent"), use_container_width=True
            )

            magic_num = 0
            for index, row in score_win_rate.iterrows():
                if row["WinRate"] >= 0.8:
                    magic_num = int(row["MyScore"])
                    break

            win_rate_val = score_win_rate[score_win_rate["MyScore"] >= magic_num][
                "WinRate"
            ].mean() if magic_num in score_win_rate["MyScore"].values else None
            win_rate_str = f"{int(win_rate_val*100)}%" if pd.notna(win_rate_val) else "-"

            st.success(
                f"🎯 **勝利のマジックナンバー： {magic_num}点** （これ以上取った時の勝率 **{win_rate_str}**）"
            )

            st.divider()

            st.markdown("### ⏱️ 試合展開の傾向")
            col_bot1, col_bot2 = st.columns(2)

            with col_bot1:
                st.caption("先制 / 被先制時の勝率")
                c_f1, c_f2 = st.columns(2)

                games_first = df_games[df_games["FirstScore"] == "自チーム"]
                if not games_first.empty:
                    w = len(games_first[games_first["Result"] == "Win"])
                    l = len(games_first[games_first["Result"] == "Lose"])
                    d = len(games_first[games_first["Result"] == "Draw"])
                    rate = w / (w+l) if (w+l) > 0 else 0
                    df_f_res = pd.DataFrame(
                        {"Result": ["Win", "Lose", "Draw"], "Count": [w, l, d]})
                    pie_f = alt.Chart(df_f_res).mark_arc(innerRadius=30).encode(
                        theta="Count",
                        color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=[
                                        "#e11d48", "#1e40af", "#94a3b8"]), legend=None),
                        tooltip=["Result", "Count"]
                    ).properties(title=f"先制時 (勝率{rate:.2f})")
                    c_f1.altair_chart(pie_f, use_container_width=True)
                else:
                    c_f1.info("先制試合なし")

                games_opp_first = df_games[df_games["FirstScore"] == "相手"]
                if not games_opp_first.empty:
                    w2 = len(
                        games_opp_first[games_opp_first["Result"] == "Win"])
                    l2 = len(
                        games_opp_first[games_opp_first["Result"] == "Lose"])
                    d2 = len(
                        games_opp_first[games_opp_first["Result"] == "Draw"])
                    rate2 = w2 / (w2+l2) if (w2+l2) > 0 else 0
                    df_f_opp_res = pd.DataFrame(
                        {"Result": ["Win", "Lose", "Draw"], "Count": [w2, l2, d2]})
                    pie_f_opp = alt.Chart(df_f_opp_res).mark_arc(innerRadius=30).encode(
                        theta="Count",
                        color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=[
                                        "#e11d48", "#1e40af", "#94a3b8"]), legend=None),
                        tooltip=["Result", "Count"]
                    ).properties(title=f"被先制時 (勝率{rate2:.2f})")
                    c_f2.altair_chart(pie_f_opp, use_container_width=True)
                else:
                    c_f2.info("被先制試合なし")

                st.write("")
                st.caption("先攻 / 後攻別の勝率")
                c_o1, c_o2 = st.columns(2)

                games_first_bat = df_games[df_games["BatOrder"] == "先攻"]
                if not games_first_bat.empty:
                    w_b1 = len(games_first_bat[games_first_bat["Result"] == "Win"])
                    l_b1 = len(games_first_bat[games_first_bat["Result"] == "Lose"])
                    d_b1 = len(games_first_bat[games_first_bat["Result"] == "Draw"])
                    rate_b1 = w_b1 / (w_b1 + l_b1) if (w_b1 + l_b1) > 0 else 0
                    df_b1_res = pd.DataFrame(
                        {"Result": ["Win", "Lose", "Draw"], "Count": [w_b1, l_b1, d_b1]})
                    pie_b1 = alt.Chart(df_b1_res).mark_arc(innerRadius=30).encode(
                        theta="Count",
                        color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=[
                                        "#e11d48", "#1e40af", "#94a3b8"]), legend=None),
                        tooltip=["Result", "Count"]
                    ).properties(title=f"先攻時 (勝率{rate_b1:.2f})")
                    c_o1.altair_chart(pie_b1, use_container_width=True)
                else:
                    c_o1.info("先攻試合なし")

                games_second_bat = df_games[df_games["BatOrder"] == "後攻"]
                if not games_second_bat.empty:
                    w_b2 = len(games_second_bat[games_second_bat["Result"] == "Win"])
                    l_b2 = len(games_second_bat[games_second_bat["Result"] == "Lose"])
                    d_b2 = len(games_second_bat[games_second_bat["Result"] == "Draw"])
                    rate_b2 = w_b2 / (w_b2 + l_b2) if (w_b2 + l_b2) > 0 else 0
                    df_b2_res = pd.DataFrame(
                        {"Result": ["Win", "Lose", "Draw"], "Count": [w_b2, l_b2, d_b2]})
                    pie_b2 = alt.Chart(df_b2_res).mark_arc(innerRadius=30).encode(
                        theta="Count",
                        color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=[
                                        "#e11d48", "#1e40af", "#94a3b8"]), legend=None),
                        tooltip=["Result", "Count"]
                    ).properties(title=f"後攻時 (勝率{rate_b2:.2f})")
                    c_o2.altair_chart(pie_b2, use_container_width=True)
                else:
                    c_o2.info("後攻試合なし")

            with col_bot2:
                st.caption("イニング別の得点力・失点傾向")

                def aggregate_innings(df_raw, score_col):
                    if df_raw.empty or "イニング" not in df_raw.columns or score_col not in df_raw.columns:
                        return pd.Series(dtype=float)
                    df_i = df_raw.copy()
                    df_i["イニング"] = df_i["イニング"].astype(str).str.replace(r"[表裏]", "", regex=True)
                    df_i = df_i[df_i["イニング"].str.match(r"^\d+回")]
                    df_i["得点"] = pd.to_numeric(
                        df_i[score_col], errors='coerce').fillna(0)
                    return df_i.groupby("イニング")["得点"].sum()

                inn_scores = aggregate_innings(df_b, "得点")
                inn_lost = aggregate_innings(df_p, "失点")

                df_inn = pd.DataFrame(
                    {"得点": inn_scores, "失点": inn_lost}).fillna(0).reset_index()
                if not df_inn.empty:
                    df_inn["InnNum"] = df_inn["イニング"].apply(
                        lambda x: int(re.search(r'\d+', str(x)).group()) if re.search(r'\d+', str(x)) else 99)
                    df_inn = df_inn.sort_values("InnNum")
                    df_inn_melt = df_inn.melt(id_vars=["イニング", "InnNum"], value_vars=[
                                              "得点", "失点"], var_name="Type", value_name="Runs")

                    bar_inn = alt.Chart(df_inn_melt).mark_bar().encode(
                        x=alt.X("Type:N", title=None, axis=alt.Axis(
                            labels=False, ticks=False)),
                        y=alt.Y("Runs:Q", title="点数"),
                        color=alt.Color("Type:N", scale=alt.Scale(
                            domain=["得点", "失点"], range=["#e11d48", "#1e40af"])),
                        column=alt.Column("イニング:N", sort=alt.EncodingSortField(
                            field="InnNum", order="ascending"), title="イニング", header=alt.Header(labelOrient="bottom")),
                        tooltip=["イニング", "Type", "Runs"]
                    ).properties(width=30)

                    st.altair_chart(bar_inn, use_container_width=False)
                else:
                    st.caption("イニング別データなし")

            # 先攻・後攻別の詳細成績テーブル
            st.write("")
            st.markdown("##### ⚾ 先攻・後攻別の詳細成績")
            df_order_stats = []
            for b_type in ["先攻", "後攻"]:
                sub_o = df_games[df_games["BatOrder"] == b_type]
                if not sub_o.empty:
                    wo = len(sub_o[sub_o["Result"] == "Win"])
                    lo = len(sub_o[sub_o["Result"] == "Lose"])
                    do = len(sub_o[sub_o["Result"] == "Draw"])
                    tot = len(sub_o)
                    ro = wo / (wo + lo) if (wo + lo) > 0 else 0.0
                    df_order_stats.append({
                        "攻守": b_type,
                        "試合数": tot,
                        "勝利": wo,
                        "敗戦": lo,
                        "引分": do,
                        "勝率": ro,
                        "平均得点": sub_o["MyScore"].mean(),
                        "平均失点": sub_o["OppScore"].mean()
                    })
            if df_order_stats:
                st.dataframe(
                    pd.DataFrame(df_order_stats).style.format({
                        "勝率": "{:.3f}", "平均得点": "{:.1f}", "平均失点": "{:.1f}"
                    }).background_gradient(subset=["勝率"], cmap="Reds"),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.caption("先攻・後攻データがありません")

    # =========================================================
    # Tab 2: 対戦相手別
    # =========================================================
    with tab2:
        if df_games.empty:
            st.warning("データなし")
        else:
            st.markdown("##### 🔍 対戦相手別成績")

            df_clean = df_games.drop_duplicates(
                subset=["Date", "Opponent"]).copy()

            df_clean["MyScore"] = pd.to_numeric(
                df_clean["MyScore"], errors='coerce').fillna(0)
            df_clean["OppScore"] = pd.to_numeric(
                df_clean["OppScore"], errors='coerce').fillna(0)

            opp_stats = df_clean.groupby("Opponent").agg(
                試合数=("Result", "count"),
                勝利=("Result", lambda x: (x == "Win").sum()),
                敗戦=("Result", lambda x: (x == "Lose").sum()),
                引分=("Result", lambda x: (x == "Draw").sum()),
                平均得点=("MyScore", "mean"),
                平均失点=("OppScore", "mean")
            ).reset_index()

            opp_stats["勝率"] = opp_stats.apply(
                lambda x: x["勝利"] / (x["勝利"] + x["敗戦"]
                                     ) if (x["勝利"] + x["敗戦"]) > 0 else 0,
                axis=1
            )

            opp_stats = opp_stats.sort_values(
                "試合数", ascending=False).reset_index(drop=True)

            st.dataframe(
                opp_stats.style.format(
                    {"平均得点": "{:.1f}", "平均失点": "{:.1f}", "勝率": "{:.3f}"})
                .background_gradient(subset=["勝率"], cmap="Reds"),
                use_container_width=True,
                hide_index=True
            )

            opp_stats["得失差"] = opp_stats["平均得点"] - opp_stats["平均失点"]
            bar_diff = (
                alt.Chart(opp_stats)
                .mark_bar()
                .encode(
                    x=alt.X("Opponent:N", sort="-y", title="対戦相手"),
                    y=alt.Y("得失差:Q", title="平均得失点差"),
                    color=alt.condition(alt.datum.得失差 > 0, alt.value(
                        "#e11d48"), alt.value("#1e40af")),
                    tooltip=[
                        alt.Tooltip("Opponent:N", title="対戦相手"),
                        alt.Tooltip("試合数:Q", title="試合数"),
                        alt.Tooltip("平均得点:Q", title="平均得点", format=".1f"),
                        alt.Tooltip("平均失点:Q", title="平均失点", format=".1f"),
                        alt.Tooltip("得失差:Q", title="得失差", format=".1f"),
                        alt.Tooltip("勝率:Q", title="勝率", format=".3f")
                    ]
                )
                .properties(height=400)
            )
            st.altair_chart(bar_diff, use_container_width=True)

    # =========================================================
    # Tab 3: 詳細投打データ分析（2026年以降）
    # =========================================================
    with tab3:
        st.markdown("## 🔍 詳細投打データ分析 (2026年以降)")
        st.caption("※詳細な記録を取り始めた2026年以降のデータを集計しています。打球の種類ごとの傾向を追加しました。")

        df_b_detail = df_batting[pd.to_datetime(df_batting["日付"], errors='coerce').dt.year >= 2026].copy(
        ) if not df_batting.empty and "日付" in df_batting.columns else pd.DataFrame()
        df_p_detail = df_pitching[pd.to_datetime(df_pitching["日付"], errors='coerce').dt.year >= 2026].copy(
        ) if not df_pitching.empty and "日付" in df_pitching.columns else pd.DataFrame()

        def remove_outfield_goro_error(df):
            if df.empty or "打球方向" not in df.columns or "結果" not in df.columns:
                return df
            is_outfield = df["打球方向"].astype(
                str).str.strip().isin(["左", "中", "右"])
            is_error = df["結果"].astype(str).str.contains("失策", na=False)
            is_goro = df["結果"].astype(str).str.contains("ゴロ", na=False)

            return df[~(is_outfield & is_error & is_goro)].copy()

        df_b_detail = remove_outfield_goro_error(df_b_detail)
        df_p_detail = remove_outfield_goro_error(df_p_detail)

        def classify_hit_type(res):
            res = str(res)
            if "ゴロ" in res or "併殺" in res:
                return "ゴロ"
            elif "フライ" in res or "犠飛" in res or "飛" in res:
                return "フライ"
            elif "ライナー" in res or "直" in res:
                return "ライナー"
            elif "三振" in res or "四球" in res or "死球" in res or "四死球" in res:
                return "非打球"
            elif any(x in res for x in ["単打", "二塁打", "三塁打", "本塁打", "安"]):
                return "安打"
            else:
                return "その他"

        if not df_b_detail.empty and "結果" in df_b_detail.columns:
            df_b_detail["打球種類"] = df_b_detail["結果"].apply(classify_hit_type)
        if not df_p_detail.empty and "結果" in df_p_detail.columns:
            df_p_detail["打球種類"] = df_p_detail["結果"].apply(classify_hit_type)

        hit_type_color_scale = alt.Scale(
            domain=["ゴロ", "フライ", "ライナー", "安打"],
            range=["#eab308", "#3b82f6", "#22c55e", "#ef4444"]
        )
        pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

        sub_tab1, sub_tab2, sub_tab3 = st.tabs(
            ["🏢 チーム全体の傾向", "🏏 個人の打撃分析", "⚾ 個人の投手分析"])

        # --- チーム全体の傾向 ---
        with sub_tab1:
            st.markdown("#### 🏢 チーム全体のプレースタイル")

            # 打数・安打・四死球フラグの事前作成
            if not df_b_detail.empty and "結果" in df_b_detail.columns:
                if "is_ab" not in df_b_detail.columns or "is_hit" not in df_b_detail.columns or "is_bb" not in df_b_detail.columns:
                    non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
                    is_valid = ~df_b_detail["結果"].astype(str).isin(["", "nan", "None", "-"])
                    is_not_excluded = ~df_b_detail["結果"].astype(str).str.contains(non_ab_pattern, na=False)
                    df_b_detail["is_ab"] = (is_valid & is_not_excluded).astype(int)
                    df_b_detail["is_hit"] = df_b_detail["結果"].astype(str).str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)
                    df_b_detail["is_bb"] = df_b_detail["結果"].astype(str).str.contains("四球|死球|四死球", na=False).astype(int)

            if not df_p_detail.empty and "結果" in df_p_detail.columns:
                if "is_ab" not in df_p_detail.columns or "is_hit" not in df_p_detail.columns or "is_bb" not in df_p_detail.columns:
                    non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
                    is_valid = ~df_p_detail["結果"].astype(str).isin(["", "nan", "None", "-"])
                    is_not_excluded = ~df_p_detail["結果"].astype(str).str.contains(non_ab_pattern, na=False)
                    df_p_detail["is_ab"] = (is_valid & is_not_excluded).astype(int)
                    df_p_detail["is_hit"] = df_p_detail["結果"].astype(str).str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)
                    df_p_detail["is_bb"] = df_p_detail["結果"].astype(str).str.contains("四球|死球|四死球", na=False).astype(int)

            # チーム全体の打率・被打率・防御率の計算とメトリクス表示
            t_ab = df_b_detail["is_ab"].sum() if not df_b_detail.empty and "is_ab" in df_b_detail.columns else 0
            t_hit = df_b_detail["is_hit"].sum() if not df_b_detail.empty and "is_hit" in df_b_detail.columns else 0
            team_avg = t_hit / t_ab if t_ab > 0 else 0.0

            tp_ab = df_p_detail["is_ab"].sum() if not df_p_detail.empty and "is_ab" in df_p_detail.columns else 0
            tp_hit = df_p_detail["is_hit"].sum() if not df_p_detail.empty and "is_hit" in df_p_detail.columns else 0
            team_p_avg = tp_hit / tp_ab if tp_ab > 0 else 0.0

            # 打撃・投球結果から正確なアウト数を動的に算出
            single_out_list = [
                "三振", "凡退(ゴロ)", "凡退(フライ)", "ゴロ", "フライ", "ライナー",
                "犠打(ゴロ)", "犠打(フライ)", "犠打", "犠飛",
                "牽制死", "盗塁死", "走塁死", "振り逃げ三振"
            ]

            if not df_p_detail.empty and "結果" in df_p_detail.columns:
                res_s = df_p_detail["結果"].astype(str).str.strip()
                s_outs = len(df_p_detail[res_s.isin(single_out_list)])
                d_outs = len(df_p_detail[res_s == "併殺打"]) * 2
                t_outs = len(df_p_detail[res_s == "三重殺"]) * 3
                outs_sum = s_outs + d_outs + t_outs
            else:
                outs_sum = pd.to_numeric(df_p_detail.get("アウト数", 0), errors='coerce').fillna(0).sum() if not df_p_detail.empty and "アウト数" in df_p_detail.columns else 0

            ip_val = outs_sum / 3.0
            run_col = "自責点" if "自責点" in df_p_detail.columns else ("失点" if "失点" in df_p_detail.columns else None)
            er_sum = pd.to_numeric(df_p_detail[run_col], errors='coerce').fillna(0).sum() if not df_p_detail.empty and run_col else 0

            # 防御率計算（7回制）
            team_era = (er_sum * 7) / ip_val if ip_val > 0 else 0.0
            run_col = "自責点" if "自責点" in df_p_detail.columns else ("失点" if "失点" in df_p_detail.columns else None)
            er_sum = pd.to_numeric(df_p_detail[run_col], errors='coerce').fillna(0).sum() if not df_p_detail.empty and run_col else 0
            team_era = (er_sum * 7) / ip_val if ip_val > 0 else 0.0

            tm1, tm2, tm3 = st.columns(3)
            tm1.metric("チーム打率", f"{team_avg:.3f}")
            tm2.metric("チーム被打率", f"{team_p_avg:.3f}")
            tm3.metric("チーム防御率", f"{team_era:.2f}")

            st.write("")
            st.divider()

            st.markdown("##### チーム打球傾向 (アウトの内訳)")
            if not df_b_detail.empty and "結果" in df_b_detail.columns:
                t_goro = len(
                    df_b_detail[df_b_detail["結果"].astype(str).str.contains("ゴロ|併殺打")])
                t_fly = len(df_b_detail[df_b_detail["結果"].astype(
                    str).str.contains("フライ|犠飛")])
                t_so = len(
                    df_b_detail[df_b_detail["結果"].astype(str).str.contains("三振")])

                df_t_out = pd.DataFrame(
                    {"種類": ["ゴロアウト", "フライアウト", "三振"], "数": [t_goro, t_fly, t_so]})
                if df_t_out["数"].sum() > 0:
                    pie_t_out = alt.Chart(df_t_out).mark_arc(innerRadius=40).encode(
                        theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロアウト", "フライアウト", "三振"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
                    ).properties(height=300)
                    st.altair_chart(pie_t_out, use_container_width=True)
                else:
                    st.caption("データがありません")
            else:
                st.caption("2026年以降の打撃データがありません")

            st.write("")
            st.markdown("##### チーム投球傾向 (アウトの内訳)")
            if not df_p_detail.empty and "結果" in df_p_detail.columns:
                df_p_out_only = df_p_detail[~df_p_detail["結果"].astype(
                    str).str.contains("失策|振り逃げ", na=False)]

                p_goro = len(
                    df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("ゴロ|併殺打")])
                p_fly = len(
                    df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("フライ")])
                p_so = len(
                    df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("三振")])

                df_p_out = pd.DataFrame(
                    {"種類": ["ゴロアウト", "フライアウト", "三振"], "数": [p_goro, p_fly, p_so]})
                if df_p_out["数"].sum() > 0:
                    pie_p_out = alt.Chart(df_p_out).mark_arc(innerRadius=40).encode(
                        theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロアウト", "フライアウト", "三振"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
                    ).properties(height=300)
                    st.altair_chart(pie_p_out, use_container_width=True)
                else:
                    st.caption("詳細な投手データがありません")
            else:
                st.caption("2026年以降の投手データがありません")

            st.write("")
            st.markdown("##### 🏟️ ポジション別の打球方向と種類")

            c_dir1, c_dir2 = st.columns(2)

            with c_dir1:
                st.markdown("**▼ チーム打撃 (どこへ・どんな打球を打っているか)**")
                if not df_b_detail.empty and "打球方向" in df_b_detail.columns:
                    # 方向が有効なもの（空文字、nan、--- を除外）かつ「その他」「非打球」を除外
                    b_dir_data = df_b_detail[
                        df_b_detail["打球方向"].notna() & 
                        (~df_b_detail["打球方向"].astype(str).str.strip().isin(["", "nan", "---"])) &
                        (~df_b_detail["打球種類"].isin(["その他", "非打球"]))
                    ].copy()
                    
                    if not b_dir_data.empty:
                        # 🌟 複合表記（二-捕など）は最初の文字に統合し、基本9ポジションに絞り込む
                        b_dir_data["方向"] = b_dir_data["打球方向"].astype(str).str.strip().apply(lambda x: x.split("-")[0])
                        b_dir_data = b_dir_data[b_dir_data["方向"].isin(pos_order)]

                        b_dir_counts = b_dir_data.groupby(["方向", "打球種類"]).size().reset_index(name="数")

                        bar_b_dir = alt.Chart(b_dir_counts).mark_bar().encode(
                            x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("数:Q", title="打球数"),
                            color=alt.Color("打球種類:N", scale=hit_type_color_scale),
                            tooltip=["方向", "打球種類", "数"]
                        ).properties(height=280)
                        st.altair_chart(bar_b_dir, use_container_width=True)
                    else:
                        st.caption("データがありません")
                else:
                    st.caption("データがありません")

            with c_dir2:
                st.markdown("**▼ チーム投手陣 (どこへ・どんな打球を打たせているか)**")
                if not df_p_detail.empty and "打球方向" in df_p_detail.columns:
                    # 方向が有効なもの（空文字、nan、--- を除外）かつ「その他」「非打球」を除外
                    p_dir_data = df_p_detail[
                        df_p_detail["打球方向"].notna() & 
                        (~df_p_detail["打球方向"].astype(str).str.strip().isin(["", "nan", "---"])) &
                        (~df_p_detail["打球種類"].isin(["その他", "非打球"]))
                    ].copy()
                    
                    if not p_dir_data.empty:
                        # 🌟 複合表記（二-捕など）は最初の文字に統合し、基本9ポジションに絞り込む
                        p_dir_data["方向"] = p_dir_data["打球方向"].astype(str).str.strip().apply(lambda x: x.split("-")[0])
                        p_dir_data = p_dir_data[p_dir_data["方向"].isin(pos_order)]

                        p_dir_counts = p_dir_data.groupby(["方向", "打球種類"]).size().reset_index(name="数")

                        bar_p_dir = alt.Chart(p_dir_counts).mark_bar().encode(
                            x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("数:Q", title="打球数"),
                            color=alt.Color("打球種類:N", scale=hit_type_color_scale),
                            tooltip=["方向", "打球種類", "数"]
                        ).properties(height=280)
                        st.altair_chart(bar_p_dir, use_container_width=True)
                    else:
                        st.caption("データがありません")
                else:
                    st.caption("データがありません")

            st.write("")
            st.divider()

            # ボールカウント別 チーム打撃・投手成績
            st.markdown("##### ⚾ ボールカウント別 チーム打撃・投手成績")
            c_cnt1, c_cnt2 = st.columns(2)

            with c_cnt1:
                st.markdown("**▼ チーム打率（カウント別）**")
                if not df_b_detail.empty:
                    if "ボール" in df_b_detail.columns and "ストライク" in df_b_detail.columns:
                        df_b_detail["ball_count_str"] = df_b_detail.apply(
                            lambda r: f"{int(float(r['ボール']))}B-{min(2, int(float(r['ストライク'])))}S" 
                            if pd.notna(r.get("ボール")) and pd.notna(r.get("ストライク")) and str(r.get("ボール")) != "nan" and str(r.get("ストライク")) != "nan" else None, 
                            axis=1
                        )
                        cnt_col_b = "ball_count_str"
                    elif "カウント" in df_b_detail.columns:
                        df_b_detail["ball_count_str"] = df_b_detail["カウント"].astype(str).apply(
                            lambda x: re.sub(r'(\d+)S', lambda m: f"{min(2, int(m.group(1)))}S", x) if x and x != "nan" else None
                        )
                        cnt_col_b = "ball_count_str"
                    else:
                        cnt_col_b = None

                    if cnt_col_b and cnt_col_b in df_b_detail.columns and not df_b_detail[cnt_col_b].dropna().empty:
                        df_b_valid_c = df_b_detail[df_b_detail[cnt_col_b].notna() & (df_b_detail[cnt_col_b] != "") & (df_b_detail[cnt_col_b] != "nan")].copy()
                        if not df_b_valid_c.empty:
                            tc_stats = df_b_valid_c.groupby(cnt_col_b).agg(
                                打数=("is_ab", "sum"),
                                四死球=("is_bb", "sum"),
                                安打=("is_hit", "sum")
                            ).reset_index()
                            tc_stats["打率"] = tc_stats.apply(lambda x: x["安打"] / x["打数"] if x["打数"] > 0 else 0.0, axis=1)
                            tc_stats = tc_stats.rename(columns={cnt_col_b: "カウント"})
                            tc_stats = tc_stats[["カウント", "打数", "四死球", "安打", "打率"]]

                            st.dataframe(
                                tc_stats.style.format({"打率": "{:.3f}"})
                                .background_gradient(subset=["打率"], cmap="Reds"),
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.caption("ボールカウント別のデータがありません。")
                    else:
                        st.caption("ボールカウント別のデータがありません。")
                else:
                    st.caption("2026年以降の打撃データがありません")

            with c_cnt2:
                st.markdown("**▼ チーム被打率（カウント別）**")
                if not df_p_detail.empty:
                    if "ボール" in df_p_detail.columns and "ストライク" in df_p_detail.columns:
                        df_p_detail["ball_count_str"] = df_p_detail.apply(
                            lambda r: f"{int(float(r['ボール']))}B-{min(2, int(float(r['ストライク'])))}S" 
                            if pd.notna(r.get("ボール")) and pd.notna(r.get("ストライク")) and str(r.get("ボール")) != "nan" and str(r.get("ストライク")) != "nan" else None, 
                            axis=1
                        )
                        cnt_col_p = "ball_count_str"
                    elif "カウント" in df_p_detail.columns:
                        df_p_detail["ball_count_str"] = df_p_detail["カウント"].astype(str).apply(
                            lambda x: re.sub(r'(\d+)S', lambda m: f"{min(2, int(m.group(1)))}S", x) if x and x != "nan" else None
                        )
                        cnt_col_p = "ball_count_str"
                    else:
                        cnt_col_p = None

                    if cnt_col_p and cnt_col_p in df_p_detail.columns and not df_p_detail[cnt_col_p].dropna().empty:
                        df_p_valid_c = df_p_detail[df_p_detail[cnt_col_p].notna() & (df_p_detail[cnt_col_p] != "") & (df_p_detail[cnt_col_p] != "nan")].copy()
                        if not df_p_valid_c.empty:
                            tpc_stats = df_p_valid_c.groupby(cnt_col_p).agg(
                                打数=("is_ab", "sum"),
                                四死球=("is_bb", "sum"),
                                被安打=("is_hit", "sum")
                            ).reset_index()
                            tpc_stats["被打率"] = tpc_stats.apply(lambda x: x["被安打"] / x["打数"] if x["打数"] > 0 else 0.0, axis=1)
                            tpc_stats = tpc_stats.rename(columns={cnt_col_p: "カウント"})
                            tpc_stats = tpc_stats[["カウント", "打数", "四死球", "被安打", "被打率"]]

                            st.dataframe(
                                tpc_stats.style.format({"被打率": "{:.3f}"})
                                .background_gradient(subset=["被打率"], cmap="Blues"),
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.caption("ボールカウント別のデータがありません。")
                    else:
                        st.caption("ボールカウント別のデータがありません。")
                else:
                    st.caption("2026年以降の投手データがありません")

        # --- 個人の打撃分析 ---
        with sub_tab2:
            if not df_b_detail.empty and "選手名" in df_b_detail.columns:
                players_b = [p for p in STATS_PLAYERS if p in df_b_detail["選手名"].unique()]

                if players_b:
                    if "ana_bat_player" not in st.session_state or st.session_state["ana_bat_player"] not in players_b:
                        st.session_state["ana_bat_player"] = None

                    current_bat_player = st.session_state.get("ana_bat_player")
                    popover_label_bat = f"👤 打者選択: {fmt_player_name(current_bat_player, STATS_NUMBERS)} 🔽" if current_bat_player else "👤 打者選択: 未選択 🔽"

                    with st.popover(popover_label_bat, use_container_width=True):
                        st.markdown("##### 👤 分析する打者をタップして選択")
                        st.pills(
                            "分析する打者を選択",
                            players_b,
                            format_func=local_fmt,
                            key="ana_bat_player",
                            label_visibility="collapsed"
                        )

                    target_b_player = st.session_state.get("ana_bat_player")
                    if not target_b_player:
                        st.info("👆 上のボタンから分析する打者を選択してください。")
                    else:
                        my_b = df_b_detail[df_b_detail["選手名"] == target_b_player].copy()

                        if not my_b.empty:
                            if "is_ab" not in my_b.columns or "is_hit" not in my_b.columns or "is_bb" not in my_b.columns:
                                non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
                                is_valid = ~my_b["結果"].astype(str).isin(["", "nan", "None", "-"])
                                is_not_excluded = ~my_b["結果"].astype(str).str.contains(non_ab_pattern, na=False)
                                my_b["is_ab"] = (is_valid & is_not_excluded).astype(int)
                                my_b["is_hit"] = my_b["結果"].astype(str).str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)
                                my_b["is_bb"] = my_b["結果"].astype(str).str.contains("四球|死球|四死球", na=False).astype(int)

                            total_b_df = df_batting[df_batting["選手名"] == target_b_player] if not df_batting.empty else pd.DataFrame()
                            if not total_b_df.empty:
                                non_ab_pat = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
                                t_res = total_b_df["結果"].astype(str)
                                t_ab = (~t_res.isin(["", "nan", "None", "-"]) & ~t_res.str.contains(non_ab_pat, na=False)).sum()
                                t_hit = t_res.str.contains("単打|二塁打|三塁打|本塁打", na=False).sum()
                                avg_total = t_hit / t_ab if t_ab > 0 else 0.0
                            else:
                                avg_total = 0.0

                            s_ab = my_b["is_ab"].sum()
                            s_hit = my_b["is_hit"].sum()
                            avg_season = s_hit / s_ab if s_ab > 0 else 0.0

                            pa_cnt = my_b["is_pa"].sum() if "is_pa" in my_b.columns else len(my_b)

                            if "球数" in my_b.columns:
                                r_pitches_b = pd.to_numeric(my_b["球数"], errors='coerce').fillna(0)
                            else:
                                s_b_cnt = pd.to_numeric(my_b.get("ストライク", 0), errors='coerce').fillna(0)
                                b_b_cnt = pd.to_numeric(my_b.get("ボール", 0), errors='coerce').fillna(0)
                                r_pitches_b = s_b_cnt + b_b_cnt

                            my_b_counted = my_b[r_pitches_b > 0]
                            pa_cnt_counted = my_b_counted["is_pa"].sum() if "is_pa" in my_b_counted.columns else len(my_b_counted)
                            total_b_pitches_counted = r_pitches_b[r_pitches_b > 0].sum()
                            ppa_val = total_b_pitches_counted / pa_cnt_counted if pa_cnt_counted > 0 else 0.0

                            st.markdown(f"#### 📊 {fmt_player_name(target_b_player, STATS_NUMBERS)} の打撃指標")
                            b_m1, b_m2, b_m3, b_m4 = st.columns(4)
                            b_m1.metric("通算打率", f"{avg_total:.3f}")
                            b_m2.metric("今季打率 (2026〜)", f"{avg_season:.3f}")
                            b_m3.metric("1打席平均球数(P/PA)", f"{ppa_val:.2f}球" if pa_cnt_counted > 0 else "-")
                            b_m4.metric("総打席数 (2026〜)", f"{int(pa_cnt)} 打席")

                            st.write("")
                            st.divider()

                            st.markdown(f"#### {fmt_player_name(target_b_player, STATS_NUMBERS)} の打球傾向（方向×種類）")

                            def show_player_direction_chart(data_df, title_label):
                                if "打球方向" not in data_df.columns:
                                    return
                                valid_df = data_df[
                                    data_df["打球方向"].notna() & 
                                    (~data_df["打球方向"].astype(str).str.strip().isin(["", "nan", "---"])) &
                                    (~data_df["打球種類"].isin(["その他", "非打球"]))
                                ].copy()
                                
                                if not valid_df.empty:
                                    valid_df["方向"] = valid_df["打球方向"].astype(str).str.strip()
                                    dir_counts = valid_df.groupby(["方向", "打球種類"]).size().reset_index(name="数")

                                    bar_dir = alt.Chart(dir_counts).mark_bar().encode(
                                        x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                                        y=alt.Y("数:Q", title="打球数"),
                                        color=alt.Color("打球種類:N", scale=hit_type_color_scale),
                                        tooltip=["方向", "打球種類", "数"]
                                    ).properties(height=250)
                                    st.altair_chart(bar_dir, use_container_width=True)
                                else:
                                    st.caption(f"（{title_label} の方向データはありません）")

                            st.markdown("**■ 全体 (安打・凡退含む)**")
                            show_player_direction_chart(my_b, "全体")

                            hit_results = ["単打", "二塁打", "三塁打", "本塁打"]
                            out_results = ["凡退(ゴロ)", "凡退(フライ)", "併殺打", "野選", "失策"]
                            st.markdown("**■ 安打時**")
                            show_player_direction_chart(
                                my_b[my_b["結果"].isin(hit_results)], "安打時")
                            st.markdown("**■ 凡退・失策時**")
                            show_player_direction_chart(
                                my_b[my_b["結果"].isin(out_results)], "凡退時")

                            st.divider()
                            st.markdown(
                                f"#### {fmt_player_name(target_b_player, STATS_NUMBERS)} のゴロ/フライ比率 (GO/AO)")
                            my_goro = len(
                                my_b[my_b["結果"].astype(str).str.contains("ゴロ|併殺打")]) if "結果" in my_b.columns else 0
                            my_fly = len(
                                my_b[my_b["結果"].astype(str).str.contains("フライ|犠飛")]) if "結果" in my_b.columns else 0
                            st.metric("ゴロアウト数", my_goro)
                            st.metric("フライアウト数", my_fly)
                            if my_fly > 0:
                                st.metric(
                                    "GO/AO (ゴロ÷フライ)", f"{my_goro / my_fly:.2f}", help="1.0以上ならゴロヒッター、未満ならフライヒッターと言えます。")
                            else:
                                st.write("※ フライアウトが0のため比率計算不可")

                            st.divider()
                            st.markdown(f"#### 🏃 {fmt_player_name(target_b_player, STATS_NUMBERS)} の走者状況別打率")
                            
                            r_col = "ランナー状況" if "ランナー状況" in my_b.columns else ("走者状況" if "走者状況" in my_b.columns else None)
                            if r_col and not my_b[r_col].dropna().empty:
                                my_b_valid_r = my_b[my_b[r_col].notna() & (my_b[r_col] != "") & (my_b[r_col] != "nan")].copy()
                                if not my_b_valid_r.empty:
                                    r_stats = my_b_valid_r.groupby(r_col).agg(
                                        打数=("is_ab", "sum"),
                                        安打=("is_hit", "sum")
                                    ).reset_index()
                                    r_stats["打率"] = r_stats.apply(lambda x: x["安打"] / x["打数"] if x["打数"] > 0 else 0.0, axis=1)
                                    
                                    r_order = ["ランナーなし", "ランナー1塁", "得点圏", "満塁"]
                                    r_stats[r_col] = pd.Categorical(r_stats[r_col], categories=r_order, ordered=True)
                                    r_stats = r_stats.sort_values(r_col).dropna(subset=[r_col])

                                    st.dataframe(
                                        r_stats.style.format({"打率": "{:.3f}"})
                                        .background_gradient(subset=["打率"], cmap="Reds"),
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                else:
                                    st.caption("走者状況のデータがありません。")
                            else:
                                st.caption("走者状況のデータがありません。")

                            st.write("")
                            st.markdown(f"#### ⚾ {fmt_player_name(target_b_player, STATS_NUMBERS)} のボールカウント別打率")
                            
                            cnt_col = None
                            if "ボール" in my_b.columns and "ストライク" in my_b.columns:
                                my_b["ball_count_str"] = my_b.apply(
                                    lambda r: f"{int(float(r['ボール']))}B-{min(2, int(float(r['ストライク'])))}S" 
                                    if pd.notna(r.get("ボール")) and pd.notna(r.get("ストライク")) and str(r.get("ボール")) != "nan" and str(r.get("ストライク")) != "nan" else None, 
                                    axis=1
                                )
                                cnt_col = "ball_count_str"
                            elif "カウント" in my_b.columns:
                                my_b["ball_count_str"] = my_b["カウント"].astype(str).apply(
                                    lambda x: re.sub(r'(\d+)S', lambda m: f"{min(2, int(m.group(1)))}S", x) if x and x != "nan" else None
                                )
                                cnt_col = "ball_count_str"

                            if cnt_col and cnt_col in my_b.columns and not my_b[cnt_col].dropna().empty:
                                my_b_valid_c = my_b[my_b[cnt_col].notna() & (my_b[cnt_col] != "") & (my_b[cnt_col] != "nan")].copy()
                                if not my_b_valid_c.empty:
                                    c_stats = my_b_valid_c.groupby(cnt_col).agg(
                                        打数=("is_ab", "sum"),
                                        四死球=("is_bb", "sum"),
                                        安打=("is_hit", "sum")
                                    ).reset_index()
                                    c_stats["打率"] = c_stats.apply(lambda x: x["安打"] / x["打数"] if x["打数"] > 0 else 0.0, axis=1)
                                    c_stats = c_stats.rename(columns={cnt_col: "カウント"})
                                    c_stats = c_stats[["カウント", "打数", "四死球", "安打", "打率"]]

                                    st.dataframe(
                                        c_stats.style.format({"打率": "{:.3f}"})
                                        .background_gradient(subset=["打率"], cmap="Reds"),
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                else:
                                    st.caption("ボールカウント別のデータがありません。")
                            else:
                                st.caption("ボールカウント別のデータがありません。")
                        else:
                            st.write("該当選手のデータなし")
                else:
                    st.write("対象となる選手がいません")
            else:
                st.info("2026年以降の打撃データがありません")

        # --- 個人の投手分析 ---
        with sub_tab3:
            if df_p_detail.empty or "選手名" not in df_p_detail.columns:
                st.info("2026年以降の投手データがありません")
            else:
                players_p = [p for p in STATS_PLAYERS if p in df_p_detail["選手名"].unique()]

                if not players_p:
                    st.write("対象となる投手がいません")
                else:
                    if "ana_pit_player" not in st.session_state or st.session_state["ana_pit_player"] not in players_p:
                        st.session_state["ana_pit_player"] = None

                    current_pit_player = st.session_state.get("ana_pit_player")
                    popover_label_pit = f"👤 投手選択: {fmt_player_name(current_pit_player, STATS_NUMBERS)} 🔽" if current_pit_player else "👤 投手選択: 未選択 🔽"

                    with st.popover(popover_label_pit, use_container_width=True):
                        st.markdown("##### 👤 分析する投手をタップして選択")
                        st.pills(
                            "分析する投手を選択",
                            players_p,
                            format_func=local_fmt,
                            key="ana_pit_player",
                            label_visibility="collapsed"
                        )

                    target_p_player = st.session_state.get("ana_pit_player")
                    if not target_p_player:
                        st.info("👆 上のボタンから分析する投手を選択してください。")
                    else:
                        my_p = df_p_detail[df_p_detail["選手名"] == target_p_player].copy()
                        
                        if my_p.empty:
                            st.write("該当選手のデータなし")
                        else:
                            if "is_ab" not in my_p.columns or "is_hit" not in my_p.columns or "is_bb" not in my_p.columns:
                                non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
                                is_valid = ~my_p["結果"].astype(str).isin(["", "nan", "None", "-"])
                                is_not_excluded = ~my_p["結果"].astype(str).str.contains(non_ab_pattern, na=False)
                                my_p["is_ab"] = (is_valid & is_not_excluded).astype(int)
                                my_p["is_hit"] = my_p["結果"].astype(str).str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)
                                my_p["is_bb"] = my_p["結果"].astype(str).str.contains("四球|死球|四死球", na=False).astype(int)

                            s_sum = pd.to_numeric(my_p.get("ストライク", 0), errors='coerce').fillna(0).sum()
                            b_sum = pd.to_numeric(my_p.get("ボール", 0), errors='coerce').fillna(0).sum()
                            total_pitches = s_sum + b_sum

                            give_bb = len(my_p[my_p["結果"].astype(str).str.contains("四球|死球|四死球", na=False)]) if "結果" in my_p.columns else 0
                            total_pa_p = len(my_p)
                            bb_rate = (give_bb / total_pa_p * 100) if total_pa_p > 0 else 0.0

                            if "球数" in my_p.columns:
                                r_pitches_p = pd.to_numeric(my_p["球数"], errors='coerce').fillna(0)
                            else:
                                s_p_cnt = pd.to_numeric(my_p.get("ストライク", 0), errors='coerce').fillna(0)
                                b_p_cnt = pd.to_numeric(my_p.get("ボール", 0), errors='coerce').fillna(0)
                                r_pitches_p = s_p_cnt + b_p_cnt

                            my_p_counted = my_p[r_pitches_p > 0]
                            total_p_cnt_counted = r_pitches_p[r_pitches_p > 0].sum()
                            # 打撃・投球結果から正確なアウト数を動的に算出（「野選」を除外）
                            single_out_list = [
                                "三振", "凡退(ゴロ)", "凡退(フライ)", "ゴロ", "フライ", "ライナー",
                                "犠打(ゴロ)", "犠打(フライ)", "犠打", "犠飛",
                                "牽制死", "盗塁死", "走塁死", "振り逃げ三振"
                            ]

                            if "結果" in my_p_counted.columns:
                                res_s = my_p_counted["結果"].astype(str).str.strip()
                                s_outs = len(my_p_counted[res_s.isin(single_out_list)])
                                d_outs = len(my_p_counted[res_s == "併殺打"]) * 2
                                t_outs = len(my_p_counted[res_s == "三重殺"]) * 3
                                outs_sum_counted = s_outs + d_outs + t_outs
                            else:
                                outs_sum_counted = pd.to_numeric(my_p_counted.get("アウト数", 0), errors='coerce').fillna(0).sum()

                            ip_val_counted = outs_sum_counted / 3.0
                            pip_val = total_p_cnt_counted / ip_val_counted if ip_val_counted > 0 else 0.0

                            pip_val = total_p_cnt_counted / ip_val_counted if ip_val_counted > 0 else 0.0

                            st.markdown(f"#### 🎯 {fmt_player_name(target_p_player, STATS_NUMBERS)} の投球カウント・ストライク率")
                            
                            m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
                            if total_pitches > 0:
                                strike_rate = (s_sum / total_pitches) * 100
                                m_col1.metric("ストライク率", f"{strike_rate:.1f}%")
                                m_col2.metric("1回平均球数(P/IP)", f"{pip_val:.2f}球" if ip_val_counted > 0 else "-")
                                m_col3.metric("総投球数", f"{int(total_pitches)} 球")
                                m_col4.metric("ストライク", f"{int(s_sum)} 球")
                                m_col5.metric("ボール", f"{int(b_sum)} 球")
                                m_col6.metric("四死球率", f"{bb_rate:.1f}%")
                            else:
                                m_col1.metric("ストライク率", "-")
                                m_col2.metric("1回平均球数(P/IP)", "-")
                                m_col3.metric("総投球数", "0 球")
                                m_col4.metric("ストライク", "0 球")
                                m_col5.metric("ボール", "0 球")
                                m_col6.metric("四死球率", f"{bb_rate:.1f}%")

                            st.write("")
                            st.divider()

                            st.markdown(f"#### {fmt_player_name(target_p_player, STATS_NUMBERS)} のアウトの取り方")
                            my_p_out_only = my_p[~my_p["結果"].astype(str).str.contains("失策", na=False)] if "結果" in my_p.columns else my_p
                            
                            out_goro = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("ゴロ|併殺打")]) if "結果" in my_p_out_only.columns else 0
                            out_fly = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("フライ")]) if "結果" in my_p_out_only.columns else 0
                            out_so = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("三振")]) if "結果" in my_p_out_only.columns else 0
                            
                            df_my_p_out = pd.DataFrame({"種類": ["ゴロ", "フライ", "三振"], "数": [out_goro, out_fly, out_so]})
                            if df_my_p_out["数"].sum() > 0:
                                pie_my_p = alt.Chart(df_my_p_out).mark_arc(innerRadius=50).encode(
                                    theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロ", "フライ", "三振"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
                                ).properties(height=300)
                                st.altair_chart(pie_my_p, use_container_width=True)
                            else:
                                st.info("詳細なアウトデータがありません。")

                            st.write("")
                            st.divider()
                            
                            st.markdown(f"#### {fmt_player_name(target_p_player, STATS_NUMBERS)} の打たせた打球方向と種類")
                            if "打球方向" in my_p.columns:
                                valid_p_df = my_p[my_p["打球方向"].notna() & 
                                                  (my_p["打球方向"] != "") & 
                                                  (my_p["打球方向"] != "nan") & 
                                                  (my_p["打球方向"] != "---")].copy()
                                
                                if not valid_p_df.empty:
                                    valid_p_df["方向"] = valid_p_df["打球方向"].astype(str).str.strip()
                                    
                                    if "打球種類" not in valid_p_df.columns:
                                        valid_p_df["打球種類"] = "その他"
                                        
                                    def determine_hit_type(res, current_type):
                                        res_s = str(res)
                                        if "本塁打" in res_s: return "本塁打"
                                        if "二塁打" in res_s or "三塁打" in res_s: return "長打"
                                        if "単打" in res_s or "安打" in res_s: return "単打"
                                        if current_type != "その他" and pd.notna(current_type) and current_type != "":
                                            return current_type 
                                        if "ゴロ" in res_s: return "ゴロ"
                                        if "フライ" in res_s or "飛" in res_s: return "フライ"
                                        if "直" in res_s or "ライナー" in res_s: return "ライナー"
                                        return "その他"
                                        
                                    valid_p_df["打球種類"] = valid_p_df.apply(lambda row: determine_hit_type(row.get("結果", ""), row.get("打球種類")), axis=1)
                                    p_indiv_dir_counts = valid_p_df.groupby(["方向", "打球種類"]).size().reset_index(name="数")
                                    
                                    if not p_indiv_dir_counts.empty:
                                        safe_pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                                        bar_p_dir_indiv = alt.Chart(p_indiv_dir_counts).mark_bar().encode(
                                            x=alt.X("方向:N", sort=safe_pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                                            y=alt.Y("数:Q", title="打球数"),
                                            color=alt.Color("打球種類:N", scale=alt.Scale(
                                                domain=["ゴロ", "フライ", "ライナー", "単打", "長打", "本塁打", "その他"], 
                                                range=["#eab308", "#3b82f6", "#22c55e", "#ef4444", "#a855f7", "#ec4899", "#9ca3af"]
                                            )),
                                            tooltip=["方向", "打球種類", "数"]
                                        ).properties(height=250)
                                        st.altair_chart(bar_p_dir_indiv, use_container_width=True)
                                    else:
                                        st.caption("有効な打球方向のデータがありません。")
                                else:
                                    st.caption("打球方向のデータがありません。")
                            else:
                                st.caption("打球方向の列が見つかりません。")
                                
                            st.write("")
                            st.divider()
                            st.markdown(f"#### {fmt_player_name(target_p_player, STATS_NUMBERS)} の被安打・四死球の傾向")
                            if "結果" in my_p.columns:
                                hit_1 = len(my_p[my_p["結果"].astype(str).str.contains("単打|安打")])
                                hit_2 = len(my_p[my_p["結果"].astype(str).str.contains("二塁打")])
                                hit_3 = len(my_p[my_p["結果"].astype(str).str.contains("三塁打")])
                                hit_hr = len(my_p[my_p["結果"].astype(str).str.contains("本塁打")])
                                give_bb = len(my_p[my_p["結果"].astype(str).str.contains("四球|死球")])
                                
                                df_my_p_hit = pd.DataFrame({
                                    "結果": ["単打", "長打(二・三塁打)", "本塁打", "四死球"], "数": [hit_1, hit_2 + hit_3, hit_hr, give_bb]
                                })
                                if df_my_p_hit["数"].sum() > 0:
                                    bar_my_p = alt.Chart(df_my_p_hit).mark_bar().encode(
                                        x=alt.X("結果:N", sort=["単打", "長打(二・三塁打)", "本塁打", "四死球"]), y="数:Q", color=alt.Color("結果:N", legend=None), tooltip=["結果", "数"]
                                    ).properties(height=300)
                                    st.altair_chart(bar_my_p, use_container_width=True)
                                else:
                                    st.info("被安打・四死球の詳細データがありません。")
                            else:
                                st.info("被安打・四死球の詳細データがありません。")

                            st.write("")
                            st.divider()
                            st.markdown(f"#### 🏃 {fmt_player_name(target_p_player, STATS_NUMBERS)} の走者状況別 被打率")
                            
                            r_col_p = "ランナー状況" if "ランナー状況" in my_p.columns else ("走者状況" if "走者状況" in my_p.columns else None)
                            if r_col_p and not my_p[r_col_p].dropna().empty:
                                my_p_valid_r = my_p[my_p[r_col_p].notna() & (my_p[r_col_p] != "") & (my_p[r_col_p] != "nan")].copy()
                                if not my_p_valid_r.empty:
                                    pr_stats = my_p_valid_r.groupby(r_col_p).agg(
                                        打数=("is_ab", "sum"),
                                        被安打=("is_hit", "sum")
                                    ).reset_index()
                                    pr_stats["被打率"] = pr_stats.apply(lambda x: x["被安打"] / x["打数"] if x["打数"] > 0 else 0.0, axis=1)
                                    
                                    r_order = ["ランナーなし", "ランナー1塁", "得点圏", "満塁"]
                                    pr_stats[r_col_p] = pd.Categorical(pr_stats[r_col_p], categories=r_order, ordered=True)
                                    pr_stats = pr_stats.sort_values(r_col_p).dropna(subset=[r_col_p])

                                    st.dataframe(
                                        pr_stats.style.format({"被打率": "{:.3f}"})
                                        .background_gradient(subset=["被打率"], cmap="Blues"),
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                else:
                                    st.caption("走者状況のデータがありません。")
                            else:
                                st.caption("走者状況のデータがありません。")

                            st.write("")
                            st.markdown(f"#### ⚾ {fmt_player_name(target_p_player, STATS_NUMBERS)} のボールカウント別 被打率")
                            
                            cnt_col_p = None
                            if "ボール" in my_p.columns and "ストライク" in my_p.columns:
                                my_p["ball_count_str"] = my_p.apply(
                                    lambda r: f"{int(float(r['ボール']))}B-{min(2, int(float(r['ストライク'])))}S" 
                                    if pd.notna(r.get("ボール")) and pd.notna(r.get("ストライク")) and str(r.get("ボール")) != "nan" and str(r.get("ストライク")) != "nan" else None, 
                                    axis=1
                                )
                                cnt_col_p = "ball_count_str"
                            elif "カウント" in my_p.columns:
                                my_p["ball_count_str"] = my_p["カウント"].astype(str).apply(
                                    lambda x: re.sub(r'(\d+)S', lambda m: f"{min(2, int(m.group(1)))}S", x) if x and x != "nan" else None
                                )
                                cnt_col_p = "ball_count_str"

                            if cnt_col_p and cnt_col_p in my_p.columns and not my_p[cnt_col_p].dropna().empty:
                                my_p_valid_c = my_p[my_p[cnt_col_p].notna() & (my_p[cnt_col_p] != "") & (my_p[cnt_col_p] != "nan")].copy()
                                if not my_p_valid_c.empty:
                                    pc_stats = my_p_valid_c.groupby(cnt_col_p).agg(
                                        打数=("is_ab", "sum"),
                                        四死球=("is_bb", "sum"),
                                        被安打=("is_hit", "sum")
                                    ).reset_index()
                                    pc_stats["被打率"] = pc_stats.apply(lambda x: x["被安打"] / x["打数"] if x["打数"] > 0 else 0.0, axis=1)
                                    pc_stats = pc_stats.rename(columns={cnt_col_p: "カウント"})
                                    pc_stats = pc_stats[["カウント", "打数", "四死球", "被安打", "被打率"]]

                                    st.dataframe(
                                        pc_stats.style.format({"被打率": "{:.3f}"})
                                        .background_gradient(subset=["被打率"], cmap="Blues"),
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                else:
                                    st.caption("ボールカウント別のデータがありません。")
                            else:
                                st.caption("ボールカウント別のデータがありません。")

    # =========================================================
    # Tab 4: 🧠 理想オーダー
    # =========================================================
    with tab4:
        sub_ideal1, sub_ideal2, sub_ideal3 = st.tabs(["👥 本日の参加メンバー", "🌐 推奨オーダー", "📊 打順分析"])

        # --- サブタブ1: 本日の参加メンバーから作成 ---
        with sub_ideal1:
            show_ideal_order_tab(df_batting, df_p_total_base)

        # --- サブタブ2: チーム全打者対象の機械的オーダー算出 ---
        with sub_ideal2:
            st.markdown("### 🤖 チーム全打者の統計データに基づく推奨オーダー（投手も含めたベストオーダー選出）")

            raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
            exclude_set = {normalize_name(n) for n in raw_hidden}

            if not df_b.empty:
                df_calc = df_b[df_b["選手名"] != "チーム記録"].copy()
                df_calc["_temp_norm"] = df_calc["選手名"].apply(normalize_name)
                df_calc = df_calc[~df_calc["_temp_norm"].isin(exclude_set)]

                if df_calc.empty:
                    st.warning("除外設定の結果、表示できるデータがなくなりました。")
                else:
                    agg_dict = {
                        "is_pa": "sum",
                        "is_ab": "sum",
                        "is_hit": "sum",
                        "is_bb": "sum",
                        "is_sf": "sum",
                        "bases": "sum",
                        "盗塁": "sum",
                        "打点": "sum",
                        "is_hr": "sum"
                    }
                    if "is_so" in df_calc.columns:
                        agg_dict["is_so"] = "sum"
                    elif "三振" in df_calc.columns:
                        agg_dict["三振"] = "sum"

                    stats = df_calc.groupby("選手名").agg(agg_dict).reset_index()

                    rename_dict = {
                        "is_pa": "PA",
                        "is_ab": "AB",
                        "is_hit": "Hit",
                        "is_bb": "BB",
                        "is_sf": "SF",
                        "bases": "TB",
                        "盗塁": "SB",
                        "打点": "RBI",
                        "is_hr": "HR"
                    }
                    if "is_so" in stats.columns:
                        rename_dict["is_so"] = "SO"
                    elif "三振" in stats.columns:
                        rename_dict["三振"] = "SO"
                        
                    stats = stats.rename(columns=rename_dict)

                    if "SO" not in stats.columns:
                        stats["SO"] = 0

                    max_ab = int(stats["AB"].max()) if not stats.empty else 0
                    default_ab = min(30, max_ab)
                    min_ab = st.slider("対象とする最低打数", 0, max_ab, default_ab, key="analysis_tab4_min_ab_slider")
                    stats = stats[stats["AB"] >= min_ab]

                    if not stats.empty:
                        stats["AVG"] = stats.apply(lambda x: x["Hit"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                        stats["OBP_Denom"] = stats["AB"] + stats["BB"] + stats["SF"]
                        stats["OBP"] = stats.apply(lambda x: (x["Hit"] + x["BB"]) / x["OBP_Denom"] if x["OBP_Denom"] > 0 else 0, axis=1)
                        stats["SLG"] = stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                        stats["OPS"] = stats["OBP"] + stats["SLG"]
                        stats["K_rate"] = stats.apply(lambda x: x["SO"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
                        
                        stats["RC"] = stats.apply(
                            lambda x: ((x["Hit"] + x["BB"]) * x["TB"]) / (x["AB"] + x["BB"]) if (x["AB"] + x["BB"]) > 0 else 0, 
                            axis=1
                        )
                        stats["RC_per_PA"] = stats.apply(lambda x: x["RC"] / x["PA"] if x["PA"] > 0 else 0, axis=1)

                        candidates = stats.copy()

                        candidates["Score_1"] = (
                            candidates["OBP"] * 2.0
                            + candidates["RC_per_PA"] * 0.5
                            + candidates["SB"] * 0.02
                            - candidates["K_rate"] * 0.8
                        )

                        candidates["Score_2"] = (
                            candidates["OPS"] * 2.5
                            + candidates["OBP"] * 1.0
                            + candidates["RC_per_PA"] * 0.5
                        )

                        candidates["Score_3"] = (
                            candidates["OPS"] * 3.0
                            + candidates["RC_per_PA"] * 0.6
                        )

                        candidates["Score_4"] = (
                            candidates["OPS"] * 2.2
                            + candidates["SLG"] * 0.8
                        )

                        candidates["Score_5"] = (
                            candidates["OPS"] * 2.0
                            + candidates["SLG"] * 0.4
                        )

                        candidates["Score_6"] = (
                            candidates["OPS"] * 1.8
                            + candidates["RC_per_PA"] * 0.4
                        )

                        candidates["Score_7"] = (
                            candidates["OBP"] * 1.5
                            + candidates["OPS"] * 0.7
                        )

                        candidates["Score_8"] = (
                            candidates["OPS"] * 1.3
                            + candidates["OBP"] * 0.3
                        )

                        candidates["Score_9"] = (
                            candidates["OBP"] * 2.0
                            + candidates["SB"] * 0.02
                            - candidates["K_rate"] * 0.6
                        )

                        ace_player = None
                        if not df_p_total_base.empty:
                            df_p_calc = df_p_total_base[df_p_total_base["選手名"] != "チーム記録"].copy()
                            if not df_p_calc.empty:
                                for c in ["自責点", "失点", "アウト数", "is_so", "奪三振"]:
                                    if c not in df_p_calc.columns:
                                        df_p_calc[c] = 0
                                    df_p_calc[c] = pd.to_numeric(df_p_calc[c], errors='coerce').fillna(0)
                                
                                temp_so = df_p_calc["結果"].isin(["三振", "振り逃げ三振"]).astype(int) if "結果" in df_p_calc.columns else 0
                                df_p_calc["total_so"] = df_p_calc[["奪三振", "is_so"]].max(axis=1) if "奪三振" in df_p_calc.columns else temp_so

                                p_agg = df_p_calc.groupby("選手名").agg(
                                    outs=("アウト数", "sum"),
                                    er=("自責点", "sum"),
                                    so=("total_so", "sum")
                                ).reset_index()

                                p_agg["投球回"] = p_agg["outs"] / 3
                                p_agg["投手_防御率"] = p_agg.apply(lambda x: (x["er"] * 7) / x["投球回"] if x["投球回"] > 0 else 99.0, axis=1)

                                def calc_pitching_score(row):
                                    p_inn = row.get("投球回", 0)
                                    p_era = row.get("投手_防御率", 99.0)
                                    p_so = row.get("so", 0)
                                    if p_inn <= 0 or p_era >= 90:
                                        return 0.0
                                    inn_pts = p_inn * 1.0
                                    so_pts = p_so * 0.3
                                    if p_era <= 3.50:
                                        era_pts = (3.50 - p_era) * p_inn * 0.5
                                    else:
                                        era_pts = (3.50 - p_era) * p_inn * 0.2
                                    return max(0.0, inn_pts + so_pts + era_pts)

                                p_agg["Pitching_Score"] = p_agg.apply(calc_pitching_score, axis=1)
                                
                                valid_candidates = set(candidates["選手名"])
                                p_agg_filtered = p_agg[p_agg["選手名"].isin(valid_candidates)]
                                
                                p_sorted = p_agg_filtered.sort_values(by="Pitching_Score", ascending=False)
                                if not p_sorted.empty and p_sorted.iloc[0]["Pitching_Score"] > 0:
                                    ace_player = p_sorted.iloc[0]["選手名"]
                                elif not p_sorted.empty and p_sorted["outs"].max() > 0:
                                    p_sorted_by_outs = p_agg_filtered.sort_values(by="outs", ascending=False)
                                    ace_player = p_sorted_by_outs.iloc[0]["選手名"]

                        used_players = []
                        lineup = {}
                        assigned_positions = {}

                        def assign_player(order, sort_col, force_ace=False):
                            if force_ace and ace_player and ace_player not in used_players:
                                ace_row = candidates[candidates["選手名"] == ace_player]
                                if not ace_row.empty:
                                    used_players.append(ace_player)
                                    lineup[order] = ace_row.iloc[0]
                                    return

                            available = candidates[~candidates["選手名"].isin(used_players)].sort_values(sort_col, ascending=False)
                            if not available.empty:
                                p = available.iloc[0]
                                used_players.append(p["選手名"])
                                lineup[order] = p
                            else:
                                lineup[order] = None

                        assign_player(3, "Score_3")
                        assign_player(1, "Score_1")
                        assign_player(2, "Score_2")
                        assign_player(4, "Score_4")
                        assign_player(5, "Score_5")
                        assign_player(6, "Score_6")
                        assign_player(7, "Score_7")
                        assign_player(8, "Score_8")
                        assign_player(9, "Score_9", force_ace=True)

                        FIELD_POSITIONS = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                        available_positions = set(FIELD_POSITIONS)
                        
                        if ace_player:
                            assigned_positions[ace_player] = "投"
                            if "投" in available_positions:
                                available_positions.remove("投")

                        other_used = [p for p in used_players if p != ace_player]
                        
                        pos_col_name = "位置" if "位置" in df_calc.columns else ("守備位置" if "守備位置" in df_calc.columns else ("守備" if "守備" in df_calc.columns else None))
                        p_df = df_calc[df_calc["選手名"].isin(other_used) & df_calc[pos_col_name].isin(FIELD_POSITIONS)] if pos_col_name else pd.DataFrame()
                        
                        if not p_df.empty:
                            pos_counts = p_df.groupby(["選手名", pos_col_name]).size().reset_index(name="count")
                            pos_counts = pos_counts.sort_values("count", ascending=False)
                        else:
                            pos_counts = pd.DataFrame(columns=["選手名", pos_col_name if pos_col_name else "位置", "count"])
                        
                        for _, row in pos_counts.iterrows():
                            player = row["選手名"]
                            pos = row[pos_col_name]
                            if player not in assigned_positions and pos in available_positions:
                                assigned_positions[player] = pos
                                available_positions.remove(pos)
                                
                        for player in used_players:
                            if player not in assigned_positions:
                                if available_positions:
                                    assigned_positions[player] = available_positions.pop()
                                else:
                                    assigned_positions[player] = "DH/控"

                        roles_info = {
                            1: ("最強のチャンスメーカー", "OBP*2.0 + RC/PA*0.5 + SB*0.02 - K*0.8", "Score_1"),
                            2: ("万能型（最強打者候補）", "OPS*2.5 + OBP*1.0 + RC/PA*0.5", "Score_2"),
                            3: ("チーム最強打者", "OPS*3.0 + RC/PA*0.6", "Score_3"),
                            4: ("最大のダメージソース", "OPS*2.2 + SLG*0.8", "Score_4"),
                            5: ("4番を支える打者", "OPS*2.0 + SLG*0.4", "Score_5"),
                            6: ("第3のクリーンナップ", "OPS*1.8 + RC/PA*0.4", "Score_6"),
                            7: ("下位打線の起点", "OBP*1.5 + OPS*0.7", "Score_7"),
                            8: ("残りの中では打力重視", "OPS*1.3 + OBP*0.3", "Score_8"),
                            9: ("第2のリードオフ", "OBP*2.0 + SB*0.02 - K*0.6", "Score_9")
                        }

                        for i in range(1, 10):
                            role_name, desc, sort_col = roles_info[i]
                            p = lineup.get(i)
                            if p is not None:
                                player_name = p['選手名']
                                assigned_pos = assigned_positions.get(player_name, "不明")
                                st.markdown(f"##### {i}番 ({assigned_pos}): {role_name}")
                                st.caption(f"選出基準: {desc}")
                                
                                pitcher_text = ""
                                if assigned_pos == "投" and not df_p_total_base.empty:
                                    p_rows = df_p_total_base[(df_p_total_base["選手名"] == player_name) & (df_p_total_base["選手名"] != "チーム記録")]
                                    if not p_rows.empty:
                                        outs_sum = pd.to_numeric(p_rows["アウト数"], errors='coerce').fillna(0).sum() if "アウト数" in p_rows.columns else len(p_rows) * 3
                                        ip_val = outs_sum / 3.0
                                        run_col = "自責点" if "自責点" in p_rows.columns else ("失点" if "失点" in p_rows.columns else None)
                                        er_sum = pd.to_numeric(p_rows[run_col], errors='coerce').fillna(0).sum() if run_col and run_col in p_rows.columns else 0
                                        era = (er_sum * 7) / ip_val if ip_val > 0 else 0.0
                                        
                                        so_col = "is_so" if "is_so" in p_rows.columns else ("三振" if "三振" in p_rows.columns else None)
                                        so_val = pd.to_numeric(p_rows[so_col], errors='coerce').fillna(0).sum() if so_col and so_col in p_rows.columns else 0
                                        if "奪三振" in p_rows.columns:
                                            so_val = max(so_val, pd.to_numeric(p_rows["奪三振"], errors='coerce').fillna(0).sum())
                                        
                                        ip_str = f"{int(ip_val//1)}.{int(round((ip_val%1)*3))}"
                                        pitcher_text = f"\n\n⚾ **【通算投手成績】** 投球回(IP): {ip_str} | 防御率(ERA): {era:.2f} | 奪三振: {int(so_val)}"

                                score_val = p.get(sort_col, 0)
                                st.success(
                                    f"**{player_name}**\n\n"
                                    f"評価値({sort_col}): **{score_val:.3f}** | "
                                    f"打率: {p['AVG']:.3f} | 出塁率: {p['OBP']:.3f} | 長打率: {p['SLG']:.3f} | OPS: {p['OPS']:.3f} | RC/PA: {p['RC_per_PA']:.3f}\n\n"
                                    f"本塁打: {int(p['HR'])} | 打点: {int(p['RBI'])} | 盗塁: {int(p['SB'])} | 三振率: {p['K_rate']:.3f}{pitcher_text}"
                                )
                            else:
                                st.markdown(f"##### {i}番: {role_name}")
                                st.info("候補選手なし")  
                                
                        st.divider()
                    else:
                        st.info("条件を満たす選手がいません。")
            else:
                st.info("データがありません。")

        # --- サブタブ3: 打順分析 ---
        with sub_ideal3:
            st.markdown("### 📊 チーム全体の打順別成績（9番までの試合のみ）")
            st.caption("チーム全体を通しての、打順ごとの実績データです。ベンチメンバー等で10番以降が出場した試合を除外し、9人制の試合のみを対象に集計しています。")

            local_type = st.radio("試合種別を選択してください", ["通算(すべて)", "公式戦のみ", "練習試合のみ"], horizontal=True, key="order_analysis_type")

            if not df_b_unfiltered.empty:
                df_order_base = df_b_unfiltered.copy()

                if selected_year != "全期間" and "Year" in df_order_base.columns:
                    df_order_base = df_order_base[df_order_base["Year"] == selected_year]

                if local_type == "公式戦のみ" and "試合種別" in df_order_base.columns:
                    df_order_base = df_order_base[df_order_base["試合種別"].isin(OFFICIAL_GAME_TYPES)]
                elif local_type == "練習試合のみ" and "試合種別" in df_order_base.columns:
                    df_order_base = df_order_base[df_order_base["試合種別"] == "練習試合"]

                df_order = df_order_base[df_order_base["選手名"] != "チーム記録"].copy()
                
                def safe_extract_order(val):
                    if pd.isna(val) or str(val).strip() == "":
                        return np.nan
                    s = unicodedata.normalize('NFKC', str(val))
                    m = re.search(r'(\d+)', s)
                    return int(m.group(1)) if m else np.nan

                if "打順" in df_order.columns:
                    df_order["打順_num"] = df_order["打順"].apply(safe_extract_order)
                    df_order_base["打順_num"] = df_order_base["打順"].apply(safe_extract_order)

                    merge_cols = [c for c in ["Date", "対戦相手", "試合種別"] if c in df_order_base.columns]
                    if merge_cols:
                        game_max_order = df_order_base.groupby(merge_cols)["打順_num"].max().reset_index()
                        valid_games = game_max_order[(game_max_order["打順_num"] >= 1) & (game_max_order["打順_num"] <= 9)][merge_cols]
                        
                        df_order_base = pd.merge(df_order_base, valid_games, on=merge_cols, how="inner")
                        df_order = pd.merge(df_order, valid_games, on=merge_cols, how="inner")

                    df_order = df_order[(df_order["打順_num"] >= 1) & (df_order["打順_num"] <= 9)]
                    df_order["打順_num"] = df_order["打順_num"].astype(int)

                    total_games_local = len(df_order_base[merge_cols].drop_duplicates()) if merge_cols else 0

                    if not df_order.empty and total_games_local > 0:
                        order_stats = df_order.groupby("打順_num").agg(
                            PA=("is_pa", "sum"),
                            AB=("is_ab", "sum"),
                            Hit=("is_hit", "sum"),
                            BB=("is_bb", "sum"),
                            SF=("is_sf", "sum"),
                            SH=("is_sh", "sum"),
                            TB=("bases", "sum"),
                            RBI=("打点", "sum"),
                            HR=("is_hr", "sum")
                        ).reset_index()
                        
                        order_stats["1試合PA"] = order_stats["PA"] / total_games_local

                        order_stats["AVG"] = order_stats.apply(lambda x: x["Hit"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                        order_stats["OBP_Denom"] = order_stats["AB"] + order_stats["BB"] + order_stats["SF"]
                        order_stats["OBP"] = order_stats.apply(
                            lambda x: (x["Hit"] + x["BB"]) / x["OBP_Denom"] if x["OBP_Denom"] > 0 else 0, axis=1
                        )
                        order_stats["SLG"] = order_stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                        order_stats["OPS"] = order_stats["OBP"] + order_stats["SLG"]
                        
                        order_stats["RC"] = order_stats.apply(
                            lambda x: ((x["Hit"] + x["BB"]) * x["TB"]) / (x["AB"] + x["BB"]) if (x["AB"] + x["BB"]) > 0 else 0, 
                            axis=1
                        )

                        disp_df = order_stats[["打順_num", "1試合PA", "AVG", "OBP", "OPS", "RC", "HR", "RBI"]].copy()
                        disp_df = disp_df.rename(columns={"打順_num": "打順", "AVG": "打率", "OBP": "出塁率", "RC": "RC", "HR": "本塁打", "RBI": "打点"})
                        disp_df["打順"] = disp_df["打順"].astype(str) + "番"

                        st.dataframe(
                            disp_df.style.format({
                                "1試合PA": "{:.2f}",
                                "打率": "{:.3f}",
                                "出塁率": "{:.3f}",
                                "OPS": "{:.3f}",
                                "RC": "{:.2f}",
                                "本塁打": "{:.0f}",
                                "打点": "{:.0f}"
                            }).background_gradient(subset=["OPS"], cmap="Oranges"),
                            use_container_width=True,
                            hide_index=True
                        )

                        st.caption(f"📈 打順別のOPS（折れ線）と 1試合あたり打席数（棒） ※対象試合数(9番までだった試合): {total_games_local}試合")
                        base_chart = alt.Chart(order_stats).encode(x=alt.X("打順_num:O", title="打順", axis=alt.Axis(labelAngle=0)))
                        
                        bar = base_chart.mark_bar(opacity=0.4, color="#64748b").encode(
                            y=alt.Y("1試合PA:Q", title="1試合あたりの打席数", scale=alt.Scale(domain=[0, order_stats["1試合PA"].max() * 1.2]))
                        )
                        line = base_chart.mark_line(point=True, color="#ea580c", strokeWidth=3).encode(
                            y=alt.Y("OPS:Q", title="OPS", scale=alt.Scale(domain=[0, order_stats["OPS"].max() * 1.2]))
                        )
                        
                        st.altair_chart((bar + line).resolve_scale(y="independent"), use_container_width=True)
                    else:
                        st.info("9番までだった有効な試合データがありません。")
                else:
                    st.info("打順データが存在しません。")
            else:
                st.info("分析するデータがありません。")