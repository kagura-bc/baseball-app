import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL, OFFICIAL_GAME_TYPES


@st.cache_data(ttl=300, show_spinner=False)
def load_all_teams_data():
    """全登録チームのスプレッドシートからデータを取得・統合（5分間キャッシュ）"""
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_teams = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="相手チーム登録", ttl=0)
    except Exception:
        return pd.DataFrame(), pd.DataFrame(), set()

    if df_teams is None or df_teams.empty:
        return pd.DataFrame(), pd.DataFrame(), set()

    url_col = next((c for c in ["spreadsheet_url", "スプレッドシートURL", "URL"] if c in df_teams.columns), None)
    if not url_col:
        return pd.DataFrame(), pd.DataFrame(), set()

    all_batting_list = []
    all_pitching_list = []
    hidden_players = set()  # (所属チーム, 選手名)

    for _, row in df_teams.iterrows():
        team_name = str(row.get("チーム名", "")).strip()
        sheet_url = row.get(url_col)

        if pd.isna(sheet_url) or not str(sheet_url).startswith("http"):
            continue

        try:
            # 1. 選手登録シートから成績非表示フラグを取得
            try:
                df_reg = conn.read(spreadsheet=sheet_url, worksheet="選手登録", ttl=0)
                if df_reg is not None and not df_reg.empty and "選手名" in df_reg.columns and "成績非表示" in df_reg.columns:
                    for _, p_row in df_reg.iterrows():
                        p_name = str(p_row.get("選手名", "")).strip()
                        p_hide = p_row.get("成績非表示", False)
                        if p_hide in [True, 1, "True", "TRUE", "true"]:
                            hidden_players.add((team_name, p_name))
            except Exception:
                pass

            # 2. 打撃成績の読み込み
            df_b = conn.read(spreadsheet=sheet_url, worksheet="打撃成績", ttl=0)
            if df_b is not None and not df_b.empty:
                df_b["所属チーム"] = team_name
                all_batting_list.append(df_b)

            # 3. 投手成績の読み込み
            df_p = conn.read(spreadsheet=sheet_url, worksheet="投手成績", ttl=0)
            if df_p is not None and not df_p.empty:
                df_p["所属チーム"] = team_name
                all_pitching_list.append(df_p)
        except Exception:
            continue

    df_all_b = pd.concat(all_batting_list, ignore_index=True) if all_batting_list else pd.DataFrame()
    df_all_p = pd.concat(all_pitching_list, ignore_index=True) if all_pitching_list else pd.DataFrame()

    return df_all_b, df_all_p, hidden_players


def render_title_card(title_label, df_data, sort_col, name_col, team_col, val_fmt="{:.3f}", suffix="", ascending=False, top_n=30):
    """タイトル別のミニリーダーボード（カード形式）を出力"""
    with st.container(border=True):
        st.markdown(f"##### {title_label}")
        if df_data.empty:
            st.caption("データなし")
            return

        if ascending:
            target_df = df_data.copy()
        else:
            target_df = df_data[df_data[sort_col] > 0].copy()

        if target_df.empty:
            st.caption("対象者なし")
            return

        top_df = target_df.sort_values(by=sort_col, ascending=ascending).head(top_n).reset_index(drop=True)

        for i, row in top_df.iterrows():
            rank = i + 1
            icon = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"**{rank}.**"
            p_name = row[name_col]
            t_name = row[team_col]
            val = row[sort_col]

            if callable(val_fmt):
                val_str = val_fmt(val)
            elif isinstance(val_fmt, str):
                try:
                    val_str = val_fmt.format(val)
                except ValueError:
                    val_str = val_fmt.format(int(val))
            else:
                val_str = str(val)

            st.markdown(
                f"{icon} **{p_name}** <small style='color:gray;'>({t_name})</small> : **{val_str}**{suffix}",
                unsafe_allow_html=True
            )


def show_league_stats():
    st.markdown("### 🌐 リーグ戦績・他チーム比較")

    df_all_b, df_all_p, hidden_players = load_all_teams_data()

    if df_all_b.empty and df_all_p.empty:
        st.info("集計可能なチームデータが見つかりませんでした。")
        return

    tab_team, tab_bat, tab_pit = st.tabs([
        "🏆 チーム順位・戦績",
        "🏏 打撃タイトル・ランキング",
        "⚾ 投手タイトル・ランキング"
    ])

    # --------------------------------------------------
    # 1. チーム順位・戦績
    # --------------------------------------------------
    with tab_team:
        st.markdown("#### 🏆 チーム総合順位表")

        if not df_all_b.empty and "所属チーム" in df_all_b.columns:
            min_games = st.number_input(
                "規定試合数（下限）",
                min_value=1,
                value=3,
                step=1,
                help="この試合数未満のチームは参考記録扱いになります"
            )
            team_summary = []

            if "日付" in df_all_b.columns:
                df_all_b["DateStr"] = pd.to_datetime(df_all_b["日付"], errors="coerce").dt.strftime("%Y-%m-%d")
            if not df_all_p.empty and "日付" in df_all_p.columns:
                df_all_p["DateStr"] = pd.to_datetime(df_all_p["日付"], errors="coerce").dt.strftime("%Y-%m-%d")

            all_teams = set(df_all_b["所属チーム"].unique()) if "所属チーム" in df_all_b.columns else set()
            if not df_all_p.empty and "所属チーム" in df_all_p.columns:
                all_teams.update(df_all_p["所属チーム"].unique())

            for team_name in all_teams:
                b_team = df_all_b[df_all_b["所属チーム"] == team_name] if not df_all_b.empty else pd.DataFrame()
                p_team = df_all_p[df_all_p["所属チーム"] == team_name] if not df_all_p.empty else pd.DataFrame()

                games_map = {}

                if not b_team.empty and {"DateStr", "対戦相手", "試合種別"}.issubset(b_team.columns):
                    for (d_str, opp, m_type), group in b_team.groupby(["DateStr", "対戦相手", "試合種別"]):
                        if not d_str or pd.isna(d_str):
                            continue

                        match_date = pd.to_datetime(d_str, errors='coerce')
                        match_year = match_date.year if pd.notna(match_date) else 2026

                        valid_batting = group[group["イニング"] != "まとめ入力"] if "イニング" in group.columns else group
                        valid_inn_mask_b = ~valid_batting["イニング"].astype(str).str.strip().isin(["", "nan", "None", "ー", "まとめ入力"]) if "イニング" in valid_batting.columns else pd.Series(True, index=valid_batting.index)

                        if match_year in [2024, 2025]:
                            runs = int((valid_batting[valid_inn_mask_b]["結果"] == "得点").sum()) if "結果" in valid_batting.columns else 0
                        else:
                            runs = int(valid_batting["結果"].isin(["得点", "本塁打"]).sum()) if "結果" in valid_batting.columns else 0

                        key = (d_str, opp, m_type)
                        if key not in games_map:
                            games_map[key] = {"得点": 0, "失点": 0}
                        games_map[key]["得点"] = runs

                if not p_team.empty and {"DateStr", "対戦相手", "試合種別"}.issubset(p_team.columns):
                    for (d_str, opp, m_type), group in p_team.groupby(["DateStr", "対戦相手", "試合種別"]):
                        if not d_str or pd.isna(d_str):
                            continue

                        match_date = pd.to_datetime(d_str, errors='coerce')
                        match_year = match_date.year if pd.notna(match_date) else 2026

                        valid_pitching = group[group["イニング"] != "まとめ入力"] if "イニング" in group.columns else group
                        valid_inn_mask_p = ~valid_pitching["イニング"].astype(str).str.strip().isin(["", "nan", "None", "ー", "まとめ入力"]) if "イニング" in valid_pitching.columns else pd.Series(True, index=valid_pitching.index)

                        if match_year in [2024, 2025]:
                            runs_allowed = int((valid_pitching[valid_inn_mask_p]["結果"] == "得点").sum()) if "結果" in valid_pitching.columns else 0
                        else:
                            runs_allowed = int(valid_pitching["結果"].isin(["得点", "本塁打"]).sum()) if "結果" in valid_pitching.columns else 0

                        key = (d_str, opp, m_type)
                        if key not in games_map:
                            games_map[key] = {"得点": 0, "失点": 0}
                        games_map[key]["失点"] = runs_allowed

                if not games_map:
                    continue

                total_games, wins, losses, draws = 0, 0, 0, 0
                total_runs_scored, total_runs_conceded = 0, 0

                for key, g_info in games_map.items():
                    s = g_info["得点"]
                    l = g_info["失点"]

                    total_games += 1
                    total_runs_scored += s
                    total_runs_conceded += l

                    if s > l:
                        wins += 1
                    elif s < l:
                        losses += 1
                    else:
                        draws += 1

                win_rate = (wins / total_games) if total_games > 0 else 0.0
                run_diff = total_runs_scored - total_runs_conceded

                team_summary.append({
                    "チーム名": team_name,
                    "試合数": total_games,
                    "勝": wins,
                    "敗": losses,
                    "分": draws,
                    "勝率": win_rate,
                    "総得点": total_runs_scored,
                    "総失点": total_runs_conceded,
                    "得失点差": run_diff,
                })

            if team_summary:
                df_rank = pd.DataFrame(team_summary)
                df_ranked = df_rank[df_rank["試合数"] >= min_games].sort_values(
                    by=["勝率", "勝", "得失点差", "総得点"],
                    ascending=[False, False, False, False]
                ).reset_index(drop=True)

                df_ranked.insert(0, "順位", range(1, len(df_ranked) + 1))

                st.dataframe(
                    df_ranked.style.format({
                        "勝率": "{:.3f}",
                        "得失点差": "{:+d}"
                    }).background_gradient(subset=["勝率"], cmap="Reds"),
                    use_container_width=True,
                    hide_index=True
                )

                df_under = df_rank[df_rank["試合数"] < min_games]
                if not df_under.empty:
                    with st.expander(f"⚠️ 規定試合数（{min_games}試合）未満のチーム（参考記録）"):
                        st.dataframe(
                            df_under.style.format({"勝率": "{:.3f}"}),
                            use_container_width=True,
                            hide_index=True
                        )
            else:
                st.caption("集計可能な試合データがありません。")
        else:
            st.caption("チームデータがありません。")

    # --------------------------------------------------
    # 2. 打撃タイトル・ランキング
    # --------------------------------------------------
    with tab_bat:
        st.markdown("#### 🏏 リーグ打撃タイトル・部門別リーダー")
        if not df_all_b.empty:
            b_p_col = "打者名" if "打者名" in df_all_b.columns else "選手名"
            df_b_calc = df_all_b[~df_all_b[b_p_col].astype(str).str.contains("チーム記録", na=False)].copy()
            df_b_calc["選手名"] = df_b_calc[b_p_col]

            if "日付" in df_b_calc.columns:
                df_b_calc["DateStr"] = pd.to_datetime(df_b_calc["日付"], errors="coerce").dt.strftime("%Y-%m-%d")

            df_b_calc["結果"] = df_b_calc["結果"].astype(str).str.replace(r"\s+", "", regex=True)
            df_b_calc["is_hit"] = df_b_calc["結果"].str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)

            non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
            is_valid = ~df_b_calc["結果"].isin(["", "nan", "None", "-"])
            is_not_excluded = ~df_b_calc["結果"].str.contains(non_ab_pattern, na=False)
            df_b_calc["is_ab"] = (is_valid & is_not_excluded).astype(int)

            df_b_calc["is_hr"] = df_b_calc["結果"].str.contains("本塁打", na=False).astype(int)
            df_b_calc["is_1b"] = df_b_calc["結果"].str.contains("単打", na=False).astype(int)
            df_b_calc["is_2b"] = df_b_calc["結果"].str.contains("二塁打", na=False).astype(int)
            df_b_calc["is_3b"] = df_b_calc["結果"].str.contains("三塁打", na=False).astype(int)
            df_b_calc["is_bb"] = df_b_calc["結果"].str.contains("四球|死球|四死球", na=False).astype(int)
            df_b_calc["is_sf"] = df_b_calc["結果"].str.contains("犠飛", na=False).astype(int)
            df_b_calc["is_sh"] = df_b_calc["結果"].str.contains("犠打", na=False).astype(int)

            df_b_calc["bases"] = (
                df_b_calc["is_1b"] * 1 +
                df_b_calc["is_2b"] * 2 +
                df_b_calc["is_3b"] * 3 +
                df_b_calc["is_hr"] * 4
            )

            for c in ["打点", "盗塁"]:
                if c not in df_b_calc.columns:
                    df_b_calc[c] = 0
                df_b_calc[c] = pd.to_numeric(df_b_calc[c], errors='coerce').fillna(0)

            res_str = df_b_calc["結果"].astype(str)
            steal_mask = (res_str == "盗塁") | (res_str.str.contains("盗塁") & ~res_str.str.contains("盗塁死"))
            df_b_calc["盗塁"] = df_b_calc["盗塁"] + steal_mask.astype(int)

            df_b_calc["MatchKey"] = df_b_calc["DateStr"] + "_" + df_b_calc["対戦相手"].astype(str)

            bat_rank = df_b_calc.groupby(["所属チーム", "選手名"]).agg(
                試合数=("MatchKey", lambda s: len(s.unique())),
                打数=("is_ab", "sum"),
                安打=("is_hit", "sum"),
                本塁打=("is_hr", "sum"),
                打点=("打点", "sum"),
                盗塁=("盗塁", "sum"),
                四死球=("is_bb", "sum"),
                犠飛=("is_sf", "sum"),
                犠打=("is_sh", "sum"),
                bases=("bases", "sum")
            ).reset_index()

            # 成績非表示選手の除外
            if hidden_players and not bat_rank.empty:
                bat_rank = bat_rank[~bat_rank.apply(lambda r: (r["所属チーム"], r["選手名"]) in hidden_players, axis=1)]

            bat_rank["打席数"] = bat_rank["打数"] + bat_rank["四死球"] + bat_rank["犠飛"] + bat_rank["犠打"]
            bat_rank["打率"] = bat_rank.apply(lambda r: r["安打"] / r["打数"] if r["打数"] > 0 else 0.0, axis=1)
            bat_rank["出塁率"] = bat_rank.apply(lambda r: (r["安打"] + r["四死球"]) / r["打席数"] if r["打席数"] > 0 else 0.0, axis=1)
            bat_rank["長打率"] = bat_rank.apply(lambda r: r["bases"] / r["打数"] if r["打数"] > 0 else 0.0, axis=1)
            bat_rank["OPS"] = bat_rank["出塁率"] + bat_rank["長打率"]

            min_ab = st.number_input("規定打数下限", min_value=0, value=5, step=1, key="bat_min_ab_input")

            # 規定打数フィルタ適用
            df_bat_reg = bat_rank[bat_rank["打数"] >= min_ab].copy()

            # --- タイトル別 Top30 カード表示 (4列×2段) ---
            st.write("")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                render_title_card("👑 打率", df_bat_reg, "打率", "選手名", "所属チーム", val_fmt="{:.3f}", top_n=30)
            with c2:
                render_title_card("👑 安打", bat_rank, "安打", "選手名", "所属チーム", val_fmt="{:d}", suffix=" 本", top_n=30)
            with c3:
                render_title_card("👑 本塁打", bat_rank, "本塁打", "選手名", "所属チーム", val_fmt="{:d}", suffix=" 本", top_n=30)
            with c4:
                render_title_card("👑 打点", bat_rank, "打点", "選手名", "所属チーム", val_fmt="{:d}", suffix=" 点", top_n=30)

            st.write("")
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                render_title_card("👑 盗塁", bat_rank, "盗塁", "選手名", "所属チーム", val_fmt="{:d}", suffix=" 個", top_n=30)
            with c6:
                render_title_card("👑 OPS", df_bat_reg, "OPS", "選手名", "所属チーム", val_fmt="{:.3f}", top_n=30)
            with c7:
                render_title_card("👑 出塁率", df_bat_reg, "出塁率", "選手名", "所属チーム", val_fmt="{:.3f}", top_n=30)
            with c8:
                render_title_card("👑 長打率", df_bat_reg, "長打率", "選手名", "所属チーム", val_fmt="{:.3f}", top_n=30)

            # --- 全データ一覧テーブル (Expander) ---
            st.write("")
            with st.expander("📊 全項目一覧テーブル (Top 30)"):
                target_col = st.selectbox("並び替え項目", ["打率", "OPS", "安打", "本塁打", "打点", "盗塁", "出塁率", "長打率", "打数", "打席数", "試合数"], key="bat_table_sort")
                filtered_bat = df_bat_reg.sort_values(by=target_col, ascending=False).head(30).reset_index(drop=True)
                filtered_bat.insert(0, "順位", range(1, len(filtered_bat) + 1))

                st.dataframe(
                    filtered_bat[["順位", "所属チーム", "選手名", "打率", "OPS", "安打", "本塁打", "打点", "盗塁", "出塁率", "長打率", "打数", "打席数", "試合数"]].style.format({
                        "打率": "{:.3f}",
                        "OPS": "{:.3f}",
                        "出塁率": "{:.3f}",
                        "長打率": "{:.3f}"
                    }).background_gradient(subset=[target_col], cmap="Reds"),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.caption("打撃データがありません。")

    # --------------------------------------------------
    # 3. 投手タイトル・ランキング
    # --------------------------------------------------
    with tab_pit:
        st.markdown("#### ⚾ リーグ投手タイトル・部門別リーダー")
        if not df_all_p.empty:
            p_p_col = "投手名" if "投手名" in df_all_p.columns else "選手名"
            df_p_calc = df_all_p[~df_all_p[p_p_col].astype(str).str.contains("チーム記録", na=False)].copy()
            df_p_calc["投手名"] = df_p_calc[p_p_col]

            if "日付" in df_p_calc.columns:
                df_p_calc["DateStr"] = pd.to_datetime(df_p_calc["日付"], errors="coerce").dt.strftime("%Y-%m-%d")
                df_p_calc["Year"] = pd.to_datetime(df_p_calc["日付"], errors="coerce").dt.strftime("%Y").fillna("不明")

            # アウト数算出
            if "アウト数" not in df_p_calc.columns or df_p_calc["アウト数"].sum() == 0:
                res_str = df_p_calc["結果"].astype(str) if "結果" in df_p_calc.columns else pd.Series([""] * len(df_p_calc))
                outs = pd.Series(0, index=df_p_calc.index)
                dp_mask = res_str.str.contains("併殺", na=False)
                outs[dp_mask] = 2
                normal_out_mask = (
                    res_str.str.contains("凡退|三振|犠打|犠飛|走塁死|盗塁死", na=False) &
                    ~res_str.str.contains("失策|得点|進塁|盗塁|安打|単打|二塁打|三塁打|本塁打|四球|死球|暴投|捕逸|ボーク", na=False)
                )
                outs[normal_out_mask] = 1
                df_p_calc["アウト数"] = outs
            else:
                df_p_calc["アウト数"] = pd.to_numeric(df_p_calc["アウト数"], errors='coerce').fillna(0)

            # 失点算出
            valid_p_inn = ~df_p_calc["イニング"].astype(str).str.strip().isin(["", "nan", "None", "ー", "まとめ入力"]) if "イニング" in df_p_calc.columns else pd.Series(True, index=df_p_calc.index)
            is_p_2024_2025 = df_p_calc["Year"].astype(str).isin(["2024", "2025"])

            df_p_calc["失点"] = 0
            df_p_calc.loc[is_p_2024_2025 & valid_p_inn & (df_p_calc["結果"] == "得点"), "失点"] = 1
            df_p_calc.loc[(~is_p_2024_2025) & df_p_calc["結果"].isin(["得点", "本塁打"]), "失点"] = 1

            # 勝利判定
            df_p_calc["is_win"] = 0
            if "勝敗" in df_p_calc.columns:
                for (player, *match_info), group in df_p_calc.groupby(["投手名", "DateStr", "対戦相手"]):
                    r_str = "".join(group["勝敗"].dropna().astype(str).tolist())
                    if "勝" in r_str or "○" in r_str:
                        df_p_calc.loc[group.index[0], "is_win"] = 1

            for c in ["自責点", "被安打", "与四球", "奪三振"]:
                if c not in df_p_calc.columns:
                    df_p_calc[c] = 0
                df_p_calc[c] = pd.to_numeric(df_p_calc[c], errors='coerce').fillna(0)

            temp_so = df_p_calc["結果"].isin(["三振", "振り逃げ三振"]).astype(int)
            df_p_calc["奪三振"] = df_p_calc[["奪三振"]].assign(flag=temp_so).max(axis=1)

            temp_bb = df_p_calc["結果"].isin(["四球", "死球"]).astype(int)
            df_p_calc["与四死球"] = df_p_calc[["与四球"]].assign(flag=temp_bb).max(axis=1)

            df_p_calc["MatchKey"] = df_p_calc["DateStr"] + "_" + df_p_calc["対戦相手"].astype(str)

            pit_rank = df_p_calc.groupby(["所属チーム", "投手名"]).agg(
                登板数=("MatchKey", lambda s: len(s.unique())),
                アウト数=("アウト数", "sum"),
                勝利=("is_win", "sum"),
                奪三振=("奪三振", "sum"),
                与四死球=("与四死球", "sum"),
                失点=("失点", "sum"),
                自責点=("自責点", "sum"),
                被安打=("被安打", "sum")
            ).reset_index()

            # 成績非表示選手の除外
            if hidden_players and not pit_rank.empty:
                pit_rank = pit_rank[~pit_rank.apply(lambda r: (r["所属チーム"], r["投手名"]) in hidden_players, axis=1)]

            pit_rank["投球回_val"] = pit_rank["アウト数"] / 3
            pit_rank["投球回"] = pit_rank["アウト数"].apply(lambda x: f"{int(x // 3)}.{int(x % 3)}")
            pit_rank["防御率"] = pit_rank.apply(lambda r: (r["自責点"] * 7) / r["投球回_val"] if r["投球回_val"] > 0 else 99.99, axis=1)
            pit_rank["WHIP"] = pit_rank.apply(lambda r: (r["与四死球"] + r["被安打"]) / r["投球回_val"] if r["投球回_val"] > 0 else 99.99, axis=1)

            min_inn = st.number_input("規定投球回下限（イニング）", min_value=0.0, value=1.0, step=1.0, key="pit_min_inn_input")

            # 規定投球回フィルタ適用
            df_pit_reg = pit_rank[pit_rank["投球回_val"] >= min_inn].copy()

            # --- タイトル別 Top30 カード表示 (3列×2段) ---
            st.write("")
            p1, p2, p3 = st.columns(3)
            with p1:
                render_title_card("👑 防御率", df_pit_reg, "防御率", "投手名", "所属チーム", val_fmt="{:.2f}", ascending=True, top_n=30)
            with p2:
                render_title_card("👑 勝利", pit_rank, "勝利", "投手名", "所属チーム", val_fmt="{:d}", suffix=" 勝", top_n=30)
            with p3:
                render_title_card("👑 奪三振", pit_rank, "奪三振", "投手名", "所属チーム", val_fmt="{:d}", suffix=" 個", top_n=30)

            st.write("")
            p4, p5, p6 = st.columns(3)
            with p4:
                render_title_card("👑 WHIP", df_pit_reg, "WHIP", "投手名", "所属チーム", val_fmt="{:.2f}", ascending=True, top_n=30)
            with p5:
                render_title_card("👑 投球回", pit_rank, "投球回_val", "投手名", "所属チーム", val_fmt=lambda v: f"{int(v*3//3)}.{int(v*3%3)}", suffix=" 回", top_n=30)
            with p6:
                render_title_card("👑 登板数", pit_rank, "登板数", "投手名", "所属チーム", val_fmt="{:d}", suffix=" 試合", top_n=30)

            # --- 全データ一覧テーブル (Expander) ---
            st.write("")
            with st.expander("📊 全項目一覧テーブル (Top 30)"):
                target_p_col = st.selectbox("並び替え項目", ["奪三振", "登板数", "防御率", "勝利", "投球回", "失点", "自責点", "WHIP"], key="pit_table_sort")
                ascending_flag = True if target_p_col in ["防御率", "失点", "自責点", "WHIP"] else False
                filtered_pit = df_pit_reg.sort_values(by=target_p_col if target_p_col != "投球回" else "投球回_val", ascending=ascending_flag).head(30).reset_index(drop=True)
                filtered_pit.insert(0, "順位", range(1, len(filtered_pit) + 1))

                st.dataframe(
                    filtered_pit[["順位", "所属チーム", "投手名", "登板数", "防御率", "勝利", "投球回", "奪三振", "失点", "自責点", "WHIP"]].style.format({
                        "防御率": "{:.2f}",
                        "WHIP": "{:.2f}"
                    }).background_gradient(subset=[target_p_col], cmap="Blues"),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.caption("投手データがありません。")