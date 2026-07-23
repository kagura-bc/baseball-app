import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from config.settings import OFFICIAL_GAME_TYPES
# 🌟 ideal_order ビューの読み込み
from views.ideal_order import show_ideal_order_tab

# =========================================================
# 共通関数
# =========================================================

FIXED_EXCLUDE_LIST = [
    "助っ人1", "助っ人2", "依田裕樹", "小峠海晴"
]


def normalize_name(name):
    """名前からスペースを除去する"""
    return str(name).replace(" ", "").replace(" ", "").strip()


def get_exclude_set():
    """Secretsから除外リストを読み込み、固定リストと結合して集合(set)にして返す"""
    raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
    combined_list = list(raw_hidden) + FIXED_EXCLUDE_LIST
    return {normalize_name(n) for n in combined_list}


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

    exclude_set = get_exclude_set()

    if df_batting.empty and df_pitching.empty:
        st.info("分析するデータがありません。")
        return

    df_b = filter_players(df_batting.copy(), exclude_set)
    df_p = filter_players(df_pitching.copy(), exclude_set)

    # 🌟 絞り込み前の全期間投手データを「通算成績用」として保持
    df_p_total_base = df_p.copy()

    # =========================================================
    # analysis.py 側でも is_ab や is_hit を計算する
    # =========================================================

    required_columns = ["is_hit", "is_ab", "is_hr", "is_so", "is_1b",
                        "is_2b", "is_3b", "is_bb", "is_sf", "bases", "打点", "盗塁", "得点"]
    for col in required_columns:
        if col not in df_b.columns:
            df_b[col] = 0

    if not df_b.empty and "結果" in df_b.columns:
        df_b["結果"] = df_b["結果"].astype(str).str.replace(r"\s+", "", regex=True)

        df_b["is_hit"] = df_b["結果"].str.contains(
            "単打|二塁打|三塁打|本塁打", na=False).astype(int)

        non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
        is_valid = ~df_b["結果"].isin(["", "nan", "None", "-"])
        is_not_excluded = ~df_b["結果"].str.contains(non_ab_pattern, na=False)
        df_b["is_ab"] = (is_valid & is_not_excluded).astype(int)

        df_b["is_hr"] = df_b["結果"].str.contains("本塁打", na=False).astype(int)
        df_b["is_so"] = df_b["結果"].str.contains("三振", na=False).astype(int)
        df_b["is_1b"] = df_b["結果"].str.contains("単打", na=False).astype(int)
        df_b["is_2b"] = df_b["結果"].str.contains("二塁打", na=False).astype(int)
        df_b["is_3b"] = df_b["結果"].str.contains("三塁打", na=False).astype(int)
        df_b["is_bb"] = df_b["結果"].str.contains(
            "四球|死球|四死球", na=False).astype(int)
        df_b["is_sf"] = df_b["結果"].str.contains("犠飛", na=False).astype(int)

        df_b["bases"] = (
            df_b["is_1b"] * 1 + df_b["is_2b"] * 2 +
            df_b["is_3b"] * 3 + df_b["is_hr"] * 4
        )

        for c in ["打点", "盗塁", "得点"]:
            df_b[c] = pd.to_numeric(df_b[c], errors='coerce').fillna(0)

    # =========================================================
    # 名前の強力クリーニング
    # =========================================================
    df_b["選手名"] = df_b["選手名"].astype(str).str.replace(" ", " ").str.strip()

    # ---------------------------------------------------------
    # 日付変換とYear列の作成
    # ---------------------------------------------------------
    df_b["Date"] = pd.to_datetime(df_b["日付"], errors='coerce')
    df_p["Date"] = pd.to_datetime(df_p["日付"], errors='coerce')

    df_b["Year"] = df_b["Date"].dt.year.astype(
        str).str.replace('.0', '', regex=False)
    df_p["Year"] = df_p["Date"].dt.year.astype(
        str).str.replace('.0', '', regex=False)

    years = sorted([y for y in df_b["Year"].unique()
                   if y not in ['nan', 'NaT']], reverse=True)
    c1, c2 = st.columns(2)
    selected_year = c1.selectbox("対象年度", ["全期間"] + list(years))

    game_types = ["すべて", "公式戦のみ", "練習試合のみ"]
    selected_type = c2.selectbox("試合種別", game_types)

    if selected_year != "全期間":
        df_b = df_b[df_b["Year"] == selected_year]
        df_p = df_p[df_p["Year"] == selected_year]

    if selected_type == "公式戦のみ":
        df_b = df_b[df_b["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        df_p = df_p[df_p["試合種別"].isin(OFFICIAL_GAME_TYPES)]
    elif selected_type == "練習試合のみ":
        df_b = df_b[df_b["試合種別"] == "練習試合"]
        df_p = df_p[df_p["試合種別"] == "練習試合"]

    # ---------------------------------------------------------
    # ゲーム単位のデータセット作成 (得点計算 + FirstScore判定)
    # ---------------------------------------------------------
    games_list = []
    for (d, opp, m_type), g_b in df_b.groupby(["Date", "対戦相手", "試合種別"]):
        g_p = df_p[(df_p["Date"] == d) & (df_p["対戦相手"] == opp)
                   & (df_p["試合種別"] == m_type)]

        is_team_rec = g_b["選手名"].astype(str).str.contains("チーム記録", na=False)
        team_rows = g_b[is_team_rec]
        indiv_rows = g_b[~is_team_rec]

        if not team_rows.empty:
            my_score = pd.to_numeric(
                team_rows["得点"], errors='coerce').fillna(0).sum()
        else:
            my_score = pd.to_numeric(
                indiv_rows["得点"], errors='coerce').fillna(0).sum()

        is_p_team_rec = g_p["選手名"].astype(str).str.contains("チーム記録", na=False)
        p_team_rows = g_p[is_p_team_rec]
        p_indiv_rows = g_p[~is_p_team_rec]

        if not p_team_rows.empty:
            opp_score = pd.to_numeric(
                p_team_rows["失点"], errors='coerce').fillna(0).sum()
        else:
            opp_score = pd.to_numeric(
                p_indiv_rows["失点"], errors='coerce').fillna(0).sum()

        res = "Win" if my_score > opp_score else (
            "Lose" if my_score < opp_score else "Draw")

        def get_inn_num(t):
            t = str(t).replace("回", "")
            return int(t) if t.isdigit() else 99

        my_inn_scores = g_b[g_b["イニング"].astype(str).str.contains("回")].copy()
        my_inn_scores["InnNum"] = my_inn_scores["イニング"].apply(get_inn_num)
        my_score_inns = my_inn_scores[pd.to_numeric(
            my_inn_scores["得点"], errors='coerce') > 0].sort_values("InnNum")
        min_my_inn = my_score_inns["InnNum"].iloc[0] if not my_score_inns.empty else 99

        opp_inn_scores = g_p[g_p["イニング"].astype(str).str.contains("回")].copy()
        opp_inn_scores["InnNum"] = opp_inn_scores["イニング"].apply(get_inn_num)
        opp_score_inns = opp_inn_scores[pd.to_numeric(
            opp_inn_scores["失点"], errors='coerce') > 0].sort_values("InnNum")
        min_opp_inn = opp_score_inns["InnNum"].iloc[0] if not opp_score_inns.empty else 99

        first_score_team = "自チーム" if min_my_inn < min_opp_inn else (
            "相手" if min_opp_inn < min_my_inn else "なし(0-0)")

        games_list.append({
            "Date": d, "Opponent": opp, "MyScore": my_score,
            "OppScore": opp_score, "Result": res, "FirstScore": first_score_team
        })

    df_games = pd.DataFrame(games_list)

    # ---------------------------------------------------------
    # タブ構成
    # ---------------------------------------------------------
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
                cols[i].caption(
                    f"<div style='text-align:center;'>{r['Date'].strftime('%m/%d')}</div>", unsafe_allow_html=True)

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
            ].mean()
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

            with col_bot2:
                st.caption("イニング別の得点力・失点傾向")

                def aggregate_innings(df_raw, score_col):
                    df_i = df_raw.copy()
                    df_i = df_i[df_i["イニング"].astype(
                        str).str.match(r"^[1-9]回$")]
                    df_i["得点"] = pd.to_numeric(
                        df_i[score_col], errors='coerce').fillna(0)
                    return df_i.groupby("イニング")["得点"].sum()

                inn_scores = aggregate_innings(df_b, "得点")
                inn_lost = aggregate_innings(df_p, "失点")

                df_inn = pd.DataFrame(
                    {"得点": inn_scores, "失点": inn_lost}).fillna(0).reset_index()
                df_inn["InnNum"] = df_inn["イニング"].apply(
                    lambda x: int(x.replace("回", "")))
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
        ) if not df_batting.empty else pd.DataFrame()
        df_p_detail = df_pitching[pd.to_datetime(df_pitching["日付"], errors='coerce').dt.year >= 2026].copy(
        ) if not df_pitching.empty else pd.DataFrame()

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
            domain=["ゴロ", "フライ", "ライナー", "安打", "非打球", "その他"],
            range=["#eab308", "#3b82f6", "#22c55e",
                   "#ef4444", "#64748b", "#9ca3af"]
        )
        pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

        sub_tab1, sub_tab2, sub_tab3 = st.tabs(
            ["🏢 チーム全体の傾向", "🏏 個人の打撃分析", "⚾ 個人の投手分析"])

        # --- チーム全体の傾向 ---
        with sub_tab1:
            st.markdown("#### 🏢 チーム全体のプレースタイル")

            st.markdown("##### チーム打球傾向 (アウトの内訳)")
            if not df_b_detail.empty:
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
            st.markdown("##### チーム投手陣のアウト取得傾向")
            if not df_p_detail.empty:
                df_p_out_only = df_p_detail[~df_p_detail["結果"].astype(
                    str).str.contains("失策|振り逃げ", na=False)]

                p_goro = len(
                    df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("ゴロ|併殺打")])
                p_fly = len(
                    df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("フライ")])
                p_so = len(
                    df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("三振")])

                df_p_out = pd.DataFrame(
                    {"種類": ["ゴロで打たせてとる", "フライアウト", "三振で奪う"], "数": [p_goro, p_fly, p_so]})
                if df_p_out["数"].sum() > 0:
                    pie_p_out = alt.Chart(df_p_out).mark_arc(innerRadius=40).encode(
                        theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロで打たせてとる", "フライアウト", "三振で奪う"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
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
                if "打球方向" in df_b_detail.columns:
                    b_dir_data = df_b_detail[df_b_detail["打球方向"].notna() & (
                        df_b_detail["打球方向"] != "") & (df_b_detail["打球方向"] != "nan")].copy()
                    if not b_dir_data.empty:
                        b_dir_data["方向"] = b_dir_data["打球方向"].astype(
                            str).str.strip()
                        b_dir_counts = b_dir_data.groupby(
                            ["方向", "打球種類"]).size().reset_index(name="数")

                        bar_b_dir = alt.Chart(b_dir_counts).mark_bar().encode(
                            x=alt.X("方向:N", sort=pos_order, title="ポジション",
                                    axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("数:Q", title="打球数"),
                            color=alt.Color(
                                "打球種類:N", scale=hit_type_color_scale),
                            tooltip=["方向", "打球種類", "数"]
                        ).properties(height=280)
                        st.altair_chart(bar_b_dir, use_container_width=True)
                    else:
                        st.caption("データがありません")

            with c_dir2:
                st.markdown("**▼ チーム投手陣 (どこへ・どんな打球を打たせているか)**")
                if "打球方向" in df_p_detail.columns:
                    p_dir_data = df_p_detail[df_p_detail["打球方向"].notna() & (
                        df_p_detail["打球方向"] != "") & (df_p_detail["打球方向"] != "nan")].copy()
                    if not p_dir_data.empty:
                        p_dir_data["方向"] = p_dir_data["打球方向"].astype(
                            str).str.strip()
                        p_dir_counts = p_dir_data.groupby(
                            ["方向", "打球種類"]).size().reset_index(name="数")

                        bar_p_dir = alt.Chart(p_dir_counts).mark_bar().encode(
                            x=alt.X("方向:N", sort=pos_order, title="ポジション",
                                    axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("数:Q", title="打球数"),
                            color=alt.Color(
                                "打球種類:N", scale=hit_type_color_scale),
                            tooltip=["方向", "打球種類", "数"]
                        ).properties(height=280)
                        st.altair_chart(bar_p_dir, use_container_width=True)
                    else:
                        st.caption("データがありません")

        # --- 個人の打撃分析 ---
        with sub_tab2:
            if not df_b_detail.empty:
                players_b = sorted(
                    df_b_detail[df_b_detail["選手名"] != "チーム記録"]["選手名"].dropna().unique())
                if players_b:
                    target_b_player = st.selectbox(
                        "分析する打者を選択", players_b, key="ana_bat_player")
                    my_b = df_b_detail[df_b_detail["選手名"]
                                       == target_b_player].copy()

                    if not my_b.empty:
                        st.markdown(f"#### {target_b_player} の打球傾向（方向×種類）")

                        def show_player_direction_chart(data_df, title_label):
                            if "打球方向" not in data_df.columns:
                                return
                            valid_df = data_df[data_df["打球方向"].notna() & (
                                data_df["打球方向"] != "") & (data_df["打球方向"] != "nan")].copy()
                            if not valid_df.empty:
                                valid_df["方向"] = valid_df["打球方向"].astype(
                                    str).str.strip()
                                dir_counts = valid_df.groupby(
                                    ["方向", "打球種類"]).size().reset_index(name="数")

                                bar_dir = alt.Chart(dir_counts).mark_bar().encode(
                                    x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(
                                        labelAngle=0)),
                                    y=alt.Y("数:Q", title="打球数"),
                                    color=alt.Color(
                                        "打球種類:N", scale=hit_type_color_scale),
                                    tooltip=["方向", "打球種類", "数"]
                                ).properties(height=250)
                                st.altair_chart(
                                    bar_dir, use_container_width=True)
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
                            f"#### {target_b_player} のゴロ/フライ比率 (GO/AO)")
                        my_goro = len(
                            my_b[my_b["結果"].astype(str).str.contains("ゴロ|併殺打")])
                        my_fly = len(
                            my_b[my_b["結果"].astype(str).str.contains("フライ|犠飛")])
                        st.metric("ゴロアウト数", my_goro)
                        st.metric("フライアウト数", my_fly)
                        if my_fly > 0:
                            st.metric(
                                "GO/AO (ゴロ÷フライ)", f"{my_goro / my_fly:.2f}", help="1.0以上ならゴロヒッター、未満ならフライヒッターと言えます。")
                        else:
                            st.write("※ フライアウトが0のため比率計算不可")
                    else:
                        st.write("該当選手のデータなし")
                else:
                    st.write("対象となる選手がいません")
            else:
                st.info("2026年以降の打撃データがありません")

        # --- 個人の投手分析 ---
        with sub_tab3:
            if df_p_detail.empty:
                st.info("2026年以降の投手データがありません")
            else:
                players_p = sorted(df_p_detail[(df_p_detail["選手名"] != "チーム記録") & (df_p_detail["選手名"].notna())]["選手名"].unique())
                if not players_p:
                    st.write("対象となる投手がいません")
                else:
                    target_p_player = st.selectbox("分析する投手を選択", players_p, key="ana_pit_player")
                    my_p = df_p_detail[df_p_detail["選手名"] == target_p_player].copy()
                    
                    if my_p.empty:
                        st.write("該当選手のデータなし")
                    else:
                        st.markdown(f"#### {target_p_player} のアウトの取り方")
                        my_p_out_only = my_p[~my_p["結果"].astype(str).str.contains("失策", na=False)]
                        
                        out_goro = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("ゴロ|併殺打")])
                        out_fly = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("フライ")])
                        out_so = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("三振")])
                        
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
                        
                        st.markdown(f"#### {target_p_player} の打たせた打球方向と種類")
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
                                    
                                valid_p_df["打球種類"] = valid_p_df.apply(lambda row: determine_hit_type(row["結果"], row.get("打球種類")), axis=1)
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
                        st.markdown(f"#### {target_p_player} の被安打・四死球の傾向")
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

    # =========================================================
    # Tab 4: 🧠 理想オーダー
    # =========================================================
    with tab4:
        sub_ideal1, sub_ideal2 = st.tabs(["👥 本日の参加メンバーで作成", "🌐 チーム全打者の推奨オーダー"])

        # --- サブタブ1: 本日の参加メンバーから作成 ---
        with sub_ideal1:
            # 🌟 通算用の全投手データ（df_p_total_base）を渡す
            show_ideal_order_tab(df_batting, df_p_total_base)

        # --- サブタブ2: チーム全打者対象の機械的オーダー算出 ---
        with sub_ideal2:
            st.markdown("### 🤖 チーム全打者の統計データに基づく推奨オーダー（投手も含めたベストオーダー選出）")

            raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
            fixed_list = st.secrets.get("FIXED_EXCLUDE_LIST", [])

            all_exclude_names = raw_hidden + fixed_list
            exclude_set = {normalize_name(n) for n in all_exclude_names}

            if not df_b.empty:
                df_calc = df_b[df_b["選手名"] != "チーム記録"].copy()
                df_calc["_temp_norm"] = df_calc["選手名"].apply(normalize_name)
                df_calc = df_calc[~df_calc["_temp_norm"].isin(exclude_set)]

                if df_calc.empty:
                    st.warning("除外設定の結果、表示できるデータがなくなりました。")
                else:
                    agg_dict = {
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
                        # 指標計算
                        stats["PA"] = stats["AB"] + stats["BB"] + stats["SF"]
                        stats["AVG"] = stats.apply(lambda x: x["Hit"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                        stats["OBP"] = stats.apply(lambda x: (x["Hit"] + x["BB"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
                        stats["SLG"] = stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                        stats["OPS"] = stats["OBP"] + stats["SLG"]
                        stats["K_rate"] = stats.apply(lambda x: x["SO"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
                        
                        stats["RC"] = stats.apply(
                            lambda x: ((x["Hit"] + x["BB"]) * x["TB"]) / (x["AB"] + x["BB"]) if (x["AB"] + x["BB"]) > 0 else 0, 
                            axis=1
                        )
                        stats["RC_per_PA"] = stats.apply(lambda x: x["RC"] / x["PA"] if x["PA"] > 0 else 0, axis=1)

                        candidates = stats.copy()

                        # 🌟 各打順の専用スコア適用
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

                        # 🌟 1. 通算の「投手部門・貢献度ランキング」に基づいてエースを特定 (candidates内の選手に限定)
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
                                
                                # candidates（規定打席到達者）に存在する選手のみから投手を決定
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

                        # 🌟 打順は打撃成績に応じて決定（上位から順に評価し、投手が未選出の場合は最後に9番に配置）
                        assign_player(3, "Score_3")  # 3番
                        assign_player(1, "Score_1")  # 1番
                        assign_player(2, "Score_2")  # 2番
                        assign_player(4, "Score_4")  # 4番
                        assign_player(5, "Score_5")  # 5番
                        assign_player(6, "Score_6")  # 6番
                        assign_player(7, "Score_7")  # 7番
                        assign_player(8, "Score_8")  # 8番
                        assign_player(9, "Score_9", force_ace=True)

                        # ==========================================
                        # 残りの守備位置の自動推論と割り当て (必ず9ポジションを使用)
                        # ==========================================
                        FIELD_POSITIONS = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                        available_positions = set(FIELD_POSITIONS)
                        
                        if ace_player:
                            assigned_positions[ace_player] = "投"
                            if "投" in available_positions:
                                available_positions.remove("投")

                        other_used = [p for p in used_players if p != ace_player]
                        
                        p_df = df_calc[df_calc["選手名"].isin(other_used) & df_calc["位置"].isin(FIELD_POSITIONS)] if "位置" in df_calc.columns else pd.DataFrame()
                        
                        if not p_df.empty:
                            pos_counts = p_df.groupby(["選手名", "位置"]).size().reset_index(name="count")
                            pos_counts = pos_counts.sort_values("count", ascending=False)
                        else:
                            pos_counts = pd.DataFrame(columns=["選手名", "位置", "count"])
                        
                        for _, row in pos_counts.iterrows():
                            player = row["選手名"]
                            pos = row["位置"]
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

                        # UI描画（守備位置付き ＆ 通算投手成績併記）
                        for i in range(1, 10):
                            role_name, desc, sort_col = roles_info[i]
                            p = lineup.get(i)
                            if p is not None:
                                player_name = p['選手名']
                                assigned_pos = assigned_positions.get(player_name, "不明")
                                st.markdown(f"##### {i}番 ({assigned_pos}): {role_name}")
                                st.caption(f"選出基準: {desc}")
                                
                                # 🌟 通算の投手データを参照して成績を計算・表記
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