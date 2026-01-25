import streamlit as st
import pandas as pd
import datetime
from config.settings import ALL_PLAYERS, PLAYER_NUMBERS, OFFICIAL_GAME_TYPES

def show_personal_stats(df_batting, df_pitching):
    st.title(" 📊 個人成績")

    # =========================================================
    # 1. データ前処理
    # =========================================================
    
    # --- 打撃データ ---
    if not df_batting.empty:
        # 日付からYearを作成
        df_batting["Year"] = pd.to_datetime(df_batting["日付"]).dt.year.astype(str)
        df_b_calc = df_batting[df_batting["選手名"] != "チーム記録"].copy()
        
        hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
        ab_cols = hit_cols + ["凡退", "失策", "走塁死", "盗塁死", "牽制死", "三振", "併殺打", "野選", "振り逃げ", "打撃妨害"]
        
        df_b_calc["is_hit"] = df_b_calc["結果"].isin(hit_cols).astype(int)
        df_b_calc["is_ab"] = df_b_calc["結果"].isin(ab_cols).astype(int)
        df_b_calc["is_hr"] = (df_b_calc["結果"] == "本塁打").astype(int)

        # 長打率計算用に、塁打の内訳フラグを作成
        df_b_calc["is_1b"] = (df_b_calc["結果"] == "単打").astype(int)
        df_b_calc["is_2b"] = (df_b_calc["結果"] == "二塁打").astype(int)
        df_b_calc["is_3b"] = (df_b_calc["結果"] == "三塁打").astype(int)
        
        # OPS計算用 (出塁数: 安打+四死球, 塁打数: 単打1, 二塁打2...)
        df_b_calc["is_bb"] = df_b_calc["結果"].isin(["四球", "死球"]).astype(int)
        df_b_calc["bases"] = 0
        df_b_calc.loc[df_b_calc["結果"]=="単打", "bases"] = 1
        df_b_calc.loc[df_b_calc["結果"]=="二塁打", "bases"] = 2
        df_b_calc.loc[df_b_calc["結果"]=="三塁打", "bases"] = 3
        df_b_calc.loc[df_b_calc["結果"]=="本塁打", "bases"] = 4

        for c in ["打点", "盗塁", "得点"]: 
            df_b_calc[c] = pd.to_numeric(df_b_calc[c], errors='coerce').fillna(0)
    else:
        # データがない場合でも、後続のフィルタ処理でエラーにならないようカラム定義をしておく
        df_b_calc = pd.DataFrame(columns=["Year", "選手名", "結果", "is_hit", "is_ab", "is_hr", "is_1b", "is_2b", "is_3b", "is_bb", "bases", "打点", "盗塁", "得点"])

    # --- 投手データ ---
    if not df_pitching.empty:
        df_pitching["Year"] = pd.to_datetime(df_pitching["日付"]).dt.year.astype(str)
        
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

        df_p_calc["is_win"] = df_p_calc["勝敗"].astype(str).str.contains("勝").astype(int)
        df_p_calc["is_lose"] = df_p_calc["勝敗"].astype(str).str.contains("負|敗").astype(int)
        df_p_calc["is_so"] = (df_p_calc["結果"] == "三振").astype(int)
        
        if "奪三振" not in df_p_calc.columns: df_p_calc["奪三振"] = 0
        if "処理野手" not in df_p_calc.columns: df_p_calc["処理野手"] = ""
        
        for c in ["自責点", "失点", "アウト数", "被安打", "与四球", "奪三振"]:
             if c not in df_p_calc.columns: df_p_calc[c] = 0
             df_p_calc[c] = pd.to_numeric(df_p_calc[c], errors='coerce').fillna(0)
             
        df_p_calc["total_bb"] = df_p_calc["与四球"] + df_p_calc["結果"].isin(["四球", "死球"]).astype(int)
    else:
        df_p_calc = pd.DataFrame()

    # --- ヘルパー関数 ---
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

    # 集計ルール
    agg_rules_b = {"is_hit": "sum", "is_ab": "sum", "is_hr": "sum", "is_1b": "sum", "is_2b": "sum", "is_3b": "sum", "is_bb": "sum","打点": "sum", "盗塁": "sum", "得点": "sum", "is_bb": "sum", "bases": "sum"}
    agg_rules_p = {"アウト数": "sum", "自責点": "sum", "失点": "sum", "is_win": "sum", "is_lose": "sum", "被安打": "sum", "total_bb": "sum", "is_so": "sum", "奪三振": "sum"}

    # タブ構成
    t_total, t_year, t_rank, t_rec = st.tabs(["個人通算", "個人年度別", "期間別ランキング", "歴代記録"])

    # ----------------------------------------------------
    # 1. 個人通算
    # ----------------------------------------------------
    with t_total:
        st.markdown("#### 📊 通算成績リスト")
        years = sorted(list(set(df_batting["Year"].unique()) | set(df_pitching["Year"].unique())), reverse=True) if not df_batting.empty else []
        
        c1, c2 = st.columns(2)
        target_year = c1.selectbox("年度", ["通算"] + years)
        target_type = c2.selectbox("試合種別", ["全種別", "公式戦 (トータル)", "練習試合"])

        df_b_tg = df_b_calc.copy()
        df_p_tg = df_p_calc.copy()

        if target_year != "通算":
            df_b_tg = df_b_tg[df_b_tg["Year"] == target_year]
            df_p_tg = df_p_tg[df_p_tg["Year"] == target_year]
        
        if target_type == "公式戦 (トータル)":
            df_b_tg = df_b_tg[df_b_tg["試合種別"].isin(OFFICIAL_GAME_TYPES)]
            df_p_tg = df_p_tg[df_p_tg["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        elif target_type == "練習試合":
            df_b_tg = df_b_tg[df_b_tg["試合種別"] == "練習試合"]
            df_p_tg = df_p_tg[df_p_tg["試合種別"] == "練習試合"]

        st_bat, st_pit, st_fld = st.tabs(["打撃", "投手", "守備"])
        
        with st_bat:
            if not df_b_tg.empty:
                # 集計実行 (agg_rules_b に is_1b, is_2b 等が含まれている前提)
                stats = df_b_tg.groupby("選手名").agg(agg_rules_b).reset_index()
                
                # --- 1. 打率計算 ---
                stats["打率"] = stats.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)

                # --- 2. OPS計算用の準備（出塁率 & 長打率） ---
                
                # A. 出塁率 (OBP) = (安打 + 四死球) / (打数 + 四死球) ※犠飛等は簡易化のため省略
                stats["出塁率"] = stats.apply(
                    lambda x: (x["is_hit"] + x["is_bb"]) / (x["is_ab"] + x["is_bb"]) 
                    if (x["is_ab"] + x["is_bb"]) > 0 else 0, 
                    axis=1
                )

                # B. 長打率 (SLG) = 塁打 / 打数
                # 塁打 = 1B + 2*2B + 3*3B + 4*HR
                stats["TotalBases"] = stats["is_1b"] + (stats["is_2b"] * 2) + (stats["is_3b"] * 3) + (stats["is_hr"] * 4)
                stats["長打率"] = stats.apply(
                    lambda x: x["TotalBases"] / x["is_ab"] 
                    if x["is_ab"] > 0 else 0, 
                    axis=1
                )

                # --- 3. OPS計算 (出塁率 + 長打率) ---
                stats["OPS"] = stats["出塁率"] + stats["長打率"]

                # 整数型への変換
                for c in ["is_hit", "is_ab", "is_hr", "打点", "盗塁"]: 
                    stats[c] = stats[c].astype(int)

                # 表示用データフレームの作成
                disp = stats.rename(columns={"is_hit":"安打", "is_ab":"打数", "is_hr":"本塁打"}).sort_values("OPS", ascending=False)
                
                # 小数点フォーマット
                disp["打率"] = disp["打率"].map(lambda x: f"{x:.3f}")
                disp["OPS"] = disp["OPS"].map(lambda x: f"{x:.3f}")
                disp["長打率"] = disp["長打率"].map(lambda x: f"{x:.3f}")
                disp["出塁率"] = disp["出塁率"].map(lambda x: f"{x:.3f}")

                # データフレーム表示（OPSと長打率を追加）
                st.dataframe(
                    disp[["選手名", "打率", "OPS", "長打率", "出塁率", "打数", "安打", "本塁打", "打点", "盗塁"]], 
                    use_container_width=True, 
                    hide_index=True
                )
            else: 
                st.info("データなし")

        with st_pit:
            if not df_p_tg.empty:
                stats_p = df_p_tg.groupby("選手名").agg(agg_rules_p).reset_index()
                stats_p["TotalSO"] = stats_p["is_so"] + stats_p["奪三振"]
                stats_p["防御率"] = stats_p.apply(lambda x: (x["自責点"]*7)/(x["アウト数"]/3) if x["アウト数"]>0 else 0, axis=1)
                stats_p["投球回"] = stats_p["アウト数"].apply(lambda x: f"{int(x//3)}.{int(x%3)}")
                for c in ["is_win", "is_lose", "TotalSO", "自責点"]: stats_p[c] = stats_p[c].astype(int)

                disp_p = stats_p[["選手名", "防御率", "is_win", "is_lose", "投球回", "TotalSO", "自責点"]].copy()
                disp_p.columns = ["選手名", "防御率", "勝", "敗", "投球回", "奪三振", "自責点"]
                disp_p = disp_p.sort_values("防御率")
                disp_p["防御率"] = disp_p["防御率"].map(lambda x: f"{x:.2f}")
                st.dataframe(disp_p, use_container_width=True, hide_index=True)
            else: st.info("データなし")

        with st_fld:
            if not df_p_tg.empty:
                fld_data = df_p_tg[df_p_tg["処理野手"] != ""].copy()
                fld_data = fld_data[fld_data["処理野手"].notna()]
                if not fld_data.empty:
                    stats_f = pd.crosstab(fld_data["処理野手"], fld_data["結果"])
                    for col in ["凡退", "犠打", "失策", "走塁死", "牽制死", "盗塁死", "併殺打"]:
                        if col not in stats_f.columns: stats_f[col] = 0
                    out_cols = [c for c in stats_f.columns if c != "失策"]
                    stats_f["刺殺・補殺"] = stats_f[out_cols].sum(axis=1)
                    stats_f["守備機会"] = stats_f["刺殺・補殺"] + stats_f["失策"]
                    stats_f["守備率"] = stats_f.apply(lambda row: (row["守備機会"] - row["失策"]) / row["守備機会"] if row["守備機会"] > 0 else 0.000, axis=1)
                    stats_f = stats_f.reset_index()
                    display_rows = []
                    pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                    for _, row in stats_f.iterrows():
                        raw = row["処理野手"]; nm = raw; pos = "-"
                        if "(" in raw:
                            try: nm, pos = raw.split(" ("); pos = pos.replace(")", "")
                            except: pass
                        try: sk = pos_order.index(pos)
                        except: sk = 99
                        display_rows.append({"SortKey": sk, "位置": pos, "選手名": nm, "守備機会": int(row["守備機会"]), "失策": int(row["失策"]), "守備率": row["守備率"]})
                    
                    if display_rows:
                        df_disp = pd.DataFrame(display_rows).sort_values(["SortKey", "守備機会"], ascending=[True, False])
                        df_disp["守備率"] = df_disp["守備率"].map(lambda x: f"{x:.3f}")
                        st.dataframe(df_disp[["位置", "選手名", "守備機会", "失策", "守備率"]], use_container_width=True, hide_index=True)
                    else: st.info("なし")
                else: st.info("なし")
            else: st.info("なし")

    # ----------------------------------------------------
    # 2. 個人年度別 + 通算
    # ----------------------------------------------------
    with t_year:
        sel_player = st.selectbox("選手選択", ALL_PLAYERS)
        if sel_player:
            # =================================================
            # ⚔️ 打撃成績 (年度別 + 通算)
            # =================================================
            if not df_b_calc.empty:
                my_b = df_b_calc[df_b_calc["選手名"] == sel_player]
                if not my_b.empty:
                    # 1. 年度別データの作成
                    hist = my_b.groupby("Year").agg(agg_rules_b).sort_index(ascending=False)
                    
                    # 2. 通算データの作成（全期間の合計を算出）
                    total_s = my_b.agg(agg_rules_b) # Seriesとして合計を取得
                    # 通算行をDataFrame化（indexを"通算"にする）
                    hist_total = pd.DataFrame(total_s).T
                    hist_total.index = ["通算"]

                    # 3. 年度別と通算を結合してから、まとめて指標計算を行う
                    #    (計算ロジックを1箇所にまとめるため)
                    combined_hist = pd.concat([hist_total, hist])

                    # --- 指標計算 (combined_histに対して一括実行) ---
                    # 打率
                    combined_hist["打率"] = combined_hist.apply(
                        lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1
                    )
                    
                    # 出塁率
                    combined_hist["出塁率"] = combined_hist.apply(
                        lambda x: (x["is_hit"] + x["is_bb"]) / (x["is_ab"] + x["is_bb"]) 
                        if (x["is_ab"] + x["is_bb"]) > 0 else 0, axis=1
                    )

                    # 長打率
                    # 塁打計算のために必要なカラムがあるか確認しつつ計算
                    combined_hist["TotalBases"] = combined_hist["is_1b"] + (combined_hist["is_2b"] * 2) + (combined_hist["is_3b"] * 3) + (combined_hist["is_hr"] * 4)
                    combined_hist["長打率"] = combined_hist.apply(
                        lambda x: x["TotalBases"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1
                    )

                    # OPS
                    combined_hist["OPS"] = combined_hist["出塁率"] + combined_hist["長打率"]

                    # 整数型変換 (表示用)
                    for col in ["is_hit", "is_ab", "is_hr", "打点", "盗塁"]: 
                        combined_hist[col] = combined_hist[col].astype(int)

                    # 表示用DataFrameの整形
                    disp_hist = pd.DataFrame()
                    disp_hist["打率"] = combined_hist["打率"]
                    disp_hist["OPS"] = combined_hist["OPS"]
                    disp_hist["長打率"] = combined_hist["長打率"]
                    disp_hist["出塁率"] = combined_hist["出塁率"]
                    disp_hist["打数"] = combined_hist["is_ab"]
                    disp_hist["安打"] = combined_hist["is_hit"]
                    disp_hist["本塁打"] = combined_hist["is_hr"]
                    disp_hist["打点"] = combined_hist["打点"]
                    disp_hist["盗塁"] = combined_hist["盗塁"]
                    disp_hist.index.name = "年度"

                    st.markdown("##### ⚔️ 打撃成績推移")
                    # スタイル適用して表示
                    st.dataframe(
                        disp_hist.style.format({
                            "打率": "{:.3f}", "OPS": "{:.3f}", "長打率": "{:.3f}", "出塁率": "{:.3f}"
                        }).applymap(
                            # "通算"行だけ太字や色を変える（オプション）
                            lambda x: "font-weight: bold; background-color: #f0f2f6;" if isinstance(x, str) else "", 
                            subset=pd.IndexSlice[["通算"], :]
                        )
                    )
                else: st.info("データなし")
        
        # =================================================
        # 🛡️ 投手成績 (年度別 + 通算)
        # =================================================
        if not df_p_calc.empty:
            my_p = df_p_calc[df_p_calc["選手名"] == sel_player]
            if not my_p.empty:
                # 1. 年度別
                hist_p = my_p.groupby("Year").agg(agg_rules_p).sort_index(ascending=False)
                
                # 2. 通算
                total_p_s = my_p.agg(agg_rules_p)
                hist_p_total = pd.DataFrame(total_p_s).T
                hist_p_total.index = ["通算"]

                # 3. 結合
                combined_p = pd.concat([hist_p_total, hist_p])

                # --- 指標計算 ---
                combined_p["TotalSO"] = combined_p["is_so"] + combined_p["奪三振"]
                
                # イニング数（計算用）
                combined_p["Innings"] = combined_p["アウト数"] / 3

                # 防御率 (7回制)
                combined_p["防御率"] = combined_p.apply(
                    lambda x: (x["自責点"]*7)/x["Innings"] if x["Innings"]>0 else 0, axis=1
                )

                # 勝率
                combined_p["勝率"] = combined_p.apply(
                    lambda x: x["is_win"] / (x["is_win"] + x["is_lose"]) 
                    if (x["is_win"] + x["is_lose"]) > 0 else 0, axis=1
                )

                # 奪三振率 (7回制: K/7)
                combined_p["奪三振率"] = combined_p.apply(
                    lambda x: (x["TotalSO"] * 7) / x["Innings"] 
                    if x["Innings"] > 0 else 0, axis=1
                )

                # WHIP
                combined_p["WHIP"] = combined_p.apply(
                    lambda x: (x["total_bb"] + x["被安打"]) / x["Innings"] 
                    if x["Innings"] > 0 else 0, axis=1
                )

                # 表示用: 投球回 (整数.端数)
                combined_p["回"] = combined_p["アウト数"].apply(lambda x: f"{int(x//3)}.{int(x%3)}")
                
                # 整数型変換
                for col in ["is_win", "is_lose", "TotalSO"]: 
                    combined_p[col] = combined_p[col].astype(int)

                # 表示用整形
                disp_p_hist = pd.DataFrame()
                disp_p_hist["防御率"] = combined_p["防御率"]
                disp_p_hist["勝率"] = combined_p["勝率"]
                disp_p_hist["WHIP"] = combined_p["WHIP"]
                disp_p_hist["奪三振率"] = combined_p["奪三振率"]
                
                disp_p_hist["投球回"] = combined_p["回"]
                disp_p_hist["勝"] = combined_p["is_win"]
                disp_p_hist["敗"] = combined_p["is_lose"]
                disp_p_hist["奪三振"] = combined_p["TotalSO"]
                disp_p_hist.index.name = "年度"

                st.markdown("##### 🛡️ 投手成績推移")
                st.dataframe(
                    disp_p_hist.style.format({
                        "防御率": "{:.2f}",
                        "勝率": "{:.3f}",
                        "WHIP": "{:.2f}",
                        "奪三振率": "{:.2f}"
                    })
                )
            else: st.info("データなし")

    # ----------------------------------------------------
    # 3. ランキング
    # ----------------------------------------------------
    with t_rank:
        st.markdown("#### 🏆 期間別ランキング")
        period = st.radio("集計期間", ["年度別", "月間", "直近3試合"], horizontal=True)
        df_b_sub = df_b_calc.copy(); df_p_sub = df_p_calc.copy()
        df_b_sub["Date"] = pd.to_datetime(df_b_sub["日付"]); df_p_sub["Date"] = pd.to_datetime(df_p_sub["日付"])
        def_ab = 1; def_inn = 1

        if period == "年度別":
            ys = sorted(df_b_sub["Date"].dt.year.unique(), reverse=True)
            sy = st.selectbox("年度選択", ys) if len(ys)>0 else datetime.date.today().year
            df_b_sub = df_b_sub[df_b_sub["Date"].dt.year == sy]
            df_p_sub = df_p_sub[df_p_sub["Date"].dt.year == sy]
            if not df_b_sub.empty: def_ab = int(df_b_sub["日付"].nunique() * 2.0); def_inn = int(df_b_sub["日付"].nunique())
        elif period == "月間":
            df_b_sub["YM"] = df_b_sub["Date"].dt.strftime('%Y-%m')
            ms = sorted(df_b_sub["YM"].unique(), reverse=True)
            sm = st.selectbox("月選択", ms) if len(ms)>0 else None
            if sm:
                df_b_sub = df_b_sub[df_b_sub["YM"] == sm]
                df_p_sub["YM"] = df_p_sub["Date"].dt.strftime('%Y-%m')
                df_p_sub = df_p_sub[df_p_sub["YM"] == sm]
                def_ab = int(df_b_sub["日付"].nunique()); def_inn = def_ab
            else: df_b_sub = pd.DataFrame(); df_p_sub = pd.DataFrame()
        else:
            dates = sorted(df_b_sub["Date"].unique(), reverse=True)[:3]
            df_b_sub = df_b_sub[df_b_sub["Date"].isin(dates)]; df_p_sub = df_p_sub[df_p_sub["Date"].isin(dates)]
            def_ab = 3; def_inn = 3

        c_f1, c_f2 = st.columns(2)
        min_ab = c_f1.number_input("規定打席", value=max(1, def_ab), min_value=1, key=f"ab_{period}")
        min_inn = c_f2.number_input("規定投球回", value=max(1, def_inn), min_value=1, key=f"inn_{period}")
        st.divider()

        if not df_b_sub.empty:
            rank_b = get_ranking_df(df_b_sub, ["選手名"], agg_rules_b)
            rank_b["AVG"] = rank_b.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
            # OPS: 出塁率(安+四)/打席 + 長打率(塁打)/打数 (簡易計算)
            # ※本来、出塁率は(安+四+死)/(打数+四+死+犠飛)、長打率は塁打/打数
            # ここでは (安打+四球)/打席数 という簡易出塁率、塁打/打数 という長打率で計算
            # 分母0回避
            rank_b["OBP"] = (rank_b["is_hit"] + rank_b["is_bb"]) / (rank_b["is_ab"] + rank_b["is_bb"]) # 近似
            rank_b["SLG"] = rank_b["bases"] / rank_b["is_ab"]
            rank_b["OPS"] = (rank_b["OBP"] + rank_b["SLG"]).fillna(0)
            
            st.markdown("##### ⚔️ 打撃部門")
            r1, r2, r3 = st.columns(3)
            with r1: show_top5("打率", rank_b[rank_b["is_ab"]>=min_ab], "AVG", "選手名", "AVG", format_float=True)
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
        rec_mode = st.radio("対象", ["シーズン最高 (Season High)", "生涯通算 (Lifetime)"], horizontal=True)
        
        if "Season" in rec_mode:
            df_bat_target = get_ranking_df(df_b_calc, ["Year", "選手名"], agg_rules_b)
            df_bat_target["Display"] = df_bat_target["選手名"] + " (" + df_bat_target["Year"] + ")"
            
            df_pit_target = get_ranking_df(df_p_calc, ["Year", "選手名"], agg_rules_p)
            df_pit_target["Display"] = df_pit_target["選手名"] + " (" + df_pit_target["Year"] + ")"
            min_ab_r = 10; min_inn_r = 10
        else:
            df_bat_target = get_ranking_df(df_b_calc, ["選手名"], agg_rules_b)
            df_bat_target["Display"] = df_bat_target["選手名"]
            
            df_pit_target = get_ranking_df(df_p_calc, ["選手名"], agg_rules_p)
            df_pit_target["Display"] = df_pit_target["選手名"]
            min_ab_r = 20; min_inn_r = 15
        
        # 指標計算
        # 打撃
        df_bat_target["AVG"] = df_bat_target.apply(lambda x: x["is_hit"]/x["is_ab"] if x["is_ab"]>0 else 0, axis=1)
        df_bat_target["OBP"] = (df_bat_target["is_hit"] + df_bat_target["is_bb"]) / (df_bat_target["is_ab"] + df_bat_target["is_bb"]) 
        df_bat_target["SLG"] = df_bat_target["bases"] / df_bat_target["is_ab"]
        df_bat_target["OPS"] = (df_bat_target["OBP"] + df_bat_target["SLG"]).fillna(0)

        # 投手
        df_pit_target["Innings"] = df_pit_target["アウト数"]/3
        df_pit_target["ERA"] = df_pit_target.apply(lambda x: (x["自責点"]*7)/x["Innings"] if x["Innings"]>0 else 99.99, axis=1)
        df_pit_target["TotalSO"] = df_pit_target["is_so"] + df_pit_target["奪三振"]
        df_pit_target["WHIP"] = df_pit_target.apply(lambda x: (x["total_bb"]+x["被安打"])/x["Innings"] if x["Innings"]>0 else 99.99, axis=1)

        st.divider()
        st.markdown(f"#####  ⚔️  歴代打撃トップ5")
        tc1, tc2, tc3 = st.columns(3)
        with tc1: show_top5("打率", df_bat_target[df_bat_target["is_ab"] >= min_ab_r], "AVG", "Display", "AVG", suffix="", format_float=True)
        with tc2: show_top5("OPS", df_bat_target[df_bat_target["is_ab"] >= min_ab_r], "OPS", "Display", "OPS", suffix="", format_float=True)
        with tc3: show_top5("安打数", df_bat_target, "is_hit", "Display", "is_hit", suffix=" 本")
        
        st.write("")
        tc4, tc5, tc6 = st.columns(3)
        with tc4: show_top5("本塁打", df_bat_target, "is_hr", "Display", "is_hr", suffix=" 本")
        with tc5: show_top5("打点", df_bat_target, "打点", "Display", "打点", suffix=" 点")
        with tc6: show_top5("盗塁", df_bat_target, "盗塁", "Display", "盗塁", suffix=" 個")
        
        st.divider()
        st.markdown(f"#####  🛡️  歴代投手トップ5")
        tp1, tp2, tp3, tp4 = st.columns(4)
        with tp1: show_top5("防御率", df_pit_target[df_pit_target["Innings"] >= min_inn_r], "ERA", "Display", "ERA", ascending=True, suffix="", format_float=True)
        with tp2: show_top5("WHIP", df_pit_target[df_pit_target["Innings"] >= min_inn_r], "WHIP", "Display", "WHIP", ascending=True, suffix="", format_float=True)
        with tp3: show_top5("勝利数", df_pit_target, "is_win", "Display", "is_win", suffix=" 勝")
        with tp4: show_top5("奪三振", df_pit_target, "TotalSO", "Display", "TotalSO", suffix=" 個")