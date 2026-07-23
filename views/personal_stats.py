import streamlit as st
import pandas as pd
import datetime
import unicodedata
from config.settings import ALL_PLAYERS, PLAYER_NUMBERS, OFFICIAL_GAME_TYPES

# ==========================================
# --- ネットとローカルの二段構えでリストを取得 ---
# ==========================================
if "HIDDEN_PLAYERS_TOTAL" in st.secrets:
    # 1. ネット上(Streamlit Cloud)に設定があればそれを使う
    HIDDEN_PLAYERS_TOTAL = st.secrets["HIDDEN_PLAYERS_TOTAL"]
else:
    # 2. なければローカルのファイルから読み込む
    try:
        from local_secrets import HIDDEN_PLAYERS_TOTAL
    except ImportError:
        HIDDEN_PLAYERS_TOTAL = []
# ==========================================

def show_personal_stats(df_batting, df_pitching):
    st.title(" 📊 個人成績")


    # =========================================================
    # 1. データ前処理
    # =========================================================
    
    # --- 打撃データ ---
    if not df_batting.empty:
        # 日付からYearを作成 (2026.0問題の解消)
        df_batting["Year"] = pd.to_datetime(df_batting["日付"], errors='coerce').dt.strftime('%Y')
        df_batting["Year"] = df_batting["Year"].fillna("不明")
        
        df_b_calc = df_batting[df_batting["選手名"] != "チーム記録"].copy()

        df_b_calc["結果"] = df_b_calc["結果"].astype(str).str.replace(r"\s+", "", regex=True)

        # 1. 安打の判定
        df_b_calc["is_hit"] = df_b_calc["結果"].str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)

        # 2. 打数(AB)の判定方法
        non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
        is_valid = ~df_b_calc["結果"].isin(["", "nan", "None", "-"])
        is_not_excluded = ~df_b_calc["結果"].str.contains(non_ab_pattern, na=False)
        df_b_calc["is_ab"] = (is_valid & is_not_excluded).astype(int)
        
        df_b_calc["is_hr"] = df_b_calc["結果"].str.contains("本塁打", na=False).astype(int)
        df_b_calc["is_so"] = df_b_calc["結果"].str.contains("三振", na=False).astype(int)

        # 長打率計算用の塁打フラグ
        df_b_calc["is_1b"] = df_b_calc["結果"].str.contains("単打", na=False).astype(int)
        df_b_calc["is_2b"] = df_b_calc["結果"].str.contains("二塁打", na=False).astype(int)
        df_b_calc["is_3b"] = df_b_calc["結果"].str.contains("三塁打", na=False).astype(int)
        
        # 四死球・犠飛
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
        
        if "選手名" in df_pitching.columns:
            df_p_calc = df_pitching[df_pitching["選手名"] != "チーム記録"].copy()
        else:
            df_p_calc = df_pitching.copy()

        if "選手名" in df_p_calc.columns:
            df_p_calc = df_p_calc[df_p_calc["選手名"] != "チーム記録"]
            df_p_calc["選手名"] = df_p_calc["選手名"].replace("", pd.NA).fillna(df_p_calc["選手名"])
        else:
            df_p_calc["選手名"] = df_p_calc["選手名"]

        df_p_calc = df_p_calc[df_p_calc["選手名"] != "チーム記録"]

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
            if c not in df_p_calc.columns: df_p_calc[c] = 0
            df_p_calc[c] = pd.to_numeric(df_p_calc[c], errors='coerce').fillna(0)
            
        if "処理野手" not in df_p_calc.columns: df_p_calc["処理野手"] = ""

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
        return df.groupby(group_keys).agg(agg_dict).reset_index()

    def show_top5(title, df, sort_col, label_col, value_col, ascending=False, suffix="", format_float=False):
        st.markdown(f"**{title}**")
        if ascending:
            target = df.copy() 
        else:
            target = df[df[value_col] > 0].copy()

        top5 = target.sort_values(sort_col, ascending=ascending).head(5).reset_index(drop=True)
        
        if top5.empty:
            st.caption("データなし")
        else:
            for i, row in top5.iterrows():
                rank = i + 1
                icon = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else f"{rank}."
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

    t_total, t_year, t_rank, t_rec, t_saber = st.tabs(["個人通算", "個人年度別", "期間別ランキング", "歴代記録", "総合貢献度"])

    # ----------------------------------------------------
    # 1. 個人通算
    # ----------------------------------------------------
    with t_total:
        st.markdown("#### 📊 通算成績リスト")
        
        years_bat = set(df_batting["Year"].dropna().astype(str).unique()) if (df_batting is not None and not df_batting.empty and "Year" in df_batting.columns) else set()
        years_pit = set(df_pitching["Year"].dropna().astype(str).unique()) if (df_pitching is not None and not df_pitching.empty and "Year" in df_pitching.columns) else set()
        years = sorted(list(years_bat | years_pit), reverse=True)
        
        c1, c2 = st.columns(2)
        target_year = c1.selectbox("年度", ["通算"] + years)
        target_type = c2.selectbox("試合種別", ["全種別", "公式戦 (トータル)", "練習試合"])

        df_b_tg = df_b_calc.copy()
        df_p_tg = df_p_calc.copy()

        def normalize_name(text):
            if not isinstance(text, str) or not text:
                return ""
            text = unicodedata.normalize('NFKC', text)
            return text.strip().replace(" ", "").replace(" ", "").replace("さん", "")

        hidden_list_raw = HIDDEN_PLAYERS_TOTAL
        clean_hidden_list = [normalize_name(n) for n in hidden_list_raw]

        if not df_b_tg.empty:
            df_b_tg["_match_name"] = df_b_tg["選手名"].apply(normalize_name)
            df_b_tg = df_b_tg[~df_b_tg["_match_name"].isin(clean_hidden_list)]
            df_b_tg = df_b_tg.drop(columns=["_match_name"])

        if not df_p_tg.empty:
            df_p_tg["_match_name"] = df_p_tg["選手名"].apply(normalize_name)
            df_p_tg = df_p_tg[~df_p_tg["_match_name"].isin(clean_hidden_list)]
            df_p_tg = df_p_tg.drop(columns=["_match_name"])

        if target_year != "通算":
            df_b_tg = df_b_tg[df_b_tg["Year"] == target_year]
            df_p_tg = df_p_tg[df_p_tg["Year"] == target_year]

        if target_type == "公式戦 (トータル)":
            df_b_tg = df_b_tg[df_b_tg["試合種別"].isin(OFFICIAL_GAME_TYPES)]
            df_p_tg = df_p_tg[df_p_tg["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        elif target_type == "練習試合":
            df_b_tg = df_b_tg[df_b_tg["試合種別"] == "練習試合"]
            df_p_tg = df_p_tg[df_p_tg["試合種別"] == "練習試合"]

        st_bat, st_pit, st_fld, st_game = st.tabs(["打撃", "投手", "守備", "試合"])
        
        with st_bat:
            if not df_b_tg.empty:
                stats = df_b_tg.groupby("選手名").agg(agg_rules_b).reset_index()
                
                stats["PA"] = stats["is_ab"] + stats["is_bb"] + stats["is_sf"]
                stats["打率"] = stats.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
                stats["出塁率"] = stats.apply(
                    lambda x: (x["is_hit"] + x["is_bb"]) / x["PA"] if x["PA"] > 0 else 0, axis=1
                )
                stats["TotalBases"] = stats["is_1b"] + (stats["is_2b"] * 2) + (stats["is_3b"] * 3) + (stats["is_hr"] * 4)
                stats["長打率"] = stats.apply(lambda x: x["TotalBases"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
                stats["OPS"] = stats["出塁率"] + stats["長打率"]

                stats["三振率"] = stats.apply(lambda x: x["is_so"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
                stats["盗塁成功率"] = stats.apply(lambda x: x["盗塁"] / (x["盗塁"] + x["盗塁死"]) if (x["盗塁"] + x["盗塁死"]) > 0 else 0, axis=1)
                stats["BB/K"] = stats.apply(lambda x: x["is_bb"] / x["is_so"] if x["is_so"] > 0 else x["is_bb"], axis=1)
                stats["IsoP"] = stats["長打率"] - stats["打率"]
                stats["IsoD"] = stats["出塁率"] - stats["打率"]

                for c in ["is_hit", "is_ab", "is_1b", "is_2b", "is_3b", "is_hr", "is_bb", "打点", "得点", "盗塁", "is_so", "盗塁死"]: 
                    stats[c] = stats[c].astype(int)

                disp = stats.rename(columns={
                    "is_hit": "安打", 
                    "is_ab": "打数", 
                    "is_1b": "単打", 
                    "is_2b": "二塁打", 
                    "is_3b": "三塁打", 
                    "is_hr": "本塁打",
                    "is_bb": "四死球",
                    "is_so": "三振" 
                }).sort_values("OPS", ascending=False).reset_index(drop=True)
                
                disp.insert(0, "順位", range(1, len(disp) + 1))
                
                for col in ["打率", "OPS", "長打率", "出塁率", "三振率", "盗塁成功率", "BB/K", "IsoP", "IsoD"]:
                    disp[col] = disp[col].map(lambda x: f"{x:.3f}")

                st.caption("💡 ヒント: 列名（OPS、長打率、IsoP など）にマウスカーソルを合わせる（タップする）と、指標の解説が表示されます。")

                st.dataframe(
                    disp[["順位", "選手名", "打率", "OPS", "長打率", "出塁率", "IsoP", "IsoD", "打数", "安打", "本塁打", "打点", "四死球", "三振", "BB/K", "三振率", "盗塁", "盗塁成功率"]], 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "順位": st.column_config.TextColumn("順位", help="ランキング順位"),
                        "OPS": st.column_config.TextColumn("OPS", help="【OPS (On-base Plus Slugging)】\n出塁率と長打率を足した総合的な打撃指標です。\n得点との相関が非常に高く、0.800以上で優秀、1.000を超えると球界を代表する強打者とされます。"),
                        "長打率": st.column_config.TextColumn("長打率", help="【長打率 (SLG)】\n1打数あたりに平均して何塁打を稼げるかを示す指標です。"),
                        "出塁率": st.column_config.TextColumn("出塁率", help="【出塁率 (OBP)】\n打率に四死球を含めた「アウトにならずに出塁する確率」です。"),
                        "IsoP": st.column_config.TextColumn("IsoP", help="【純長打率 (IsoP / Isolated Power)】\n長打率から打率を引いた「純粋な長打力」を示します。"),
                        "IsoD": st.column_config.TextColumn("IsoD", help="【純出塁率 (IsoD / Isolated Discipline)】\n出塁率から打率を引いた数値です。四死球を選んで出塁する選球眼を示します。"),
                        "BB/K": st.column_config.TextColumn("BB/K", help="【四球/三振比率】\n四死球 ÷ 三振。1.000を超えると三振より四球が多い選球眼とコンタクトに優れた打者です。"),
                    }
                )
            else: 
                st.info("データなし")

        with st_pit:
            if not df_p_tg.empty:
                stats_p = df_p_tg.groupby("選手名").agg(agg_rules_p).reset_index()
                stats_p["TotalSO"] = stats_p["is_so"] + stats_p["奪三振"]
                stats_p["防御率"] = stats_p.apply(lambda x: (x["自責点"]*7)/(x["アウト数"]/3) if x["アウト数"]>0 else 0, axis=1)
                stats_p["投球回"] = stats_p["アウト数"].apply(lambda x: f"{int(x//3)}.{int(x%3)}")
                for c in ["is_win", "is_lose", "TotalSO", "自責点", "total_bb"]: stats_p[c] = stats_p[c].astype(int)

                disp_p = stats_p[["選手名", "防御率", "is_win", "is_lose", "投球回", "TotalSO", "total_bb", "自責点"]].copy()
                disp_p.columns = ["選手名", "防御率", "勝", "敗", "投球回", "奪三振", "四死球", "自責点"]
                disp_p = disp_p.sort_values("防御率").reset_index(drop=True)
                
                disp_p.insert(0, "順位", range(1, len(disp_p) + 1))
                
                disp_p["防御率"] = disp_p["防御率"].map(lambda x: f"{x:.2f}")
                st.dataframe(disp_p, use_container_width=True, hide_index=True, column_config={
                    "順位": st.column_config.TextColumn("順位", help="ランキング順位")
                })
            else: st.info("データなし")

        with st_fld:
            if not df_p_tg.empty and "処理野手" in df_p_tg.columns and "守備位置" in df_p_tg.columns:
                fld_base = df_p_tg.copy().reset_index(drop=True)
                fld_base["Original_Idx"] = fld_base.index 

                fld_data = fld_base[fld_base["処理野手"].notna() & (fld_base["処理野手"] != "")].copy()
                
                if not fld_data.empty:
                    fld_data["処理野手"] = fld_data["処理野手"].astype(str)
                    fld_data["守備位置"] = fld_data["守備位置"].astype(str)

                    fld_data["zipped"] = fld_data.apply(
                        lambda x: list(dict.fromkeys(zip(str(x["処理野手"]).split("-"), str(x["守備位置"]).split("-")))), 
                        axis=1
                    )
                    
                    fld_expanded = fld_data.explode("zipped").reset_index(drop=True)
                    if not fld_expanded.empty:
                        fld_expanded[["FielderName", "FielderPos"]] = pd.DataFrame(fld_expanded["zipped"].tolist(), index=fld_expanded.index)
                    else:
                        fld_expanded["FielderName"] = ""
                        fld_expanded["FielderPos"] = ""

                    fld_expanded["is_error"] = fld_expanded["結果"].astype(str).str.contains("失策|暴投|捕逸", na=False)

                    group_keys = ["Original_Idx", "FielderName", "FielderPos"]

                    fld_unique = fld_expanded.groupby(group_keys).agg(
                        is_error=("is_error", "max")
                    ).reset_index()

                    stats_f = fld_unique.groupby(["FielderName", "FielderPos"]).agg(
                        守備機会=("FielderName", "count"),
                        失策数=("is_error", "sum")
                    ).reset_index()
                    
                    stats_f["守備率"] = stats_f.apply(
                        lambda x: (x["守備機会"] - x["失策数"]) / x["守備機会"] if x["守備機会"] > 0 else 0.0, 
                        axis=1
                    )
                    
                    pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                    stats_f["SortKey"] = stats_f["FielderPos"].apply(
                        lambda x: pos_order.index(x) if x in pos_order else 99
                    )
                    stats_f = stats_f.sort_values(["SortKey", "守備機会"], ascending=[True, False]).reset_index(drop=True)
                    
                    disp_df = stats_f[["FielderPos", "FielderName", "守備機会", "失策数", "守備率"]].copy()
                    disp_df.columns = ["守備位置", "選手名", "守備機会", "失策", "守備率"]
                    disp_df["守備率"] = disp_df["守備率"].map(lambda x: f"{x:.3f}")
                    disp_df = disp_df[disp_df["選手名"] != ""].reset_index(drop=True)
                    
                    disp_df.insert(0, "順位", range(1, len(disp_df) + 1))
                    
                    st.dataframe(disp_df, use_container_width=True, hide_index=True, column_config={
                        "順位": st.column_config.TextColumn("順位", help="ランキング順位")
                    })
                else:
                    st.info("守備記録なし")
            else:
                st.info("データなし")

        with st_game:
            if not df_batting.empty or not df_pitching.empty:
                df_b_target = df_batting[df_batting["Year"] == target_year] if target_year != "通算" else df_batting
                df_p_target = df_pitching[df_pitching["Year"] == target_year] if target_year != "通算" else df_pitching

                df_all_logs = pd.concat([df_b_target, df_p_target], ignore_index=True)

                if not df_all_logs.empty:
                    for col in ["日付", "試合種別", "選手名"]:
                        if col in df_all_logs.columns:
                            df_all_logs[col] = df_all_logs[col].fillna("").astype(str).str.strip()
                    if "対戦相手" in df_all_logs.columns:
                        df_all_logs["対戦相手"] = df_all_logs["対戦相手"].fillna("").astype(str).str.strip()
                    else:
                        df_all_logs["対戦相手"] = ""

                    df_all_logs["Game_ID"] = df_all_logs["日付"] + "_" + df_all_logs["対戦相手"] + "_" + df_all_logs["試合種別"]

                    team_games = df_all_logs[["Game_ID", "試合種別"]].drop_duplicates()
                    
                    official_games = len(team_games[team_games["試合種別"].isin(OFFICIAL_GAME_TYPES)])
                    practice_games = len(team_games[team_games["試合種別"] == "練習試合"])
                    other_games = len(team_games[~team_games["試合種別"].isin(OFFICIAL_GAME_TYPES) & (team_games["試合種別"] != "練習試合")])
                    
                    total_games = official_games + practice_games + other_games

                    df_personal_logs = df_all_logs[df_all_logs["選手名"] != "チーム記録"].copy()
                    df_personal_logs["_match_name"] = df_personal_logs["選手名"].apply(normalize_name)
                    df_valid_players = df_personal_logs[~df_personal_logs["_match_name"].isin(clean_hidden_list)].copy()

                    if not df_valid_players.empty:
                        # 🌟 日付型への変換と最新活動日の特定
                        df_valid_players["Date_dt"] = pd.to_datetime(df_valid_players["日付"], errors='coerce')
                        df_all_logs["Date_dt"] = pd.to_datetime(df_all_logs["日付"], errors='coerce')
                        
                        latest_game_date = df_all_logs["Date_dt"].max()
                        ref_date = latest_game_date if pd.notna(latest_game_date) else pd.to_datetime(datetime.date.today())
                        
                        # 直近1年間（365日以内）の境界日
                        one_year_ago = ref_date - pd.Timedelta(days=365)

                        df_off = df_valid_players[df_valid_players["試合種別"].isin(OFFICIAL_GAME_TYPES)]
                        df_prac = df_valid_players[df_valid_players["試合種別"] == "練習試合"]
                        df_other = df_valid_players[~df_valid_players["試合種別"].isin(OFFICIAL_GAME_TYPES) & (df_valid_players["試合種別"] != "練習試合")]

                        off_counts = df_off.groupby("選手名")["Game_ID"].nunique().reset_index(name="公式戦参加数")
                        prac_counts = df_prac.groupby("選手名")["Game_ID"].nunique().reset_index(name="練習試合参加数")
                        other_counts = df_other.groupby("選手名")["Game_ID"].nunique().reset_index(name="その他参加数")
                        
                        # 🌟 直近1年参加数と最終参加日の集計
                        df_1y = df_valid_players[df_valid_players["Date_dt"] >= one_year_ago]
                        counts_1y = df_1y.groupby("選手名")["Game_ID"].nunique().reset_index(name="直近1年参加数")
                        last_dates = df_valid_players.groupby("選手名")["Date_dt"].max().reset_index(name="最終参加日")

                        base_players = df_valid_players[["選手名"]].drop_duplicates()

                        game_stats = base_players.merge(off_counts, on="選手名", how="left") \
                                                 .merge(prac_counts, on="選手名", how="left") \
                                                 .merge(other_counts, on="選手名", how="left") \
                                                 .merge(counts_1y, on="選手名", how="left") \
                                                 .merge(last_dates, on="選手名", how="left")
                        
                        # 数値カラムの欠損値を0補完
                        game_stats = game_stats.fillna({
                            "公式戦参加数": 0, "練習試合参加数": 0, "その他参加数": 0, "直近1年参加数": 0
                        })

                        game_stats["全試合参加数"] = game_stats["公式戦参加数"] + game_stats["練習試合参加数"] + game_stats["その他参加数"]
                        game_stats = game_stats[game_stats["全試合参加数"] > 0]

                        if not game_stats.empty:
                            game_stats["公式戦参加率"] = game_stats["公式戦参加数"] / official_games if official_games > 0 else 0
                            game_stats["練習試合参加率"] = game_stats["練習試合参加数"] / practice_games if practice_games > 0 else 0
                            game_stats["その他参加率"] = game_stats["その他参加数"] / other_games if other_games > 0 else 0
                            game_stats["全体参加率"] = game_stats["全試合参加数"] / total_games if total_games > 0 else 0

                            # 🌟 活動未参加期間の計算とフォーマット生成
                            def format_inactive_period(last_d):
                                if pd.isna(last_d):
                                    return "-"
                                days = (ref_date - last_d).days
                                if days <= 0:
                                    return "直近参加"
                                elif days < 30:
                                    return f"{days}日"
                                elif days < 365:
                                    months = days // 30
                                    return f"{months}ヶ月 ({days}日)"
                                else:
                                    years = days // 365
                                    months = (days % 365) // 30
                                    return f"{years}年{months}ヶ月 ({days}日)"

                            game_stats["活動未参加期間"] = game_stats["最終参加日"].apply(format_inactive_period)

                            for c in ["全試合参加数", "公式戦参加数", "練習試合参加数", "その他参加数", "直近1年参加数"]:
                                game_stats[c] = game_stats[c].astype(int)

                            game_stats["公式戦参加率"] = (game_stats["公式戦参加率"] * 100).map("{:.1f}%".format)
                            game_stats["練習試合参加率"] = (game_stats["練習試合参加率"] * 100).map("{:.1f}%".format)
                            game_stats["その他参加率"] = (game_stats["その他参加率"] * 100).map("{:.1f}%".format)
                            game_stats["全体参加率"] = (game_stats["全体参加率"] * 100).map("{:.1f}%".format)

                            game_stats = game_stats.sort_values(by=["全試合参加数", "公式戦参加数"], ascending=[False, False]).reset_index(drop=True)
                            
                            # 🌟 表示テーブルに「直近1年参加数」と「活動未参加期間」を配置
                            disp_game = game_stats[[
                                "選手名", "全試合参加数", "全体参加率", "公式戦参加数", "公式戦参加率",
                                 "練習試合参加数", "練習試合参加率", "その他参加数", "その他参加率", "直近1年参加数", "活動未参加期間"
                            ]]
                            disp_game = disp_game.rename(columns={"その他参加数": "その他(リーグ等)数", "その他参加率": "その他参加率"})
                            
                            disp_game.insert(0, "順位", range(1, len(disp_game) + 1))

                            st.markdown(f"**対象期間のチーム総試合数**: 全 {total_games} 試合 (公式戦: {official_games} / 練習試合: {practice_games} / その他: {other_games})")
                            st.caption("※ チームの全試合（公式戦・練習試合・その他リーグ戦等）を合算・分類して表示しています。活動未参加期間はチーム最終試合日からの経過期間です。")
                            st.dataframe(disp_game, use_container_width=True, hide_index=True, column_config={
                                "順位": st.column_config.TextColumn("順位", help="ランキング順位"),
                                "直近1年参加数": st.column_config.NumberColumn("直近1年参加数", help="過去1年間（365日以内）に参加した試合数"),
                                "活動未参加期間": st.column_config.TextColumn("活動未参加期間", help="チームの最新活動日からの未参加経過期間"),
                            })
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
        sel_player = st.selectbox("選手選択", ALL_PLAYERS)
        if sel_player:
            if not df_b_calc.empty:
                my_b = df_b_calc[df_b_calc["選手名"] == sel_player]
                if not my_b.empty:
                    hist = my_b.groupby("Year").agg(agg_rules_b).sort_index(ascending=False)
                    total_s = my_b.agg(agg_rules_b)
                    hist_total = pd.DataFrame(total_s).T
                    hist_total.index = ["通算"]

                    combined_hist = pd.concat([hist_total, hist])

                    combined_hist["PA"] = combined_hist["is_ab"] + combined_hist["is_bb"] + combined_hist["is_sf"]
                    combined_hist["打率"] = combined_hist.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
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
                    disp_hist["三振率"] = combined_hist["三振率"] 
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
                else: st.info("データなし")
        
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
                    lambda x: (x["自責点"]*7)/x["Innings"] if x["Innings"]>0 else 0, axis=1
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
                combined_p["回"] = combined_p["アウト数"].apply(lambda x: f"{int(x//3)}.{int(x%3)}")
                
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
            else: st.info("データなし")
        
        if not df_p_calc.empty and "処理野手" in df_p_calc.columns and "守備位置" in df_p_calc.columns:
            fld_base_all = df_p_calc.copy().reset_index(drop=True)
            
            if "Year" not in fld_base_all.columns:
                fld_base_all["Year"] = pd.to_datetime(fld_base_all["日付"], errors='coerce').dt.strftime('%Y').fillna("不明")
                
            fld_base_all["Original_Idx"] = fld_base_all.index
            
            fld_base = fld_base_all[fld_base_all["処理野手"].notna() & (fld_base_all["処理野手"] != "")].copy()
            
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

                            group_keys = ["Original_Idx", "FielderName", "FielderPos"]

                            fld_unique = my_f.groupby(group_keys).agg(
                                Year=("Year", "first"),
                                is_error=("is_error", "max")
                            ).reset_index()

                            hist_f = fld_unique.groupby("Year").agg(
                                守備機会=("FielderName", "count"),
                                失策数=("is_error", "sum")
                            ).sort_index(ascending=False)
                            
                            total_f_opp = fld_unique["FielderName"].count()
                            total_f_err = fld_unique["is_error"].sum()
                            hist_f_total = pd.DataFrame({
                                "守備機会": [total_f_opp],
                                "失策数": [total_f_err]
                            }, index=["通算"])
                            
                            combined_f = pd.concat([hist_f_total, hist_f])
                            
                            combined_f["守備率"] = combined_f.apply(
                                lambda x: (x["守備機会"] - x["失策数"]) / x["守備機会"] if x["守備機会"] > 0 else 0.0, 
                                axis=1
                            )
                            
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
    # 3. ランキング
    # ----------------------------------------------------
    with t_rank:
        st.markdown("#### 🏆 期間別ランキング")
        period = st.radio("集計期間", ["年度別", "月間", "直近3試合"], horizontal=True)
        df_b_sub = df_b_calc.copy(); df_p_sub = df_p_calc.copy()
        df_b_sub["Date"] = pd.to_datetime(df_b_sub["日付"]); df_p_sub["Date"] = pd.to_datetime(df_p_sub["日付"])
        
        def_ab = 1; def_inn = 1
        key_suffix = ""

        if period == "年度別":
            ys = sorted(df_b_sub["Date"].dt.year.unique(), reverse=True)
            sy = st.selectbox("年度選択", ys) if len(ys)>0 else datetime.date.today().year
            key_suffix = str(sy) 

            df_b_sub = df_b_sub[df_b_sub["Date"].dt.year == sy]
            df_p_sub = df_p_sub[df_p_sub["Date"].dt.year == sy]
            if not df_b_sub.empty: def_ab = int(df_b_sub["日付"].nunique() * 1.0); def_inn = int(df_b_sub["日付"].nunique() * 0.8)
        
        elif period == "月間":
            df_b_sub["YM"] = df_b_sub["Date"].dt.strftime('%Y-%m')
            ms = sorted(df_b_sub["YM"].unique(), reverse=True)
            sm = st.selectbox("月選択", ms) if len(ms)>0 else None
            
            if sm:
                key_suffix = str(sm)
                df_b_sub = df_b_sub[df_b_sub["YM"] == sm]
                df_p_sub["YM"] = df_p_sub["Date"].dt.strftime('%Y-%m')
                df_p_sub = df_p_sub[df_p_sub["YM"] == sm]
                def_ab = int(df_b_sub["日付"].nunique()); def_inn = def_ab
            else: df_b_sub = pd.DataFrame(); df_p_sub = pd.DataFrame()
        
        else:
            dates = sorted(df_b_sub["Date"].unique(), reverse=True)[:3]
            df_b_sub = df_b_sub[df_b_sub["Date"].isin(dates)]; df_p_sub = df_p_sub[df_p_sub["Date"].isin(dates)]
            def_ab = 3; def_inn = 3
            key_suffix = "recent"

        c_f1, c_f2 = st.columns(2)
        min_ab = c_f1.number_input("規定打席", value=max(1, def_ab), min_value=1, key=f"ab_{period}_{key_suffix}")
        min_inn = c_f2.number_input("規定投球回", value=max(1, def_inn), min_value=1, key=f"inn_{period}_{key_suffix}")
        
        st.divider()

        if not df_b_sub.empty:
            rank_b = get_ranking_df(df_b_sub, ["選手名"], agg_rules_b)
            rank_b["Total_PA"] = rank_b["is_ab"] + rank_b["is_bb"] 
            rank_b["AVG"] = rank_b.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
            rank_b["OBP"] = (rank_b["is_hit"] + rank_b["is_bb"]) / (rank_b["is_ab"] + rank_b["is_bb"] + rank_b["is_sf"])
            rank_b["SLG"] = rank_b["bases"] / rank_b["is_ab"]
            rank_b["OPS"] = (rank_b["OBP"] + rank_b["SLG"]).fillna(0)
            
            st.markdown("##### ⚔️ 打撃部門")
            r1, r2, r3 = st.columns(3)
            with r1: show_top5("打率", rank_b[rank_b["Total_PA"]>=min_ab], "AVG", "選手名", "AVG", format_float=True)
            with r2: show_top5("本塁打", rank_b, "is_hr", "選手名", "is_hr", suffix="本")
            with r3: show_top5("打点", rank_b, "打点", "選手名", "打点", suffix="点")
            
            st.write("")
            r4, r5, r6 = st.columns(3)
            with r4: show_top5("安打", rank_b, "is_hit", "選手名", "is_hit", suffix="本")
            with r5: show_top5("盗塁", rank_b, "盗塁", "選手名", "盗塁", suffix="個")
            with r6: show_top5("OPS", rank_b[rank_b["is_ab"]>=min_ab], "OPS", "選手名", "OPS", format_float=True)
        else: st.info("データなし")
        st.divider()

        if not df_p_sub.empty:
            rank_p = get_ranking_df(df_p_sub, ["選手名"], agg_rules_p)
            rank_p["Innings"] = rank_p["アウト数"]/3
            rank_p["ERA"] = rank_p.apply(lambda x: (x["自責点"]*7)/x["Innings"] if x["Innings"]>0 else 99.99, axis=1)
            rank_p["TotalSO"] = rank_p["is_so"] + rank_p["奪三振"]
            rank_p["WHIP"] = rank_p.apply(lambda x: (x["total_bb"]+x["被安打"])/x["Innings"] if x["Innings"]>0 else 99.99, axis=1)

            st.markdown("##### 🛡️ 投手部門")
            st.caption("※ WHIP: (被安打 + 与四死球) ÷ 投球回。1イニングあたりに出した走者の数。")
            p1, p2, p3, p4 = st.columns(4)
            with p1: show_top5("防御率", rank_p[rank_p["Innings"]>=min_inn], "ERA", "選手名", "ERA", ascending=True, format_float=True)
            with p2: show_top5("WHIP", rank_p[rank_p["Innings"]>=min_inn], "WHIP", "選手名", "WHIP", ascending=True, format_float=True)
            with p3: show_top5("勝利", rank_p, "is_win", "選手名", "is_win", suffix="勝")
            with p4: show_top5("奪三振", rank_p, "TotalSO", "選手名", "TotalSO", suffix="個")
        else: st.info("データなし")

    # ----------------------------------------------------
    # 4. 歴代記録
    # ----------------------------------------------------
    with t_rec:
        st.markdown("#### 👑 歴代記録")
        rc1, rc2 = st.columns([1, 2])
        rec_mode = rc1.radio("対象", ["シーズン最高", "生涯通算"], horizontal=True)
        
        FIXED_EXCLUDE_LIST = HIDDEN_PLAYERS_TOTAL

        def normalize_name_for_rec(text):
            if not isinstance(text, str) or not text:
                return ""
            text = unicodedata.normalize('NFKC', text)
            return text.strip().replace(" ", "").replace(" ", "").replace("さん", "")

        clean_exclude_list = [normalize_name_for_rec(n) for n in FIXED_EXCLUDE_LIST]

        df_b_target = df_b_calc.copy()
        df_p_target = df_p_calc.copy()

        if not df_b_target.empty and clean_exclude_list:
            df_b_target["_match_name"] = df_b_target["選手名"].apply(normalize_name_for_rec)
            df_b_target = df_b_target[~df_b_target["_match_name"].isin(clean_exclude_list)]
            df_b_target = df_b_target.drop(columns=["_match_name"])

        if not df_p_target.empty and clean_exclude_list:
            df_p_target["_match_name"] = df_p_target["選手名"].apply(normalize_name_for_rec)
            df_p_target = df_p_target[~df_p_target["_match_name"].isin(clean_exclude_list)]
            df_p_target = df_p_target.drop(columns=["_match_name"])

        if not df_b_target.empty:
            df_b_target["Date"] = pd.to_datetime(df_b_target["日付"])
            df_b_target["Year"] = df_b_target["Date"].dt.year.astype(str)
        
        if not df_p_target.empty:
            df_p_target["Date"] = pd.to_datetime(df_p_target["日付"])
            df_p_target["Year"] = df_p_target["Date"].dt.year.astype(str)

        if "シーズン" in rec_mode:
            COEFF_AB  = 1.0
            COEFF_INN = 0.8
            MIN_AB  = 10
            MIN_INN = 10

            games_by_year_b = df_b_target.groupby("Year")["日付"].nunique().to_dict()
            games_by_year_p = df_p_target.groupby("Year")["日付"].nunique().to_dict()

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
            MIN_AB_LIFETIME = 20
            MIN_INN_LIFETIME = 15

            df_bat_res = get_ranking_df(df_b_target, ["選手名"], agg_rules_b)
            df_bat_res["Display"] = df_bat_res["選手名"]
            df_bat_rate_target = df_bat_res[df_bat_res["is_ab"] >= MIN_AB_LIFETIME].copy()
            
            df_pit_res = get_ranking_df(df_p_target, ["選手名"], agg_rules_p)
            df_pit_res["Display"] = df_pit_res["選手名"]
            df_pit_res["Innings"] = df_pit_res["アウト数"]/3
            df_pit_rate_target = df_pit_res[df_pit_res["Innings"] >= MIN_INN_LIFETIME].copy()

        if not df_bat_res.empty:
            for df in [df_bat_res, df_bat_rate_target]:
                if df.empty: continue
                df["AVG"] = df.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
                obp = (df["is_hit"] + df["is_bb"]) / (df["is_ab"] + df["is_bb"] + df["is_sf"] + 1e-9)
                slg = df["bases"] / (df["is_ab"] + 1e-9)
                df["OPS"] = obp + slg

        if not df_pit_res.empty:
            for df in [df_pit_res, df_pit_rate_target]:
                if df.empty: continue
                df["ERA"] = df.apply(lambda x: (x["自責点"]*7)/x["Innings"] if x["Innings"]>0 else 99.99, axis=1)
                df["TotalSO"] = df["is_so"] + df["奪三振"]
                df["WHIP"] = df.apply(lambda x: (x["total_bb"]+x["被安打"])/x["Innings"] if x["Innings"]>0 else 99.99, axis=1)

        st.divider()

        if not df_bat_res.empty:
            st.markdown(f"##### ⚔️ 歴代打撃トップ5")
            tc1, tc2, tc3 = st.columns(3)
            with tc1: show_top5("打率", df_bat_rate_target, "AVG", "Display", "AVG", suffix="", format_float=True)
            with tc2: show_top5("OPS", df_bat_rate_target, "OPS", "Display", "OPS", suffix="", format_float=True)
            with tc3: show_top5("安打数", df_bat_res, "is_hit", "Display", "is_hit", suffix=" 本")
            
            st.write("")
            tc4, tc5, tc6 = st.columns(3)
            with tc4: show_top5("本塁打", df_bat_res, "is_hr", "Display", "is_hr", suffix=" 本")
            with tc5: show_top5("打点", df_bat_res, "打点", "Display", "打点", suffix=" 点")
            with tc6: show_top5("盗塁", df_bat_res, "盗塁", "Display", "盗塁", suffix=" 個")
        else:
            st.info("打撃データがありません")
        
        st.divider()

        if not df_pit_res.empty:
            if "Display" in df_pit_res.columns:
                df_pit_res["Display"] = df_pit_res["Display"].astype(str).str.replace(r'\.0\)', ')', regex=True)
            if "Display" in df_pit_rate_target.columns:
                df_pit_rate_target["Display"] = df_pit_rate_target["Display"].astype(str).str.replace(r'\.0\)', ')', regex=True)

            st.markdown(f"##### 🛡️ 歴代投手トップ5")
            tp1, tp2, tp3, tp4 = st.columns(4)
            with tp1: show_top5("防御率", df_pit_rate_target, "ERA", "Display", "ERA", ascending=True, suffix="", format_float=True)
            with tp2: show_top5("WHIP", df_pit_rate_target, "WHIP", "Display", "WHIP", ascending=True, suffix="", format_float=True)
            with tp3: show_top5("勝利数", df_pit_res, "is_win", "Display", "is_win", suffix=" 勝")
            with tp4: show_top5("奪三振", df_pit_res, "TotalSO", "Display", "TotalSO", suffix=" 個")
        else:
            st.info("投手データがありません")

    # ----------------------------------------------------
    # 5. 総合貢献度・高度指標 (RC、投手・守備・試合を含めた総合MVP ＆ 捕手補正付き)
    # ----------------------------------------------------
    with t_saber:
        st.markdown("#### 📈 総合貢献度・セイバーメトリクス指標")
        st.caption("※ 打撃・投手・守備・試合参加数を総合的に評価したチーム貢献度ランキングです。年度ごとに切り替えて確認できます。")

        if not df_batting.empty or not df_pitching.empty:
            # --- 年度リストの取得 ---
            years_bat_saber = set(df_batting["Year"].dropna().astype(str).unique()) if (df_batting is not None and not df_batting.empty and "Year" in df_batting.columns) else set()
            years_pit_saber = set(df_pitching["Year"].dropna().astype(str).unique()) if (df_pitching is not None and not df_pitching.empty and "Year" in df_pitching.columns) else set()
            saber_years = sorted(list(years_bat_saber | years_pit_saber), reverse=True)

            # 年度切り替えセレクトボックス
            c_y1, c_y2 = st.columns([1, 2])
            target_saber_year = c_y1.selectbox("集計年度選択", ["通算"] + saber_years, key="saber_year_selectbox")

            # データの絞り込み（通算 or 選択年度）
            df_b_target = df_b_calc.copy()
            df_p_target = df_p_calc.copy()
            if target_saber_year != "通算":
                if not df_b_target.empty and "Year" in df_b_target.columns:
                    df_b_target = df_b_target[df_b_target["Year"] == target_saber_year]
                if not df_p_target.empty and "Year" in df_p_target.columns:
                    df_p_target = df_p_target[df_p_target["Year"] == target_saber_year]

            # 1. 選手ごとの打撃スタッツを集計
            saber_stats_b = pd.DataFrame()
            if not df_b_target.empty:
                df_b_saber = df_b_target.copy()
                df_b_saber["_match_name"] = df_b_saber["選手名"].apply(normalize_name)
                df_b_saber = df_b_saber[~df_b_saber["_match_name"].isin(clean_hidden_list)]
                if not df_b_saber.empty:
                    saber_stats_b = df_b_saber.groupby("選手名").agg(agg_rules_b).reset_index()
                    saber_stats_b["PA"] = saber_stats_b["is_ab"] + saber_stats_b["is_bb"] + saber_stats_b["is_sf"]
                    saber_stats_b["打率"] = saber_stats_b.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
                    saber_stats_b["出塁率"] = saber_stats_b.apply(lambda x: (x["is_hit"] + x["is_bb"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
                    saber_stats_b["TotalBases"] = saber_stats_b["is_1b"] + (saber_stats_b["is_2b"] * 2) + (saber_stats_b["is_3b"] * 3) + (saber_stats_b["is_hr"] * 4)
                    saber_stats_b["長打率"] = (saber_stats_b["TotalBases"] / saber_stats_b["is_ab"]).fillna(0)
                    saber_stats_b["OPS"] = saber_stats_b["出塁率"] + saber_stats_b["長打率"]

                    # RC (得点創出)
                    saber_stats_b["RC"] = saber_stats_b.apply(
                        lambda x: ((x["is_hit"] + x["is_bb"]) * x["TotalBases"]) / (x["is_ab"] + x["is_bb"])
                        if (x["is_ab"] + x["is_bb"]) > 0 else 0, axis=1
                    )

            # 2. 選手ごとの投手スタッツを集計
            saber_stats_p = pd.DataFrame()
            if not df_p_target.empty:
                df_p_saber = df_p_target.copy()
                df_p_saber["_match_name"] = df_p_saber["選手名"].apply(normalize_name)
                df_p_saber = df_p_saber[~df_p_saber["_match_name"].isin(clean_hidden_list)]
                if not df_p_saber.empty:
                    saber_stats_p = df_p_saber.groupby("選手名").agg(agg_rules_p).reset_index()
                    saber_stats_p["投球回"] = saber_stats_p["アウト数"] / 3
                    saber_stats_p["投手_勝利"] = saber_stats_p["is_win"]
                    saber_stats_p["投手_防御率"] = saber_stats_p.apply(lambda x: (x["自責点"] * 7) / x["投球回"] if x["投球回"] > 0 else 99.0, axis=1)
                    saber_stats_p["投手_奪三振"] = saber_stats_p["is_so"] + saber_stats_p["奪三振"]

            # 3. 選手ごとの守備スタッツを集計（捕手守備機会の別枠集計を追加）
            saber_stats_f = pd.DataFrame()
            if not df_p_target.empty and "処理野手" in df_p_target.columns and "守備位置" in df_p_target.columns:
                fld_base = df_p_target.copy().reset_index(drop=True)
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
                        fld_expanded["_match_name"] = fld_expanded["FielderName"].apply(normalize_name)
                        fld_expanded = fld_expanded[~fld_expanded["_match_name"].isin(clean_hidden_list)]
                        
                        fld_expanded["is_error"] = fld_expanded["Result" if "Result" in fld_expanded.columns else "結果"].astype(str).str.contains("失策|暴投|捕逸", na=False)
                        
                        group_keys = ["Original_Idx", "FielderName", "FielderPos"]

                        fld_unique = fld_expanded.groupby(group_keys).agg(
                            is_error=("is_error", "max")
                        ).reset_index()
                        
                        stats_f_agg = fld_unique.groupby("FielderName").agg(
                            守備機会=("FielderName", "count"),
                            失策数=("is_error", "sum"),
                            捕手守備機会=("FielderPos", lambda x: (x == "捕").sum())
                        ).reset_index()
                        stats_f_agg["守備率"] = stats_f_agg.apply(lambda x: (x["守備機会"] - x["失策数"]) / x["守備機会"] if x["守備機会"] > 0 else 1.0, axis=1)
                        saber_stats_f = stats_f_agg.rename(columns={"FielderName": "選手名"})

            # 4. 選手ごとの試合参加数を集計
            saber_stats_g = pd.DataFrame()
            df_all_logs = pd.concat([df_b_target, df_p_target], ignore_index=True) if not df_b_target.empty or not df_p_target.empty else pd.DataFrame()
            if not df_all_logs.empty:
                for col in ["日付", "試合種別", "選手名"]:
                    if col in df_all_logs.columns:
                        df_all_logs[col] = df_all_logs[col].fillna("").astype(str).str.strip()
                if "対戦相手" in df_all_logs.columns:
                    df_all_logs["対戦相手"] = df_all_logs["対戦相手"].fillna("").astype(str).str.strip()
                else:
                    df_all_logs["対戦相手"] = ""

                df_all_logs = df_all_logs[df_all_logs["選手名"] != "チーム記録"]
                df_all_logs["Game_ID"] = df_all_logs["日付"] + "_" + df_all_logs["対戦相手"] + "_" + df_all_logs["試合種別"]
                df_all_logs["_match_name"] = df_all_logs["選手名"].apply(normalize_name)
                df_valid_games = df_all_logs[~df_all_logs["_match_name"].isin(clean_hidden_list)]
                
                if not df_valid_games.empty:
                    game_counts = df_valid_games.groupby("選手名")["Game_ID"].nunique().reset_index(name="試合参加数")
                    saber_stats_g = game_counts

            # 5. すべてのデータを「選手名」でマージ
            all_players_list = []
            for df_sub in [saber_stats_b, saber_stats_p, saber_stats_f, saber_stats_g]:
                if df_sub is not None and not df_sub.empty and "選手名" in df_sub.columns:
                    all_players_list.append(df_sub[["選手名"]])
            
            if all_players_list:
                master_players = pd.concat(all_players_list).drop_duplicates().reset_index(drop=True)
                
                merged_saber = master_players.copy()
                if not saber_stats_b.empty: merged_saber = merged_saber.merge(saber_stats_b, on="選手名", how="left")
                if not saber_stats_p.empty: merged_saber = merged_saber.merge(saber_stats_p, on="選手名", how="left")
                if not saber_stats_f.empty: merged_saber = merged_saber.merge(saber_stats_f, on="選手名", how="left")
                if not saber_stats_g.empty: merged_saber = merged_saber.merge(saber_stats_g, on="選手名", how="left")

                fill_zeros = ["is_ab", "is_hit", "is_hr", "is_bb", "打点", "盗塁", "盗塁死", "RC", "OPS", "打率", 
                              "投球回", "投手_勝利", "投手_奪三振", "守備機会", "失策数", "捕手守備機会", "試合参加数"]
                for c in fill_zeros:
                    if c in merged_saber.columns:
                        merged_saber[c] = merged_saber[c].fillna(0)
                
                if "守備率" in merged_saber.columns:
                    merged_saber["守備率"] = merged_saber["守備率"].fillna(1.0)
                if "投手_防御率" in merged_saber.columns:
                    merged_saber["投手_防御率"] = merged_saber["投手_防御率"].fillna(99.0)

                # ==========================================
                # 6. 部門別貢献度 ＆ 総合MVPスコアの算出（バランス調整＆投手純粋評価版）
                # ==========================================
                def calc_batting_score(row):
                    return (row.get("OPS", 0) * 50.0) + (row.get("RC", 0) * 3.0) + (row.get("盗塁", 0) * 1.0)

                def calc_pitching_score(row):
                    p_inn = row.get("投球回", 0)
                    p_era = row.get("投手_防御率", 99.0)
                    p_so = row.get("投手_奪三振", 0)
                    
                    if p_inn <= 0 or p_era >= 90:
                        return 0.0
                    
                    inn_pts = p_inn * 1.0
                    so_pts = p_so * 0.3
                    
                    if p_era <= 3.50:
                        era_pts = (3.50 - p_era) * p_inn * 0.5
                    else:
                        era_pts = (3.50 - p_era) * p_inn * 0.2
                    
                    total_score = inn_pts + so_pts + era_pts
                    return max(0.0, total_score)

                def calc_defense_score(row):
                    f_opp = row.get("守備機会", 0)
                    f_err = row.get("失策数", 0)
                    f_pct = row.get("守備率", 1.0)
                    catcher_opp = row.get("捕手守備機会", 0)
                    
                    non_catcher_opp = max(0, f_opp - catcher_opp)
                    defense_pts = (non_catcher_opp * 1.0 + catcher_opp * 2.5) * f_pct - (f_err * 2.0)
                    return max(0.0, defense_pts)

                merged_saber["Batting_Score"] = merged_saber.apply(calc_batting_score, axis=1)
                merged_saber["Pitching_Score"] = merged_saber.apply(calc_pitching_score, axis=1)
                merged_saber["Defense_Score"] = merged_saber.apply(calc_defense_score, axis=1)
                merged_saber["Game_Score"] = merged_saber.get("試合参加数", 0) * 1.0

                # チーム全体で守備機会を持つ人が一人でもいるか判定
                has_defense_data = merged_saber["守備機会"].sum() > 0 if "守備機会" in merged_saber.columns else False

                # 総合MVPスコア（守備機会がある年は守備点を含め、ない年は除外する）
                if has_defense_data:
                    merged_saber["MVP_Score"] = (
                        merged_saber["Batting_Score"] + 
                        merged_saber["Pitching_Score"] + 
                        merged_saber["Defense_Score"] + 
                        merged_saber["Game_Score"]
                    )
                else:
                    merged_saber["MVP_Score"] = (
                        merged_saber["Batting_Score"] + 
                        merged_saber["Pitching_Score"] + 
                        merged_saber["Game_Score"]
                    )

                # --- サブタブ（部門別の可視化） ---
                sub_tab_mvp, sub_tab_bat, sub_tab_pit, sub_tab_fld = st.tabs(["🏆 総合MVP", "⚔️ 打撃部門", "🛡️ 投手部門", "🧤 守備部門"])

                # 最低試合数スライダー（すべてデフォルト2試合に設定）
                max_games_val = int(merged_saber["試合参加数"].max()) if not merged_saber.empty else 1
                target_default = 2
                    
                default_games_val = min(target_default, max_games_val)
                
                min_games = st.slider("表示対象とする最低試合参加数", 0, max_games_val, default_games_val, key=f"saber_min_games_{target_saber_year}")
                saber_filtered = merged_saber[merged_saber["試合参加数"] >= min_games].reset_index(drop=True)

                if not saber_filtered.empty:
                    
                    # --- 1. 総合MVPタブ ---
                    with sub_tab_mvp:
                        st.markdown(f"##### 🏆 総合MVPランキング ({target_saber_year})")
                        df_mvp_sort = saber_filtered.sort_values("MVP_Score", ascending=False).reset_index(drop=True)
                        df_mvp_sort.insert(0, "順位", range(1, len(df_mvp_sort) + 1))
                        
                        if has_defense_data:
                            disp_cols = ["順位", "選手名", "MVP_Score", "試合参加数", "Batting_Score", "Pitching_Score", "Defense_Score", "RC", "OPS", "投手_勝利", "投球回", "守備率"]
                            col_names = ["順位", "選手名", "総合貢献度点数", "試合数", "打撃P", "投手P", "守備P", "RC", "OPS", "勝利", "投球回", "守備率"]
                        else:
                            disp_cols = ["順位", "選手名", "MVP_Score", "試合参加数", "Batting_Score", "Pitching_Score", "RC", "OPS", "投手_勝利", "投球回"]
                            col_names = ["順位", "選手名", "総合貢献度点数", "試合数", "打撃P", "投手P", "RC", "OPS", "勝利", "投球回"]
                            st.info("💡 ※この年度（または期間）は守備機会の記録がないため、打撃・投手・試合指標のみで総合MVPを算出しています。")

                        disp_mvp = df_mvp_sort[disp_cols].copy()
                        disp_mvp.columns = col_names
                        
                        disp_mvp["総合貢献度点数"] = disp_mvp["総合貢献度点数"].map(lambda x: f"{x:.1f}")
                        disp_mvp["打撃P"] = disp_mvp["打撃P"].map(lambda x: f"{x:.1f}")
                        disp_mvp["投手P"] = disp_mvp["投手P"].map(lambda x: f"{x:.1f}")
                        if has_defense_data:
                            disp_mvp["守備P"] = disp_mvp["守備P"].map(lambda x: f"{x:.1f}")
                            disp_mvp["守備率"] = disp_mvp["守備率"].map(lambda x: f"{x:.3f}")
                        disp_mvp["RC"] = disp_mvp["RC"].map(lambda x: f"{x:.2f}")
                        disp_mvp["OPS"] = disp_mvp["OPS"].map(lambda x: f"{x:.3f}")
                        disp_mvp["投球回"] = disp_mvp["投球回"].map(lambda x: f"{x:.1f}")

                        column_config_dict = {
                            "順位": st.column_config.TextColumn("順位", help="ランキング順位"),
                            "総合貢献度点数": st.column_config.TextColumn("総合貢献度点数", help="打撃・投手・守備・試合参加の全貢献度を合算した総合得点です。"),
                            "打撃P": st.column_config.TextColumn("打撃P", help="打撃による獲得ポイント（OPS/RC等）"),
                            "投手P": st.column_config.TextColumn("投手P", help="投手による獲得ポイント（防御率/イニング/三振）※勝利数は除外して実力を評価しています。"),
                        }
                        if has_defense_data:
                            column_config_dict["守備P"] = st.column_config.TextColumn("守備P", help="守備による獲得ポイント（守備機会×守備率。捕手は高係数補正あり）")

                        st.dataframe(disp_mvp, use_container_width=True, hide_index=True, column_config=column_config_dict)

                    # --- 2. 打撃部門タブ ---
                    with sub_tab_bat:
                        st.markdown(f"##### ⚔️ 打撃部門・貢献度ランキング ({target_saber_year})")
                        df_bat_sort = saber_filtered.sort_values("Batting_Score", ascending=False).reset_index(drop=True)
                        df_bat_sort.insert(0, "順位", range(1, len(df_bat_sort) + 1))
                        
                        disp_bat = df_bat_sort[["順位", "選手名", "Batting_Score", "RC", "OPS", "打率", "is_ab", "is_hit", "is_hr", "打点", "盗塁"]].copy()
                        disp_bat.columns = ["順位", "選手名", "打撃貢献点数", "RC (得点創出)", "OPS", "打率", "打数", "安打", "本塁打", "打点", "盗塁"]
                        
                        disp_bat["打撃貢献点数"] = disp_bat["打撃貢献点数"].map(lambda x: f"{x:.1f}")
                        disp_bat["RC (得点創出)"] = disp_bat["RC (得点創出)"].map(lambda x: f"{x:.2f}")
                        disp_bat["OPS"] = disp_bat["OPS"].map(lambda x: f"{x:.3f}")
                        disp_bat["打率"] = disp_bat["打率"].map(lambda x: f"{x:.3f}")

                        st.dataframe(disp_bat, use_container_width=True, hide_index=True)

                    # --- 3. 投手部門タブ ---
                    with sub_tab_pit:
                        st.markdown(f"##### 🛡️ 投手部門・貢献度ランキング ({target_saber_year})")
                        df_pit_sort = saber_filtered.sort_values("Pitching_Score", ascending=False).reset_index(drop=True)
                        df_pit_sort.insert(0, "順位", range(1, len(df_pit_sort) + 1))
                        
                        disp_pit = df_pit_sort[["順位", "選手名", "Pitching_Score", "投手_勝利", "投球回", "投手_防御率", "投手_奪三振"]].copy()
                        disp_pit.columns = ["順位", "選手名", "投手貢献点数", "勝利", "投球回", "防御率", "奪三振"]
                        
                        disp_pit["投手貢献点数"] = disp_pit["投手貢献点数"].map(lambda x: f"{x:.1f}")
                        disp_pit["投球回"] = disp_pit["投球回"].map(lambda x: f"{x:.1f}")
                        disp_pit["防御率"] = disp_pit["防御率"].map(lambda x: f"{x:.2f}" if x < 90 else "-")

                        st.dataframe(disp_pit, use_container_width=True, hide_index=True)

                    # --- 4. 守備部門タブ ---
                    with sub_tab_fld:
                        st.markdown(f"##### 🧤 守備部門・貢献度ランキング ({target_saber_year})")
                        
                        has_fld_players = ("守備機会" in saber_filtered.columns) and not saber_filtered[saber_filtered["守備機会"] > 0].empty
                        
                        if has_fld_players:
                            df_fld_sort = saber_filtered[saber_filtered["守備機会"] > 0].sort_values("Defense_Score", ascending=False).reset_index(drop=True)
                            df_fld_sort.insert(0, "順位", range(1, len(df_fld_sort) + 1))
                            
                            disp_fld = df_fld_sort[["順位", "選手名", "Defense_Score", "守備機会", "捕手守備機会", "失策数", "守備率"]].copy()
                            disp_fld.columns = ["順位", "選手名", "守備貢献点数", "総守備機会", "うち捕手機会", "失策", "守備率"]
                            
                            disp_fld["守備貢献点数"] = disp_fld["守備貢献点数"].map(lambda x: f"{x:.1f}")
                            disp_fld["守備率"] = disp_fld["守備率"].map(lambda x: f"{x:.3f}")

                            st.dataframe(disp_fld, use_container_width=True, hide_index=True, column_config={
                                "守備貢献点数": st.column_config.TextColumn("守備貢献点数", help="捕手守備機会には高い係数（2.5倍）を適用し、負担の大きいポジションの貢献度を高く評価しています。"),
                            })
                        else:
                            st.info("ℹ️ 該当する守備機会のある選手がいません（この年度は守備データの入力がないか、全員の守備機会が0です）。")

                    # --- 各種指標の算出式解説用エクスパンダー ---
                    with st.expander("ℹ️ 各指標の算出式と評価モデルの解説"):
                        st.markdown("""
                        ### ⚾ セイバーメトリクス・指標の解説ルーム 📊

                        #### ⚔️ 1. 打撃系指標（チームにどれだけ得点をもたらしたか！）
                        * **OPS (On-base Plus Slugging)**
                          * **算出式:** OPS = 出塁率 + 長打率
                          * **概念:** 「出塁能力 ＋ 長打力」
                          * **解説:** 打者の総合的な攻撃力を表す最もポピュラーな指標！0.8超えで優秀、1.0超えなら超スター選手です✨
                        * **RC (Runs Created / 得点創出)**
                          * **算出式:** RC = (安打 + 四球) × 塁打 ÷ (打数 + 四球)
                          * **概念:** 「出塁能力 × 進塁能力 ÷ 出塁機会」
                          * **解説:** 安打や四球、長打の組み合わせから「チームに何点分の得点を生み出したか」の総量を推計します！チーム全員のRCを足すと、チームの総得点にほぼ一致するロマンあふれる指標です🔥
                        * **打撃貢献点数 (Batting_Score)**
                          * **算出式:** Batting_Score = (OPS × 50.0) + (RC × 3.0) + (盗塁 × 1.0)
                          * **解説:** 率の高さと、実際に試合に出て稼いだ得点総量（RC）のバランスを重視したスコアです！

                        #### 🛡️ 2. 投手系指標（マウンドでの絶対的守護神！）
                        * **投手貢献点数 (Pitching_Score)**
                          * **算出式:** 
                            * 防御率が3.50以下（優秀）の場合: `投球回 + (奪三振 × 0.3) + ((3.50 - 防御率) × 投球回 × 0.5)`
                            * 防御率が3.50より悪い場合: `投球回 + (奪三振 × 0.3) + ((3.50 - 防御率) × 投球回 × 0.2)`
                          * **概念:** 「イニング消化 ＋ 球威 ＋ 防御率ボーナス(ペナルティ・係数付き)」
                          * **解説:** 基準の防御率 **3.50** に対し、良ければ **0.5倍** の係数で強力プラス！悪くても **0.2倍** の緩やかなマイナスにとどめ、長いイニングを支えたタフさをしっかり評価するエースモデルです🔥 *(※勝敗は運や打線の影響を受けるため除外)*

                        #### 🧤 3. 守備系指標（鉄壁の守り & キャッチャー補正！）
                        * **守備貢献点数 (Defense_Score)**
                          * **算出式:** Defense_Score = ((通常守備機会 × 1.0 + 捕手守備機会 × 2.5) × 守備率) - (失策数 × 2.0)
                          * **概念:** 「(通常守備 ＋ キャッチャー高補正) × 確実性 － ミス減点」
                          * **解説:** 守備機会の多さと確実性を掛け合わせ、負担の大きいキャッチャーには2.5倍の高いウェイトをかけています🛡️✨
                          *(※守備機会がある年度のみ算入されます)*

                        #### 🏆 4. 総合MVPスコア（チームの真のMVPを決定！）
                        * **算出式:** MVP_Score = Batting_Score + Pitching_Score + Defense_Score + (試合参加数 × 1.0)
                          *(※守備機会が誰もいない年は Defense_Score を除外して算出)*
                        * **解説:** 打撃・投手・守備の各貢献度に加え、チームへのコミットメント（試合参加数）をプラスした栄誉ある総合得点です🎉
                        """)
                else:
                    st.info("指定した最低試合数以上の選手がいません。スライダーの値を下げてください。")
            else:
                st.info("有効な選手データがありません。")
        else:
            st.info("成績データがありません。")