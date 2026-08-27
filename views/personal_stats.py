import datetime
import unicodedata
import pandas as pd
import streamlit as st

from config.settings import OFFICIAL_GAME_TYPES
from utils.players import get_stats_active_players
from utils.ui import fmt_player_name


def show_personal_stats(df_batting, df_pitching):
    st.title(" 📊 個人成績")

    # ▼▼▼ スプレッドシートから成績表示用の選手リストを取得 ▼▼▼
    STATS_PLAYERS, STATS_NUMBERS = get_stats_active_players()

    def local_fmt(name):
        return fmt_player_name(name, STATS_NUMBERS)

    # チーム記録は残しつつ、非表示対象の選手を除外する
    allowed_names = STATS_PLAYERS + ["チーム記録"]

    # 必須カラムの安全補完（打者名・投手名・選手名の互換吸収）
    if not df_batting.empty:
        b_p_col = "打者名" if "打者名" in df_batting.columns else "選手名"
        df_batting["選手名_表示"] = df_batting[b_p_col]
        df_batting = df_batting[df_batting["選手名_表示"].isin(allowed_names)].copy()

    if not df_pitching.empty:
        p_p_col = "投手名" if "投手名" in df_pitching.columns else "選手名"
        df_pitching["選手名_表示"] = df_pitching[p_p_col]
        df_pitching = df_pitching[df_pitching["選手名_表示"].isin(allowed_names)].copy()

    # =========================================================
    # 1. データ前処理
    # =========================================================

    # --- 打撃データ ---
    if not df_batting.empty:
        df_batting["Year"] = pd.to_datetime(df_batting["日付"], errors='coerce').dt.strftime('%Y')
        df_batting["Year"] = df_batting["Year"].fillna("不明")

        df_b_calc = df_batting[df_batting["選手名_表示"] != "チーム記録"].copy()
        df_b_calc["選手名"] = df_b_calc["選手名_表示"]
        df_b_calc["結果"] = df_b_calc["結果"].astype(str).str.replace(r"\s+", "", regex=True)

        df_b_calc["is_hit"] = df_b_calc["結果"].str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)

        non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
        is_valid = ~df_b_calc["結果"].isin(["", "nan", "None", "-"])
        is_not_excluded = ~df_b_calc["結果"].str.contains(non_ab_pattern, na=False)
        df_b_calc["is_ab"] = (is_valid & is_not_excluded).astype(int)

        df_b_calc["is_hr"] = df_b_calc["結果"].str.contains("本塁打", na=False).astype(int)
        df_b_calc["is_so"] = df_b_calc["結果"].str.contains("三振", na=False).astype(int)

        df_b_calc["is_1b"] = df_b_calc["結果"].str.contains("単打", na=False).astype(int)
        df_b_calc["is_2b"] = df_b_calc["結果"].str.contains("二塁打", na=False).astype(int)
        df_b_calc["is_3b"] = df_b_calc["結果"].str.contains("三塁打", na=False).astype(int)

        df_b_calc["is_bb"] = df_b_calc["結果"].str.contains("四球|死球|四死球", na=False).astype(int)
        df_b_calc["is_sf"] = df_b_calc["結果"].str.contains("犠飛", na=False).astype(int)

        df_b_calc["bases"] = (
            df_b_calc["is_1b"] * 1 +
            df_b_calc["is_2b"] * 2 +
            df_b_calc["is_3b"] * 3 +
            df_b_calc["is_hr"] * 4
        )

        for c in ["打点", "盗塁", "得点", "盗塁死"]:
            if c not in df_b_calc.columns:
                df_b_calc[c] = 0
            df_b_calc[c] = pd.to_numeric(df_b_calc[c], errors='coerce').fillna(0)
    else:
        df_b_calc = pd.DataFrame(columns=["Year", "選手名", "結果", "is_hit", "is_ab", "is_hr", "is_so", "is_1b", "is_2b", "is_3b", "is_bb", "bases", "打点", "盗塁", "盗塁死", "得点"])

    # --- 投手データ ---
    if not df_pitching.empty:
        df_pitching["Year"] = pd.to_datetime(df_pitching["日付"], errors='coerce').dt.strftime('%Y')
        df_pitching["Year"] = df_pitching["Year"].fillna("不明")

        df_p_calc = df_pitching[df_pitching["選手名_表示"] != "チーム記録"].copy()
        df_p_calc["選手名"] = df_p_calc["選手名_表示"]

        df_p_calc["is_win"] = 0
        df_p_calc["is_lose"] = 0

        if "勝敗" in df_p_calc.columns:
            match_keys = ["日付", "対戦相手"] if "対戦相手" in df_p_calc.columns else ["日付"]
            for (player, *match_info), group in df_p_calc.groupby(["選手名"] + match_keys):
                r_str = "".join(group["勝敗"].dropna().astype(str).tolist())
                if "勝" in r_str or "○" in r_str:
                    df_p_calc.loc[group.index[0], "is_win"] = 1
                elif "負" in r_str or "敗" in r_str or "●" in r_str:
                    df_p_calc.loc[group.index[0], "is_lose"] = 1
        for c in ["自責点", "失点", "アウト数", "被安打", "与四球", "奪三振"]:
            if c not in df_p_calc.columns:
                df_p_calc[c] = 0
            df_p_calc[c] = pd.to_numeric(df_p_calc[c], errors='coerce').fillna(0)

        if "処理野手" not in df_p_calc.columns:
            df_p_calc["処理野手"] = ""

        temp_so = df_p_calc["結果"].isin(["三振", "振り逃げ三振"]).astype(int)
        df_p_calc["奪三振"] = df_p_calc[["奪三振"]].assign(flag=temp_so).max(axis=1)
        df_p_calc["is_so"] = 0

        temp_bb = df_p_calc["結果"].isin(["四球", "死球"]).astype(int)
        df_p_calc["total_bb"] = df_p_calc[["与四球"]].assign(flag=temp_bb).max(axis=1)

        temp_hit = df_p_calc["結果"].isin(["安打", "単打", "二塁打", "三塁打", "本塁打"]).astype(int)
        df_p_calc["被安打"] = df_p_calc[["被安打"]].assign(flag=temp_hit).max(axis=1)
    else:
        df_p_calc = pd.DataFrame()

    def get_ranking_df(df, group_keys, agg_dict):
        if df.empty:
            cols = group_keys + list(agg_dict.keys())
            return pd.DataFrame(columns=cols)

        for col in agg_dict.keys():
            if col not in df.columns:
                df[col] = 0

        return df.groupby(group_keys).agg(agg_dict).reset_index()

    def show_top10(title, df, sort_col, label_col, value_col, ascending=False, suffix="", format_float=False):
        st.markdown(f"**{title}**")
        if ascending:
            target = df.copy()
        else:
            target = df[df[value_col] > 0].copy()

        top10 = target.sort_values(sort_col, ascending=ascending).head(10).reset_index(drop=True)

        if top10.empty:
            st.caption("データなし")
        else:
            for i, row in top10.iterrows():
                rank = i + 1
                icon = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
                val = row[value_col]
                if format_float:
                    val_str = f"{val:.3f}" if title in ["打率", "OPS"] else f"{val:.2f}"
                else:
                    val_str = f"{int(val)}"
                st.write(f"{icon} **{row[label_col]}** : {val_str}{suffix}")

    agg_rules_b = {
        "is_hit": "sum", "is_ab": "sum", "is_hr": "sum", "is_so": "sum",
        "is_1b": "sum", "is_2b": "sum", "is_3b": "sum", "is_bb": "sum",
        "is_sf": "sum",
        "打点": "sum", "盗塁": "sum", "盗塁死": "sum", "得点": "sum", "bases": "sum"
    }
    agg_rules_p = {
        "アウト数": "sum", "自責点": "sum", "失点": "sum",
        "is_win": "sum", "is_lose": "sum", "被安打": "sum",
        "total_bb": "sum", "is_so": "sum", "奪三振": "sum"
    }

    # 全3つのメインタブ構造
    t_total, t_year, t_rank_rec = st.tabs(["総合成績・ポイント", "個人年度別", "ランキング・歴代記録"])

    # ----------------------------------------------------
    # 1. 総合成績・ポイント
    # ----------------------------------------------------
    with t_total:
        st.markdown("#### 📊 総合成績・ポイントリスト")

        years_bat = set(df_batting["Year"].dropna().astype(str).unique()) if (df_batting is not None and not df_batting.empty and "Year" in df_batting.columns) else set()
        years_pit = set(df_pitching["Year"].dropna().astype(str).unique()) if (df_pitching is not None and not df_pitching.empty and "Year" in df_pitching.columns) else set()
        years = sorted(list(years_bat | years_pit), reverse=True)

        c1, c2 = st.columns(2)
        target_year = c1.selectbox("集計年度", ["直近2年分", "通算"] + years, key="total_merged_year")
        target_type = c2.selectbox("試合種別", ["全種別", "公式戦 (トータル)", "練習試合"], key="total_merged_type")

        # 絞り込みロジック
        df_b_tg = df_b_calc.copy()
        df_p_tg = df_p_calc.copy()

        if target_year == "直近2年分":
            recent_2years = years[:2]
            df_b_tg = df_b_tg[df_b_tg["Year"].isin(recent_2years)] if not df_b_tg.empty and "Year" in df_b_tg.columns else df_b_tg
            df_p_tg = df_p_tg[df_p_tg["Year"].isin(recent_2years)] if not df_p_tg.empty and "Year" in df_p_tg.columns else df_p_tg
        elif target_year != "通算":
            df_b_tg = df_b_tg[df_b_tg["Year"] == target_year] if not df_b_tg.empty and "Year" in df_b_tg.columns else df_b_tg
            df_p_tg = df_p_tg[df_p_tg["Year"] == target_year] if not df_p_tg.empty and "Year" in df_p_tg.columns else df_p_tg

        if target_type == "公式戦 (トータル)":
            df_b_tg = df_b_tg[df_b_tg["試合種別"].isin(OFFICIAL_GAME_TYPES)] if not df_b_tg.empty and "試合種別" in df_b_tg.columns else df_b_tg
            df_p_tg = df_p_tg[df_p_tg["試合種別"].isin(OFFICIAL_GAME_TYPES)] if not df_p_tg.empty and "試合種別" in df_p_tg.columns else df_p_tg
        elif target_type == "練習試合":
            df_b_tg = df_b_tg[df_b_tg["試合種別"] == "練習試合"] if not df_b_tg.empty and "試合種別" in df_b_tg.columns else df_b_tg
            df_p_tg = df_p_tg[df_p_tg["試合種別"] == "練習試合"] if not df_p_tg.empty and "試合種別" in df_p_tg.columns else df_p_tg

        # --- 共通計算: セイバー＆貢献度ポイント ---
        saber_b = pd.DataFrame()
        if not df_b_tg.empty:
            saber_b = df_b_tg.groupby("選手名").agg(agg_rules_b).reset_index()
            saber_b["PA"] = saber_b["is_ab"] + saber_b["is_bb"] + saber_b["is_sf"]
            saber_b["打率"] = saber_b.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
            saber_b["出塁率"] = saber_b.apply(lambda x: (x["is_hit"] + x["is_bb"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
            saber_b["TotalBases"] = saber_b["is_1b"] + (saber_b["is_2b"] * 2) + (saber_b["is_3b"] * 3) + (saber_b["is_hr"] * 4)
            saber_b["長打率"] = (saber_b["TotalBases"] / saber_b["is_ab"]).fillna(0)
            saber_b["OPS"] = saber_b["出塁率"] + saber_b["長打率"]
            saber_b["RC"] = saber_b.apply(
                lambda x: ((x["is_hit"] + x["is_bb"]) * x["TotalBases"]) / (x["is_ab"] + x["is_bb"])
                if (x["is_ab"] + x["is_bb"]) > 0 else 0, axis=1
            )
            saber_b["Batting_Score"] = saber_b["OPS"] * 50.0 + saber_b["RC"] * 3.0 + saber_b["盗塁"] * 1.0

        saber_p = pd.DataFrame()
        if not df_p_tg.empty:
            saber_p = df_p_tg.groupby("選手名").agg(agg_rules_p).reset_index()
            saber_p["投球回"] = saber_p["アウト数"] / 3
            saber_p["防御率"] = saber_p.apply(lambda x: (x["自責点"] * 7) / x["投球回"] if x["投球回"] > 0 else 99.0, axis=1)
            saber_p["TotalSO"] = saber_p["is_so"] + saber_p["奪三振"]

            def p_score(r):
                p_inn, p_era, p_so = r["投球回"], r["防御率"], r["TotalSO"]
                if p_inn <= 0 or p_era >= 90:
                    return 0.0
                era_pts = (3.50 - p_era) * p_inn * 0.3
                return max(0.0, p_inn * 1.0 + p_so * 0.3 + era_pts)

            saber_p["Pitching_Score"] = saber_p.apply(p_score, axis=1)

        saber_f = pd.DataFrame()
        if not df_p_tg.empty and "処理野手" in df_p_tg.columns and "守備位置" in df_p_tg.columns:
            fld_base = df_p_tg.copy().reset_index(drop=True)
            fld_base["Original_Idx"] = fld_base.index
            fld_data = fld_base[fld_base["処理野手"].notna() & (fld_base["処理野手"] != "")].copy()
            if not fld_data.empty:
                fld_data["処理野手"] = fld_data["処理野手"].astype(str)
                fld_data["守備位置"] = fld_data["守備位置"].astype(str)
                fld_data["zipped"] = fld_data.apply(
                    lambda x: list(dict.fromkeys(zip(str(x["処理野手"]).split("-"), str(x["守備位置"]).split("-")))), axis=1
                )
                fld_expanded = fld_data.explode("zipped").reset_index(drop=True)
                if not fld_expanded.empty:
                    fld_expanded[["FielderName", "FielderPos"]] = pd.DataFrame(fld_expanded["zipped"].tolist(), index=fld_expanded.index)
                    fld_expanded = fld_expanded[fld_expanded["FielderName"].isin(STATS_PLAYERS)]

                    fld_expanded = fld_expanded[~fld_expanded["結果"].astype(str).str.contains("本塁打", na=False)]
                    fld_expanded["is_error"] = fld_expanded["結果"].astype(str).str.contains("失策|暴投|捕逸", na=False)

                    fld_unique = fld_expanded.groupby(["Original_Idx", "FielderName", "FielderPos"]).agg(is_error=("is_error", "max")).reset_index()
                    saber_f = fld_unique.groupby("FielderName").agg(
                        守備機会=("FielderName", "count"),
                        失策数=("is_error", "sum"),
                        捕手守備機会=("FielderPos", lambda x: (x == "捕").sum())
                    ).reset_index().rename(columns={"FielderName": "選手名"})

                    saber_f["守備率"] = saber_f.apply(lambda x: (x["守備機会"] - x["失策数"]) / x["守備機会"] if x["守備機会"] > 0 else 1.0, axis=1)
                    saber_f["Defense_Score"] = saber_f.apply(
                        lambda r: max(0.0, ((r["守備機会"] - r["捕手守備機会"]) * 1.0 + r["捕手守備機会"] * 2.5) * r["守備率"] - r["失策数"] * 2.0), axis=1
                    )

        saber_g = pd.DataFrame()
        df_all_logs = pd.concat([df_b_tg, df_p_tg], ignore_index=True) if not df_b_tg.empty or not df_p_tg.empty else pd.DataFrame()
        if not df_all_logs.empty:
            for col in ["日付", "試合種別", "選手名"]:
                if col in df_all_logs.columns:
                    df_all_logs[col] = df_all_logs[col].fillna("").astype(str).str.strip()
            df_all_logs["対戦相手"] = df_all_logs["対戦相手"].fillna("").astype(str).str.strip() if "対戦相手" in df_all_logs.columns else ""
            df_all_logs["Game_ID"] = df_all_logs["日付"] + "_" + df_all_logs["対戦相手"] + "_" + df_all_logs["試合種別"]
            saber_g = df_all_logs.groupby("選手名")["Game_ID"].nunique().reset_index(name="試合参加数")
            saber_g["Game_Score"] = saber_g["試合参加数"] * 1.0

        all_plist = [df[["選手名"]] for df in [saber_b, saber_p, saber_f, saber_g] if df is not None and not df.empty]
        if all_plist:
            m_saber = pd.concat(all_plist).drop_duplicates().reset_index(drop=True)
            if not saber_b.empty:
                m_saber = m_saber.merge(saber_b, on="選手名", how="left")
            if not saber_p.empty:
                m_saber = m_saber.merge(saber_p, on="選手名", how="left")
            if not saber_f.empty:
                m_saber = m_saber.merge(saber_f, on="選手名", how="left")
            if not saber_g.empty:
                m_saber = m_saber.merge(saber_g, on="選手名", how="left")

            fill_cols = [
                "is_ab", "is_hit", "is_hr", "is_bb", "打点", "盗塁", "盗塁死", "RC", "OPS", "打率",
                "投球回", "is_win", "TotalSO", "守備機会", "失策数", "捕手守備機会", "試合参加数",
                "Batting_Score", "Pitching_Score", "Defense_Score", "Game_Score"
            ]
            for c in fill_cols:
                if c not in m_saber.columns:
                    m_saber[c] = 0.0
                else:
                    m_saber[c] = m_saber[c].fillna(0.0)

            if "守備率" in m_saber.columns:
                m_saber["守備率"] = m_saber["守備率"].fillna(1.0)
            else:
                m_saber["守備率"] = 1.0

            if "防御率" in m_saber.columns:
                m_saber["防御率"] = m_saber["防御率"].fillna(99.0)
            else:
                m_saber["防御率"] = 99.0

            has_def_data = m_saber["守備機会"].sum() > 0 if "守備機会" in m_saber.columns else False
            m_saber["MVP_Score"] = (
                m_saber["Batting_Score"] +
                m_saber["Pitching_Score"] +
                (m_saber["Defense_Score"] if has_def_data else 0.0) +
                m_saber["Game_Score"]
            )
        else:
            m_saber = pd.DataFrame()

        st_mvp, st_bat, st_pit, st_fld, st_game = st.tabs(["🏆 総合ポイント (MVP)", "⚔️ 打撃", "🛡️ 投手", "🧤 守備", "🏟️ 試合"])

        with st_mvp:
            if not m_saber.empty:
                max_g = int(m_saber["試合参加数"].max()) if "試合参加数" in m_saber.columns else 1
                min_g = st.slider("表示対象とする最低試合参加数", 0, max_g, min(2, max_g), key=f"min_g_{target_year}_{target_type}")

                filtered_mvp = m_saber[m_saber["試合参加数"] >= min_g].sort_values("MVP_Score", ascending=False).reset_index(drop=True)
                filtered_mvp.insert(0, "順位", range(1, len(filtered_mvp) + 1))

                cols_show = ["順位", "選手名", "MVP_Score", "試合参加数", "Batting_Score", "Pitching_Score"]
                cols_name = ["順位", "選手名", "総合ポイント", "試合数", "打撃P", "投手P"]
                if has_def_data:
                    cols_show.append("Defense_Score")
                    cols_name.append("守備P")
                cols_show.extend(["RC", "OPS", "is_win", "投球回"])
                cols_name.extend(["RC", "OPS", "勝利", "投球回"])

                disp_mvp = filtered_mvp[cols_show].copy()
                disp_mvp.columns = cols_name

                disp_mvp["総合ポイント"] = disp_mvp["総合ポイント"].map(lambda x: f"{x:.1f}")
                disp_mvp["打撃P"] = disp_mvp["打撃P"].map(lambda x: f"{x:.1f}")
                disp_mvp["投手P"] = disp_mvp["投手P"].map(lambda x: f"{x:.1f}")
                if has_def_data:
                    disp_mvp["守備P"] = disp_mvp["守備P"].map(lambda x: f"{x:.1f}")
                disp_mvp["RC"] = disp_mvp["RC"].map(lambda x: f"{x:.2f}")
                disp_mvp["OPS"] = disp_mvp["OPS"].map(lambda x: f"{x:.3f}")
                disp_mvp["投球回"] = disp_mvp["投球回"].map(lambda x: f"{x:.1f}")

                st.dataframe(disp_mvp, use_container_width=True, hide_index=True)

                with st.expander("ℹ️ 総合ポイントの算出モデル解説"):
                    st.markdown("""
                    * **総合ポイント** = 打撃P + 投手P + 守備P + (試合参加数 × 1.0)
                    * **打撃P**: `(OPS × 50.0) + (RC × 3.0) + (盗塁 × 1.0)`
                    * **投手P**: `(投球回 × 1.0) + (奪三振 × 0.3) + (3.50 - 防御率) × 投球回 × 0.3`
                    * **守備P**: `((通常守備機会 × 1.0 + 捕手守備機会 × 2.5) × 守備率) - (失策数 × 2.0)`
                    * **RC (創出得点)**: `((安打 + 四死球) × 塁打) ÷ (打数 + 四死球)`
                    
                    ---
                    💡 **RC（Runs Created：創出得点）とは？**  
                    打者が「1人でチームの得点を何点生み出したか」を推定するセイバーメトリクス指標です。出塁能力（安打・四死球）と長打力を掛け合わせて算出され、前後の打者の打撃や打順などの展開に左右されず、純粋な個人としての打撃貢献度を測ることができます。
                    """)
            else:
                st.info("データがありません")

        with st_bat:
            if not df_b_tg.empty:
                stats = df_b_tg.groupby("選手名").agg(agg_rules_b).reset_index()
                stats["PA"] = stats["is_ab"] + stats["is_bb"] + stats["is_sf"]
                stats["打率"] = stats.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                stats["出塁率"] = stats.apply(lambda x: (x["is_hit"] + x["is_bb"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
                stats["TotalBases"] = stats["is_1b"] + (stats["is_2b"] * 2) + (stats["is_3b"] * 3) + (stats["is_hr"] * 4)
                stats["長打率"] = stats.apply(lambda x: x["TotalBases"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                stats["OPS"] = stats["出塁率"] + stats["長打率"]
                stats["RC"] = stats.apply(lambda x: ((x["is_hit"] + x["is_bb"]) * x["TotalBases"]) / (x["is_ab"] + x["is_bb"]) if (x["is_ab"] + x["is_bb"]) > 0 else 0, axis=1)
                stats["Batting_Score"] = stats["OPS"] * 50.0 + stats["RC"] * 3.0 + stats["盗塁"] * 1.0

                stats["三振率"] = stats.apply(lambda x: x["is_so"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
                stats["盗塁成功率"] = stats.apply(lambda x: x["盗塁"] / (x["盗塁"] + x["盗塁死"]) if (x["盗塁"] + x["盗塁死"]) > 0 else 0, axis=1)
                stats["BB/K"] = stats.apply(lambda x: x["is_bb"] / x["is_so"] if x["is_so"] > 0 else x["is_bb"], axis=1)
                stats["IsoP"] = stats["長打率"] - stats["打率"]
                stats["IsoD"] = stats["出塁率"] - stats["打率"]

                for c in ["is_hit", "is_ab", "is_1b", "is_2b", "is_3b", "is_hr", "is_bb", "打点", "得点", "盗塁", "is_so", "盗塁死"]:
                    stats[c] = stats[c].astype(int)

                disp = stats.rename(columns={
                    "is_hit": "安打", "is_ab": "打数", "is_1b": "単打", "is_2b": "二塁打", "is_3b": "三塁打",
                    "is_hr": "本塁打", "is_bb": "四死球", "is_so": "三振"
                }).sort_values("OPS", ascending=False).reset_index(drop=True)

                disp.insert(0, "順位", range(1, len(disp) + 1))

                for col in ["打率", "OPS", "長打率", "出塁率", "三振率", "盗塁成功率", "BB/K", "IsoP", "IsoD"]:
                    disp[col] = disp[col].map(lambda x: f"{x:.3f}")
                disp["Batting_Score"] = disp["Batting_Score"].map(lambda x: f"{x:.1f}")
                disp["RC"] = disp["RC"].map(lambda x: f"{x:.2f}")

                st.caption("💡 ヒント: OPS、RC、打撃ポイントなどの各列ヘッダーをタップするとソートが可能です。")
                st.dataframe(
                    disp[["順位", "選手名", "Batting_Score", "打率", "OPS", "長打率", "出塁率", "RC", "打数", "安打", "本塁打", "打点", "四死球", "三振", "BB/K", "三振率", "盗塁", "盗塁成功率"]].rename(columns={"Batting_Score": "打撃P"}),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("データなし")

        with st_pit:
            if not df_p_tg.empty:
                stats_p = df_p_tg.groupby("選手名").agg(agg_rules_p).reset_index()
                stats_p["TotalSO"] = stats_p["is_so"] + stats_p["奪三振"]
                stats_p["投球回_val"] = stats_p["アウト数"] / 3
                stats_p["防御率"] = stats_p.apply(lambda x: (x["自責点"] * 7) / x["投球回_val"] if x["投球回_val"] > 0 else 0, axis=1)
                stats_p["WHIP"] = stats_p.apply(lambda x: (x["total_bb"] + x["被安打"]) / x["投球回_val"] if x["投球回_val"] > 0 else 0, axis=1)
                stats_p["投球回"] = stats_p["アウト数"].apply(lambda x: f"{int(x // 3)}.{int(x % 3)}")

                def p_score_calc(r):
                    p_inn, p_era, p_so = r["投球回_val"], r["防御率"], r["TotalSO"]
                    if p_inn <= 0 or p_era >= 90:
                        return 0.0
                    era_pts = (3.50 - p_era) * p_inn * 0.3
                    return max(0.0, p_inn * 1.0 + p_so * 0.3 + era_pts)

                stats_p["Pitching_Score"] = stats_p.apply(p_score_calc, axis=1)

                for c in ["is_win", "is_lose", "TotalSO", "自責点", "total_bb"]:
                    stats_p[c] = stats_p[c].astype(int)

                disp_p = stats_p[["選手名", "Pitching_Score", "防御率", "WHIP", "is_win", "is_lose", "投球回", "TotalSO", "total_bb", "自責点"]].copy()
                disp_p.columns = ["選手名", "投手P", "防御率", "WHIP", "勝", "敗", "投球回", "奪三振", "四死球", "自責点"]
                disp_p = disp_p.sort_values("防御率").reset_index(drop=True)

                disp_p.insert(0, "順位", range(1, len(disp_p) + 1))
                disp_p["投手P"] = disp_p["投手P"].map(lambda x: f"{x:.1f}")
                disp_p["防御率"] = disp_p["防御率"].map(lambda x: f"{x:.2f}")
                disp_p["WHIP"] = disp_p["WHIP"].map(lambda x: f"{x:.2f}")
                st.dataframe(disp_p, use_container_width=True, hide_index=True)
            else:
                st.info("データなし")

        with st_fld:
            if not saber_f.empty:
                disp_df = saber_f[["選手名", "Defense_Score", "守備機会", "失策数", "守備率"]].copy()
                disp_df.columns = ["選手名", "守備P", "守備機会", "失策", "守備率"]

                disp_df = disp_df.sort_values(["守備P", "守備率", "守備機会"], ascending=[False, False, False]).reset_index(drop=True)

                disp_df["守備P"] = disp_df["守備P"].map(lambda x: f"{x:.1f}")
                disp_df["守備率"] = disp_df["守備率"].map(lambda x: f"{x:.3f}")

                disp_df = disp_df[disp_df["選手名"] != ""].reset_index(drop=True)
                disp_df.insert(0, "順位", range(1, len(disp_df) + 1))

                st.dataframe(disp_df, use_container_width=True, hide_index=True)
            else:
                st.info("守備記録がありません")

        with st_game:
            if not df_b_calc.empty or not df_p_calc.empty:
                # 💡 前処理済みの df_b_calc / df_p_calc を参照（打者名・投手名から選手名への補正が反映済み）
                df_b_target = df_b_calc[df_b_calc["Year"].isin(years[:2])] if target_year == "直近2年分" else (df_b_calc[df_b_calc["Year"] == target_year] if target_year != "通算" else df_b_calc)
                df_p_target = df_p_calc[df_p_calc["Year"].isin(years[:2])] if target_year == "直近2年分" else (df_p_calc[df_p_calc["Year"] == target_year] if target_year != "通算" else df_p_calc)
                df_all_logs = pd.concat([df_b_target, df_p_target], ignore_index=True)

                if not df_all_logs.empty:
                    for col in ["日付", "試合種別", "選手名"]:
                        if col in df_all_logs.columns:
                            df_all_logs[col] = df_all_logs[col].fillna("").astype(str).str.strip()
                    df_all_logs["対戦相手"] = df_all_logs["対戦相手"].fillna("").astype(str).str.strip() if "対戦相手" in df_all_logs.columns else ""
                    df_all_logs["Game_ID"] = df_all_logs["日付"] + "_" + df_all_logs["対戦相手"] + "_" + df_all_logs["試合種別"]

                    team_games = df_all_logs[["Game_ID", "試合種別"]].drop_duplicates()
                    official_games = len(team_games[team_games["試合種別"].isin(OFFICIAL_GAME_TYPES)])
                    practice_games = len(team_games[team_games["試合種別"] == "練習試合"])
                    other_games = len(team_games[~team_games["試合種別"].isin(OFFICIAL_GAME_TYPES) & (team_games["試合種別"] != "練習試合")])
                    total_games = official_games + practice_games + other_games

                    # 💡 "チーム記録" に加えて 空文字 ("") や NaN も除外
                    df_personal_logs = df_all_logs[
                        (~df_all_logs["選手名"].isin(["チーム記録", ""])) & 
                        (df_all_logs["選手名"].notna())
                    ].copy()

                    if not df_personal_logs.empty:
                        df_personal_logs["Date_dt"] = pd.to_datetime(df_personal_logs["日付"], errors='coerce')
                        df_all_logs["Date_dt"] = pd.to_datetime(df_all_logs["日付"], errors='coerce')
                        latest_game_date = df_all_logs["Date_dt"].max()
                        ref_date = latest_game_date if pd.notna(latest_game_date) else pd.to_datetime(datetime.date.today())
                        one_year_ago = ref_date - pd.Timedelta(days=365)

                        off_counts = df_personal_logs[df_personal_logs["試合種別"].isin(OFFICIAL_GAME_TYPES)].groupby("選手名")["Game_ID"].nunique().reset_index(name="公式戦参加数")
                        prac_counts = df_personal_logs[df_personal_logs["試合種別"] == "練習試合"].groupby("選手名")["Game_ID"].nunique().reset_index(name="練習試合参加数")
                        other_counts = df_personal_logs[~df_personal_logs["試合種別"].isin(OFFICIAL_GAME_TYPES) & (df_personal_logs["試合種別"] != "練習試合")].groupby("選手名")["Game_ID"].nunique().reset_index(name="その他参加数")

                        counts_1y = df_personal_logs[df_personal_logs["Date_dt"] >= one_year_ago].groupby("選手名")["Game_ID"].nunique().reset_index(name="直近1年参加数")
                        last_dates = df_personal_logs.groupby("選手名")["Date_dt"].max().reset_index(name="最終参加日")

                        game_stats = df_personal_logs[["選手名"]].drop_duplicates() \
                            .merge(off_counts, on="選手名", how="left").merge(prac_counts, on="選手名", how="left") \
                            .merge(other_counts, on="選手名", how="left").merge(counts_1y, on="選手名", how="left") \
                            .merge(last_dates, on="選手名", how="left").fillna(0)

                        game_stats["全試合参加数"] = game_stats["公式戦参加数"] + game_stats["練習試合参加数"] + game_stats["その他参加数"]
                        game_stats = game_stats[game_stats["全試合参加数"] > 0]

                        if not game_stats.empty:
                            game_stats["全体参加率"] = (game_stats["全試合参加数"] / total_games * 100).map("{:.1f}%".format) if total_games > 0 else "0.0%"
                            game_stats["公式戦参加率"] = (game_stats["公式戦参加数"] / official_games * 100).map("{:.1f}%".format) if official_games > 0 else "0.0%"

                            def format_inactive_period(last_d):
                                if pd.isna(last_d) or last_d == 0:
                                    return "-"
                                days = (ref_date - last_d).days
                                if days <= 0:
                                    return "直近参加"
                                elif days < 30:
                                    return f"{days}日"
                                elif days < 365:
                                    return f"{days // 30}ヶ月 ({days}日)"
                                else:
                                    return f"{days // 365}年{(days % 365) // 30}ヶ月 ({days}日)"

                            game_stats["活動未参加期間"] = game_stats["最終参加日"].apply(format_inactive_period)
                            disp_game = game_stats[["選手名", "全試合参加数", "全体参加率", "公式戦参加数", "公式戦参加率", "直近1年参加数", "活動未参加期間"]].sort_values("全試合参加数", ascending=False).reset_index(drop=True)
                            disp_game.insert(0, "順位", range(1, len(disp_game) + 1))

                            st.markdown(f"**対象期間のチーム総試合数**: 全 {total_games} 試合 (公式戦: {official_games} / 練習試合: {practice_games} / その他: {other_games})")
                            st.dataframe(disp_game, use_container_width=True, hide_index=True)
                        else:
                            st.info("参加記録がありません")
                    else:
                        st.info("参加記録がありません")
                else:
                    st.info("データがありません")
            else:
                st.info("データがありません")

    # ----------------------------------------------------
    # 2. 個人年度別 + 通算
    # ----------------------------------------------------
    with t_year:
        if "personal_stats_selected_player" not in st.session_state:
            st.session_state["personal_stats_selected_player"] = None

        current_sel_player = st.session_state.get("personal_stats_selected_player")
        popover_label = f"👤 選手選択: {current_sel_player} 🔽" if current_sel_player else "👤 選手選択: 未選択 🔽"

        with st.popover(popover_label, use_container_width=True):
            st.markdown("##### 👤 表示する選手をタップして選択")
            st.pills(
                "選手選択",
                STATS_PLAYERS,
                format_func=local_fmt,
                key="personal_stats_selected_player",
                label_visibility="collapsed"
            )

        sel_player = st.session_state.get("personal_stats_selected_player", None)

        if not sel_player:
            st.info("👆 上のボタンから表示する選手を選択してください。")
        else:
            if not df_b_calc.empty:
                my_b = df_b_calc[df_b_calc["選手名"] == sel_player]
                if not my_b.empty:
                    hist = my_b.groupby("Year").agg(agg_rules_b).sort_index(ascending=False)
                    total_s = my_b.agg(agg_rules_b)
                    hist_total = pd.DataFrame(total_s).T
                    hist_total.index = ["通算"]

                    combined_hist = pd.concat([hist_total, hist])

                    combined_hist["PA"] = combined_hist["is_ab"] + combined_hist["is_bb"] + combined_hist["is_sf"]
                    combined_hist["打率"] = combined_hist.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                    combined_hist["出塁率"] = combined_hist.apply(lambda x: (x["is_hit"] + x["is_bb"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
                    combined_hist["TotalBases"] = combined_hist["is_1b"] + (combined_hist["is_2b"] * 2) + (combined_hist["is_3b"] * 3) + (combined_hist["is_hr"] * 4)
                    combined_hist["長打率"] = combined_hist.apply(lambda x: x["TotalBases"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                    combined_hist["OPS"] = combined_hist["出塁率"] + combined_hist["長打率"]

                    combined_hist["三振率"] = combined_hist.apply(lambda x: x["is_so"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
                    combined_hist["盗塁成功率"] = combined_hist.apply(lambda x: x["盗塁"] / (x["盗塁"] + x["盗塁死"]) if (x["盗塁"] + x["盗塁死"]) > 0 else 0, axis=1)
                    combined_hist["BB/K"] = combined_hist.apply(lambda x: x["is_bb"] / x["is_so"] if x["is_so"] > 0 else x["is_bb"], axis=1)
                    combined_hist["IsoP"] = combined_hist["長打率"] - combined_hist["打率"]
                    combined_hist["IsoD"] = combined_hist["出塁率"] - combined_hist["打率"]

                    for col in ["is_hit", "is_ab", "is_hr", "is_bb", "打点", "盗塁", "is_so", "盗塁死"]:
                        combined_hist[col] = combined_hist[col].astype(int)

                    disp_hist = pd.DataFrame()
                    disp_hist["打率"] = combined_hist["打率"]
                    disp_hist["OPS"] = combined_hist["OPS"]
                    disp_hist["長打率"] = combined_hist["長打率"]
                    disp_hist["出塁率"] = combined_hist["出塁率"]
                    disp_hist["IsoP"] = combined_hist["IsoP"]
                    disp_hist["IsoD"] = combined_hist["IsoD"]
                    disp_hist["打数"] = combined_hist["is_ab"]
                    disp_hist["安打"] = combined_hist["is_hit"]
                    disp_hist["本塁打"] = combined_hist["is_hr"]
                    disp_hist["打点"] = combined_hist["打点"]
                    disp_hist["四死球"] = combined_hist["is_bb"]
                    disp_hist["三振"] = combined_hist["is_so"]
                    disp_hist["BB/K"] = combined_hist["BB/K"]
                    disp_hist["三振率"] = combined_hist["is_so"] / combined_hist["PA"]
                    disp_hist["盗塁"] = combined_hist["盗塁"]
                    disp_hist["盗塁成功率"] = combined_hist["盗塁成功率"]
                    disp_hist.index.name = "年度"

                    st.markdown("##### ⚔️ 打撃成績推移")
                    st.dataframe(
                        disp_hist.style.format({
                            "打率": "{:.3f}", "OPS": "{:.3f}", "長打率": "{:.3f}", "出塁率": "{:.3f}",
                            "三振率": "{:.3f}", "盗塁成功率": "{:.3f}", "BB/K": "{:.3f}", "IsoP": "{:.3f}", "IsoD": "{:.3f}"
                        }).map(
                            lambda x: "font-weight: bold; background-color: #f0f2f6;" if isinstance(x, str) else "",
                            subset=pd.IndexSlice[["通算"], :]
                        )
                    )
                else:
                    st.info("データなし")

            if not df_p_calc.empty:
                my_p = df_p_calc[df_p_calc["選手名"] == sel_player]
                if not my_p.empty:
                    hist_p = my_p.groupby("Year").agg(agg_rules_p).sort_index(ascending=False)
                    total_p_s = my_p.agg(agg_rules_p)
                    hist_p_total = pd.DataFrame(total_p_s).T
                    hist_p_total.index = ["通算"]

                    combined_p = pd.concat([hist_p_total, hist_p])

                    combined_p["TotalSO"] = combined_p["is_so"] + combined_p["奪三振"]
                    combined_p["Innings"] = combined_p["アウト数"] / 3
                    combined_p["防御率"] = combined_p.apply(
                        lambda x: (x["自責点"] * 7) / x["Innings"] if x["Innings"] > 0 else 0, axis=1
                    )
                    combined_p["勝率"] = combined_p.apply(
                        lambda x: x["is_win"] / (x["is_win"] + x["is_lose"])
                        if (x["is_win"] + x["is_lose"]) > 0 else 0, axis=1
                    )
                    combined_p["奪三振率"] = combined_p.apply(
                        lambda x: (x["TotalSO"] * 7) / x["Innings"]
                        if x["Innings"] > 0 else 0, axis=1
                    )
                    combined_p["WHIP"] = combined_p.apply(
                        lambda x: (x["total_bb"] + x["被安打"]) / x["Innings"]
                        if x["Innings"] > 0 else 0, axis=1
                    )
                    combined_p["回"] = combined_p["アウト数"].apply(lambda x: f"{int(x // 3)}.{int(x % 3)}")

                    for col in ["is_win", "is_lose", "TotalSO", "total_bb"]:
                        combined_p[col] = combined_p[col].astype(int)

                    disp_p_hist = pd.DataFrame()
                    disp_p_hist["防御率"] = combined_p["防御率"]
                    disp_p_hist["勝率"] = combined_p["勝率"]
                    disp_p_hist["WHIP"] = combined_p["WHIP"]
                    disp_p_hist["奪三振率"] = combined_p["奪三振率"]
                    disp_p_hist["投球回"] = combined_p["回"]
                    disp_p_hist["勝"] = combined_p["is_win"]
                    disp_p_hist["敗"] = combined_p["is_lose"]
                    disp_p_hist["奪三振"] = combined_p["TotalSO"]
                    disp_p_hist["四死球"] = combined_p["total_bb"]
                    disp_p_hist.index.name = "年度"

                    st.markdown("##### 🛡️ 投手成績推移")
                    st.dataframe(
                        disp_p_hist.style.format({
                            "防御率": "{:.2f}", "勝率": "{:.3f}", "WHIP": "{:.2f}", "奪三振率": "{:.2f}"
                        })
                    )
                else:
                    st.info("データなし")

            if not df_p_calc.empty and "処理野手" in df_p_calc.columns and "守備位置" in df_p_calc.columns:
                fld_base_all = df_p_calc.copy().reset_index(drop=True)
                if "Year" not in fld_base_all.columns:
                    fld_base_all["Year"] = pd.to_datetime(fld_base_all["日付"], errors='coerce').dt.strftime('%Y').fillna("不明")
                fld_base_all["Original_Idx"] = fld_base_all.index
                fld_base = fld_base_all[fld_base_all["処理野手"].notna() & (fld_base_all["処理野手"] != "")].copy()

                if not fld_base.empty:
                    fld_base = fld_base[~fld_base["結果"].astype(str).str.contains("本塁打", na=False)]

                if not fld_base.empty:
                    fld_base["処理野手"] = fld_base["処理野手"].astype(str)
                    fld_base["守備位置"] = fld_base["守備位置"].astype(str)
                    fld_base = fld_base[fld_base["処理野手"].str.contains(sel_player, na=False)]

                    if not fld_base.empty:
                        fld_base["zipped"] = fld_base.apply(
                            lambda x: list(dict.fromkeys(zip(str(x["処理野手"]).split("-"), str(x["守備位置"]).split("-")))),
                            axis=1
                        )
                        fld_expanded = fld_base.explode("zipped").reset_index(drop=True)

                        if not fld_expanded.empty:
                            fld_expanded[["FielderName", "FielderPos"]] = pd.DataFrame(fld_expanded["zipped"].tolist(), index=fld_expanded.index)
                            my_f = fld_expanded[fld_expanded["FielderName"] == sel_player].copy()

                            if not my_f.empty:
                                my_f["is_error"] = my_f["結果"].astype(str).str.contains("失策|暴投|捕逸", na=False)
                                fld_unique = my_f.groupby(["Original_Idx", "FielderName", "FielderPos"]).agg(
                                    Year=("Year", "first"), is_error=("is_error", "max")
                                ).reset_index()

                                hist_f = fld_unique.groupby("Year").agg(守備機会=("FielderName", "count"), 失策数=("is_error", "sum")).sort_index(ascending=False)
                                hist_f_total = pd.DataFrame({"守備機会": [fld_unique["FielderName"].count()], "失策数": [fld_unique["is_error"].sum()]}, index=["通算"])
                                combined_f = pd.concat([hist_f_total, hist_f])
                                combined_f["守備率"] = combined_f.apply(lambda x: (x["守備機会"] - x["失策数"]) / x["守備機会"] if x["守備機会"] > 0 else 0.0, axis=1)

                                disp_f_hist = pd.DataFrame()
                                disp_f_hist["守備率"] = combined_f["守備率"]
                                disp_f_hist["守備機会"] = combined_f["守備機会"]
                                disp_f_hist["失策"] = combined_f["失策数"]
                                disp_f_hist.index.name = "年度"

                                st.markdown("##### 🧤 守備成績推移")
                                st.dataframe(disp_f_hist.style.format({"守備率": "{:.3f}"}))
                            else:
                                st.caption("※ 守備記録なし")

    # ----------------------------------------------------
    # 3. ランキング・歴代記録
    # ----------------------------------------------------
    with t_rank_rec:
        sub_tab_rec, sub_tab_period = st.tabs(["👑 歴代記録 (通算・シーズン)", "📅 期間別ランキング"])

        # --- 3-1. 歴代記録 サブタブ ---
        with sub_tab_rec:
            st.markdown("#### 👑 歴代記録")
            rec_mode = st.radio("対象範囲", ["シーズン最高", "生涯通算"], horizontal=True, key="rec_mode_radio")

            df_b_target = df_b_calc.copy()
            df_p_target = df_p_calc.copy()

            if not df_b_target.empty:
                df_b_target["Date"] = pd.to_datetime(df_b_target["日付"], errors='coerce')
                df_b_target["Year"] = df_b_target["Date"].dt.year.astype(str)

            if not df_p_target.empty:
                df_p_target["Date"] = pd.to_datetime(df_p_target["日付"], errors='coerce')
                df_p_target["Year"] = df_p_target["Date"].dt.year.astype(str)

            if "シーズン" in rec_mode:
                COEFF_AB, COEFF_INN = 1.0, 0.8
                MIN_AB, MIN_INN = 10, 10

                if "日付" in df_b_target.columns and "Year" in df_b_target.columns and not df_b_target.empty:
                    games_by_year_b = df_b_target.groupby("Year")["日付"].nunique().to_dict()
                else:
                    games_by_year_b = {}

                if "日付" in df_p_target.columns and "Year" in df_p_target.columns and not df_p_target.empty:
                    games_by_year_p = df_p_target.groupby("Year")["日付"].nunique().to_dict()
                else:
                    games_by_year_p = {}

                df_bat_res = get_ranking_df(df_b_target, ["Year", "選手名"], agg_rules_b)
                df_bat_res["Display"] = df_bat_res["選手名"] + " (" + df_bat_res["Year"] + ")"
                df_bat_res["Req_Quota"] = df_bat_res["Year"].map(games_by_year_b).fillna(0) * COEFF_AB

                df_bat_rate_target = df_bat_res[
                    (df_bat_res["is_ab"] >= df_bat_res["Req_Quota"]) &
                    (df_bat_res["is_ab"] >= MIN_AB)
                ].copy()

                df_pit_res = get_ranking_df(df_p_target, ["Year", "選手名"], agg_rules_p)
                df_pit_res["Display"] = df_pit_res["選手名"] + " (" + df_pit_res["Year"] + ")"
                df_pit_res["Innings"] = df_pit_res["アウト数"] / 3
                df_pit_res["Req_Quota"] = df_pit_res["Year"].map(games_by_year_p).fillna(0) * COEFF_INN

                df_pit_rate_target = df_pit_res[
                    (df_pit_res["Innings"] >= df_pit_res["Req_Quota"]) &
                    (df_pit_res["Innings"] >= MIN_INN)
                ].copy()

            else:
                MIN_AB_LIFETIME, MIN_INN_LIFETIME = 20, 15

                df_bat_res = get_ranking_df(df_b_target, ["選手名"], agg_rules_b)
                df_bat_res["Display"] = df_bat_res["選手名"]
                df_bat_rate_target = df_bat_res[df_bat_res["is_ab"] >= MIN_AB_LIFETIME].copy()

                df_pit_res = get_ranking_df(df_p_target, ["選手名"], agg_rules_p)
                df_pit_res["Display"] = df_pit_res["選手名"]
                df_pit_res["Innings"] = df_pit_res["アウト数"] / 3
                df_pit_rate_target = df_pit_res[df_pit_res["Innings"] >= MIN_INN_LIFETIME].copy()

            if not df_bat_res.empty:
                for df in [df_bat_res, df_bat_rate_target]:
                    if df.empty:
                        continue
                    df["AVG"] = df.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                    obp = (df["is_hit"] + df["is_bb"]) / (df["is_ab"] + df["is_bb"] + df["is_sf"] + 1e-9)
                    slg = df["bases"] / (df["is_ab"] + 1e-9)
                    df["OPS"] = obp + slg

            if not df_pit_res.empty:
                for df in [df_pit_res, df_pit_rate_target]:
                    if df.empty:
                        continue
                    df["ERA"] = df.apply(lambda x: (x["自責点"] * 7) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)
                    df["TotalSO"] = df["is_so"] + df["奪三振"]
                    df["WHIP"] = df.apply(lambda x: (x["total_bb"] + x["被安打"]) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)

            st.divider()

            if not df_bat_res.empty:
                st.markdown("##### ⚔️ 歴代打撃トップ10")
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    show_top10("打率", df_bat_rate_target, "AVG", "Display", "AVG", suffix="", format_float=True)
                with tc2:
                    show_top10("OPS", df_bat_rate_target, "OPS", "Display", "OPS", suffix="", format_float=True)
                with tc3:
                    show_top10("安打数", df_bat_res, "is_hit", "Display", "is_hit", suffix=" 本")

                st.write("")
                tc4, tc5, tc6 = st.columns(3)
                with tc4:
                    show_top10("本塁打", df_bat_res, "is_hr", "Display", "is_hr", suffix=" 本")
                with tc5:
                    show_top10("打点", df_bat_res, "打点", "Display", "打点", suffix=" 点")
                with tc6:
                    show_top10("盗塁", df_bat_res, "盗塁", "Display", "盗塁", suffix=" 個")
            else:
                st.info("打撃データがありません")

            st.divider()

            if not df_pit_res.empty:
                if "Display" in df_pit_res.columns:
                    df_pit_res["Display"] = df_pit_res["Display"].astype(str).str.replace(r'\.0\)', ')', regex=True)
                if "Display" in df_pit_rate_target.columns:
                    df_pit_rate_target["Display"] = df_pit_rate_target["Display"].astype(str).str.replace(r'\.0\)', ')', regex=True)

                st.markdown("##### 🛡️ 歴代投手トップ10")
                tp1, tp2, tp3, tp4 = st.columns(4)
                with tp1:
                    show_top10("防御率", df_pit_rate_target, "ERA", "Display", "ERA", ascending=True, format_float=True)
                with tp2:
                    show_top10("WHIP", df_pit_rate_target, "WHIP", "Display", "WHIP", ascending=True, format_float=True)
                with tp3:
                    show_top10("勝利数", df_pit_res, "is_win", "Display", "is_win", suffix=" 勝")
                with tp4:
                    show_top10("奪三振", df_pit_res, "TotalSO", "Display", "TotalSO", suffix=" 個")
            else:
                st.info("投手データがありません")

        # --- 3-2. 期間別ランキング サブタブ ---
        with sub_tab_period:
            st.markdown("#### 🏆 期間別ランキング")
            period = st.radio("集計期間", ["年度別", "月間", "直近3試合"], horizontal=True, key="period_mode_radio")
            df_b_sub = df_b_calc.copy()
            df_p_sub = df_p_calc.copy()

            if "日付" in df_b_sub.columns and not df_b_sub.empty:
                df_b_sub["Date"] = pd.to_datetime(df_b_sub["日付"], errors='coerce')
            else:
                df_b_sub["Date"] = pd.Series(dtype="datetime64[ns]")

            if "日付" in df_p_sub.columns and not df_p_sub.empty:
                df_p_sub["Date"] = pd.to_datetime(df_p_sub["日付"], errors='coerce')
            else:
                df_p_sub["Date"] = pd.Series(dtype="datetime64[ns]")

            def_ab = 1
            def_inn = 1
            key_suffix = ""

            if period == "年度別":
                ys = sorted([y for y in df_b_sub["Date"].dt.year.dropna().unique()], reverse=True)
                sy = st.selectbox("年度選択", ys, key="period_year_select") if len(ys) > 0 else datetime.date.today().year
                key_suffix = str(sy)

                df_b_sub = df_b_sub[df_b_sub["Date"].dt.year == sy] if not df_b_sub.empty else df_b_sub
                df_p_sub = df_p_sub[df_p_sub["Date"].dt.year == sy] if not df_p_sub.empty else df_p_sub
                if not df_b_sub.empty:
                    def_ab = int(df_b_sub["日付"].nunique() * 1.0)
                    def_inn = int(df_b_sub["日付"].nunique() * 0.8)

            elif period == "月間":
                if not df_b_sub.empty:
                    df_b_sub["YM"] = df_b_sub["Date"].dt.strftime('%Y-%m')
                    ms = sorted([m for m in df_b_sub["YM"].dropna().unique()], reverse=True)
                else:
                    ms = []

                sm = st.selectbox("月選択", ms, key="period_month_select") if len(ms) > 0 else None

                if sm:
                    key_suffix = str(sm)
                    df_b_sub = df_b_sub[df_b_sub["YM"] == sm]
                    if not df_p_sub.empty:
                        df_p_sub["YM"] = df_p_sub["Date"].dt.strftime('%Y-%m')
                        df_p_sub = df_p_sub[df_p_sub["YM"] == sm]
                    def_ab = int(df_b_sub["日付"].nunique())
                    def_inn = def_ab
                else:
                    df_b_sub = pd.DataFrame()
                    df_p_sub = pd.DataFrame()

            else:
                dates = sorted([d for d in df_b_sub["Date"].dropna().unique()], reverse=True)[:3]
                df_b_sub = df_b_sub[df_b_sub["Date"].isin(dates)] if not df_b_sub.empty else df_b_sub
                df_p_sub = df_p_sub[df_p_sub["Date"].isin(dates)] if not df_p_sub.empty else df_p_sub
                def_ab = 3
                def_inn = 3
                key_suffix = "recent"

            c_f1, c_f2 = st.columns(2)
            min_ab = c_f1.number_input("規定打席", value=max(1, def_ab), min_value=1, key=f"ab_{period}_{key_suffix}")
            min_inn = c_f2.number_input("規定投球回", value=max(1, def_inn), min_value=1, key=f"inn_{period}_{key_suffix}")

            st.divider()

            if not df_b_sub.empty:
                rank_b = get_ranking_df(df_b_sub, ["選手名"], agg_rules_b)
                rank_b["Total_PA"] = rank_b["is_ab"] + rank_b["is_bb"]
                rank_b["AVG"] = rank_b.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                rank_b["OBP"] = (rank_b["is_hit"] + rank_b["is_bb"]) / (rank_b["is_ab"] + rank_b["is_bb"] + rank_b["is_sf"] + 1e-9)
                rank_b["SLG"] = rank_b["bases"] / (rank_b["is_ab"] + 1e-9)
                rank_b["OPS"] = (rank_b["OBP"] + rank_b["SLG"]).fillna(0)

                st.markdown("##### ⚔️ 打撃部門")
                r1, r2, r3 = st.columns(3)
                with r1:
                    show_top10("打率", rank_b[rank_b["Total_PA"] >= min_ab], "AVG", "選手名", "AVG", format_float=True)
                with r2:
                    show_top10("本塁打", rank_b, "is_hr", "選手名", "is_hr", suffix="本")
                with r3:
                    show_top10("打点", rank_b, "打点", "選手名", "打点", suffix="点")

                st.write("")
                r4, r5, r6 = st.columns(3)
                with r4:
                    show_top10("安打", rank_b, "is_hit", "選手名", "is_hit", suffix="本")
                with r5:
                    show_top10("盗塁", rank_b, "盗塁", "選手名", "盗塁", suffix="個")
                with r6:
                    show_top10("OPS", rank_b[rank_b["is_ab"] >= min_ab], "OPS", "選手名", "OPS", format_float=True)
            else:
                st.info("データなし")
            st.divider()

            if not df_p_sub.empty:
                rank_p = get_ranking_df(df_p_sub, ["選手名"], agg_rules_p)
                rank_p["Innings"] = rank_p["アウト数"] / 3
                rank_p["ERA"] = rank_p.apply(lambda x: (x["自責点"] * 7) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)
                rank_p["TotalSO"] = rank_p["is_so"] + rank_p["奪三振"]
                rank_p["WHIP"] = rank_p.apply(lambda x: (x["total_bb"] + x["被安打"]) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)

                st.markdown("##### 🛡️ 投手部門")
                st.caption("※ WHIP: (被安打 + 与四死球) ÷ 投球回。1イニングあたりに出した走者の数。")
                p1, p2, p3, p4 = st.columns(4)
                with p1:
                    show_top10("防御率", rank_p[rank_p["Innings"] >= min_inn], "ERA", "選手名", "ERA", ascending=True, format_float=True)
                with p2:
                    show_top10("WHIP", rank_p[rank_p["Innings"] >= min_inn], "WHIP", "選手名", "WHIP", ascending=True, format_float=True)
                with p3:
                    show_top10("勝利", rank_p, "is_win", "選手名", "is_win", suffix="勝")
                with p4:
                    show_top10("奪三振", rank_p, "TotalSO", "選手名", "TotalSO", suffix="個")
            else:
                st.info("データなし")