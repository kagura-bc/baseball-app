import streamlit as st
import pandas as pd
from config.settings import OFFICIAL_GAME_TYPES
from utils.ui import render_scoreboard

def show_team_stats(df_batting, df_pitching):
    st.title(" 🏆 チーム成績ダッシュボード")

    # 1. データ準備 & 集計ロジック
    if df_batting.empty and df_pitching.empty:
        st.info("データがまだありません。")
        return

    games_map = {}

    # --- A. 打撃データから集計 ---
    df_b_work = df_batting.copy()
    df_b_work["DateStr"] = pd.to_datetime(df_b_work["日付"]).dt.strftime('%Y-%m-%d')
    
    for (d_str, opp, m_type), group in df_b_work.groupby(["DateStr", "対戦相手", "試合種別"]):
        # 1. 得点の計算
        team_rec_rows = group[group["選手名"] == "チーム記録"]
        if not team_rec_rows.empty:
            runs = pd.to_numeric(team_rec_rows["得点"], errors='coerce').fillna(0).sum()
            is_team_record = True
        else:
            runs = pd.to_numeric(group["得点"], errors='coerce').fillna(0).sum()
            is_team_record = False

        # 2. スタッツの計算
        individuals = group[group["選手名"] != "チーム記録"]
        total_hits = 0; total_ab = 0; total_hr = 0; total_sb = 0

        if not individuals.empty:
            s1 = len(individuals[individuals["結果"] == "単打"])
            s2 = len(individuals[individuals["結果"] == "二塁打"])
            s3 = len(individuals[individuals["結果"] == "三塁打"])
            hr = len(individuals[individuals["結果"] == "本塁打"])
            total_hits = s1 + s2 + s3 + hr
            total_hr = hr
            total_sb = pd.to_numeric(individuals["盗塁"], errors='coerce').fillna(0).sum()
            
            ab_results = ["単打", "二塁打", "三塁打", "本塁打", "三振", "凡退", "失策", "併殺打", "野選", "振り逃げ"]
            total_ab = len(individuals[individuals["結果"].isin(ab_results)])

        gr = group["グラウンド"].iloc[0] if not group.empty else ""
        key = (d_str, opp, m_type)

        if key not in games_map:
            games_map[key] = {
                "日付": d_str, "対戦相手": opp, "試合種別": m_type, "グラウンド": gr,
                "得点": 0, "失点": 0, "打数": 0, "安打": 0, "本塁打": 0, "盗塁": 0,
                "自責点": 0, "投球回": 0.0,
                "has_team_record": False
            }
        
        games_map[key]["得点"] = runs
        games_map[key]["打数"] = total_ab
        games_map[key]["安打"] = total_hits
        games_map[key]["本塁打"] = total_hr
        games_map[key]["盗塁"] = total_sb
        if is_team_record:
            games_map[key]["has_team_record"] = True

    # --- B. 投手データから集計 ---
    df_p_work = df_pitching.copy()
    df_p_work["DateStr"] = pd.to_datetime(df_p_work["日付"]).dt.strftime('%Y-%m-%d')

    for (d_str, opp, m_type), group in df_p_work.groupby(["DateStr", "対戦相手", "試合種別"]):
        team_rec_rows = group[group["選手名"] == "チーム記録"]
        if not team_rec_rows.empty:
            runs_allowed = pd.to_numeric(team_rec_rows["失点"], errors='coerce').fillna(0).sum()
        else:
            runs_allowed = pd.to_numeric(group["失点"], errors='coerce').fillna(0).sum()

        if "投手名" in group.columns:
            individuals_p = group[group["投手名"] != "チーム記録"]
        else:
            individuals_p = group[group["選手名"] != "チーム記録"]

        er = 0; outs = 0.0
        if not individuals_p.empty:
            if "自責点" in individuals_p.columns:
                er = pd.to_numeric(individuals_p["自責点"], errors='coerce').fillna(0).sum()
            
            if "アウト数" in individuals_p.columns:
                total_outs = pd.to_numeric(individuals_p["アウト数"], errors='coerce').fillna(0).sum()
                outs = total_outs / 3
            elif "投球回" in individuals_p.columns:
                outs = pd.to_numeric(individuals_p["投球回"], errors='coerce').fillna(0).sum()

        key = (d_str, opp, m_type)
        if key not in games_map:
            gr = group["グラウンド"].iloc[0] if not group.empty else ""
            games_map[key] = {
                "日付": d_str, "対戦相手": opp, "試合種別": m_type, "グラウンド": gr,
                "得点": 0, "失点": 0, "打数": 0, "安打": 0, "本塁打": 0, "盗塁": 0,
                "自責点": 0, "投球回": 0.0,
                "has_team_record": False
            }
        
        games_map[key]["失点"] = runs_allowed
        games_map[key]["自責点"] += er
        games_map[key]["投球回"] += outs

    match_results = list(games_map.values())
    df_team_stats = pd.DataFrame(match_results)

    if not df_team_stats.empty:
        df_team_stats["日付"] = pd.to_datetime(df_team_stats["日付"])
        df_team_stats = df_team_stats.sort_values("日付", ascending=False)

    # 2. フィルタリング
    if not df_team_stats.empty:
        df_team_stats["Year"] = df_team_stats["日付"].dt.year.astype(str)
        all_years = sorted(list(df_team_stats["Year"].unique()), reverse=True)
        
        c_filter1, c_filter2 = st.columns(2)
        with c_filter1:
            default_idx = 1 if all_years else 0
            target_year = st.selectbox("年度", ["通算"] + all_years, index=default_idx, key="team_stats_year")
        
        with c_filter2:
            types_list = [x for x in df_team_stats["試合種別"].unique() if str(x) != 'nan']
            others = [t for t in types_list if t != "練習試合"]
            all_types = ["全種別", "練習試合", "公式戦 (トータル)"] + sorted(others)
            target_type = st.selectbox("試合種別", all_types, key="team_stats_type")
            
        df_display = df_team_stats.copy()
        if target_year != "通算":
            df_display = df_display[df_display["Year"] == target_year]

        if target_type == "全種別": pass
        elif target_type == "公式戦 (トータル)":
            df_display = df_display[df_display["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        else:
            df_display = df_display[df_display["試合種別"] == target_type]
    else:
        df_display = pd.DataFrame()

    st.divider()

    # 3. 集計 & メトリクス
    wins = 0; losses = 0; draws = 0
    total_score = 0; total_lost = 0
    total_ab_sum = 0; total_hits = 0; total_hr = 0; total_sb = 0; total_er = 0; total_ip = 0.0
    viewer_options = []

    if not df_display.empty:
        for index, row in df_display.iterrows():
            s = row["得点"]; l = row["失点"]
            total_score += s; total_lost += l
            
            total_ab_sum += row.get("打数", 0) 
            total_hits += row.get("安打", 0)
            total_hr += row.get("本塁打", 0)
            total_sb += row.get("盗塁", 0)
            total_er += row.get("自責点", 0)
            total_ip += row.get("投球回", 0)

            res_txt = "-"
            if s > l: wins += 1; res_txt = " 🔴 勝ち"
            elif s < l: losses += 1; res_txt = " 🔵 敗け"
            else: draws += 1; res_txt = " △ 引き分け"
            
            df_display.at[index, "勝敗"] = res_txt
            d_str = row["日付"].strftime('%Y-%m-%d')
            label = f"{d_str} vs {row['対戦相手']} ({res_txt}) - {row['試合種別']}"
            viewer_options.append(label)

    total_games = wins + losses + draws
    win_pct = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    team_avg = total_hits / total_ab_sum if total_ab_sum > 0 else 0.0
    team_era = (total_er * 7) / total_ip if total_ip > 0 else 0.0
    runs_per_game = total_score / total_games if total_games > 0 else 0.0
    runs_allowed_per_game = total_lost / total_games if total_games > 0 else 0.0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("試合数", f"{total_games}")
    m2.metric("勝利", f"{wins}", delta="WIN")
    m3.metric("敗戦", f"{losses}", delta="-LOSE", delta_color="inverse")
    m4.metric("引分", f"{draws}")
    m5.metric("勝率", f"{win_pct:.3f}")

    st.markdown("#####   ⚔️   攻撃スタッツ")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("チーム打率", f"{team_avg:.3f}")
    a2.metric("平均得点", f"{runs_per_game:.2f}", delta=f"総: {int(total_score)}")
    a3.metric("本塁打数", f"{int(total_hr)} 本")
    a4.metric("盗塁数", f"{int(total_sb)} 個")

    st.markdown("#####   🛡️   守備スタッツ")
    d1, d2, d3 = st.columns(3)
    d1.metric("チーム防御率", f"{team_era:.2f}")
    d2.metric("平均失点", f"{runs_allowed_per_game:.2f}", delta=f"総: {int(total_lost)}", delta_color="inverse")
    d3.metric("得失点差", f"{int(total_score - total_lost):+d}")

    # 4. 試合履歴
    st.subheader(" 📋  試合履歴")
    if not df_display.empty:
        cols = ["日付", "対戦相手", "得点", "失点", "勝敗", "試合種別", "グラウンド"]
        st.dataframe(df_display[cols], use_container_width=True, hide_index=True)
    else:
        st.write("履歴データがありません")

    # 5. 試合詳細ビューワー
    st.markdown("### 📝 試合詳細ビューワー")
    
    if viewer_options:
        selected_label = st.selectbox("詳細を確認したい試合を選択してください", viewer_options, key="detail_selector")
        
        if selected_label:
            try:
                parts = selected_label.split(" vs ")
                target_date_str = parts[0]
                rest = parts[1]
                target_opp = rest.split(" (")[0]
            except:
                st.error("データの特定に失敗しました。")
                target_date_str = ""; target_opp = ""

            if target_date_str:
                target_row = df_display[(df_display["日付"] == pd.to_datetime(target_date_str)) & (df_display["対戦相手"] == target_opp)].iloc[0]
                has_team_rec = target_row["has_team_record"]
                
                match_bat = df_batting[(pd.to_datetime(df_batting["日付"]).dt.strftime('%Y-%m-%d') == target_date_str) & (df_batting["対戦相手"] == target_opp)].copy()
                match_pit = df_pitching[(pd.to_datetime(df_pitching["日付"]).dt.strftime('%Y-%m-%d') == target_date_str) & (df_pitching["対戦相手"] == target_opp)].copy()

                detected_top = True
                tr_row = match_bat[match_bat["選手名"] == "チーム記録"]
                if not tr_row.empty:
                    p_info = str(tr_row.iloc[0]["位置"])
                    if "後攻" in p_info or "裏" in p_info: detected_top = False

                if has_team_rec:
                    sb_bat = match_bat[match_bat["選手名"] == "チーム記録"].copy()
                    sb_pit = match_pit[match_pit["選手名"] == "チーム記録"].copy()
                else:
                    sb_bat = match_bat; sb_pit = match_pit

                render_scoreboard(sb_bat, sb_pit, target_date_str, target_row["試合種別"], target_row["グラウンド"], target_opp, is_top_first=detected_top)

                # ここからスタメン表示ロジック) 
                st.divider()
                st.markdown("#### 🏏  打撃成績")
                personal_bat = match_bat[match_bat["選手名"] != "チーム記録"].copy()
                
                if not personal_bat.empty:
                    # スタメンとベンチの分離
                    active_mask = personal_bat["イニング"] != "ベンチ"
                    active_players = personal_bat.loc[active_mask, "選手名"].unique()
                    
                    df_active = personal_bat[(personal_bat["選手名"].isin(active_players)) & (personal_bat["イニング"] != "ベンチ")].copy()
                    df_bench = personal_bat[~personal_bat["選手名"].isin(active_players)].copy()

                    if not df_active.empty:
                        def summarize_bat(df_group):
                            df_group["打点"] = pd.to_numeric(df_group["打点"], errors='coerce').fillna(0)
                            df_group["盗塁"] = pd.to_numeric(df_group["盗塁"], errors='coerce').fillna(0)
                            
                            pa_list = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "併殺打", "野選", "振り逃げ", "打撃妨害"]
                            tpa = df_group[df_group["結果"].isin(pa_list)].shape[0]

                            hits = df_group[df_group["結果"].isin(["単打", "二塁打", "三塁打", "本塁打"])].shape[0]
                            hr = df_group[df_group["結果"] == "本塁打"].shape[0]
                            rbi = int(df_group["打点"].sum())
                            so = df_group[df_group["結果"].isin(["三振", "振り逃げ"])].shape[0]
                            bb = df_group[df_group["結果"].isin(["四球", "死球"])].shape[0]
                            sb = int(df_group["盗塁"].sum())
                            run = int(pd.to_numeric(df_group["得点"], errors='coerce').fillna(0).sum())

                            order_val = 999
                            if "打順" in df_group.columns:
                                vals = pd.to_numeric(df_group["打順"], errors='coerce').dropna()
                                if not vals.empty: order_val = int(vals.min())
                            
                            pos_val = ""
                            if "位置" in df_group.columns:
                                valid_pos = df_group["位置"].dropna().astype(str)
                                valid_pos = valid_pos[valid_pos != ""]
                                if not valid_pos.empty: pos_val = valid_pos.iloc[0]

                            res_parts = []
                            if hits > 0: res_parts.append(f"安打{hits}")
                            if hr > 0: res_parts.append(f"本塁打{hr}")
                            if rbi > 0: res_parts.append(f"打点{rbi}")
                            if sb > 0: res_parts.append(f"盗塁{sb}")
                            if run > 0: res_parts.append(f"得点{run}")
                            if so > 0: res_parts.append(f"三振{so}")
                            if bb > 0: res_parts.append(f"四球{bb}")
                            
                            summary_str = " ".join(res_parts)
                            return pd.Series({"打順": order_val, "守備": pos_val, "選手名": df_group["選手名"].iloc[0], "打席": tpa, "成績詳細": summary_str})

                        df_summary = df_active.groupby("選手名", sort=False).apply(summarize_bat).reset_index(drop=True)
                        
                        # 打順補完
                        temp_orders = []
                        for i in range(len(df_summary)):
                            current_val = df_summary.at[i, "打順"]
                            temp_orders.append(i + 1 if current_val == 999 else current_val)
                        df_summary["打順"] = temp_orders
                        df_summary = df_summary.sort_values("打順")
                        df_summary["打順"] = df_summary["打順"].astype(int).astype(str)
                        st.table(df_summary.set_index("打順")[["守備", "選手名", "打席", "成績詳細"]])
                    else:
                        st.info("出場選手の記録がありません")

                    if not df_bench.empty:
                        st.write("")
                        st.markdown("##### 🚌  ベンチ入りメンバー")
                        st.success(", ".join(df_bench["選手名"].unique().tolist()))
                else:
                    st.caption("※ 個人打撃成績なし")

                st.write("")
                st.markdown("#### ⚾  投手成績")
                personal_pit = match_pit[match_pit["選手名"] != "チーム記録"].copy()
                if not personal_pit.empty:
                    if "選手名" in personal_pit.columns:
                        if "投手名" not in personal_pit.columns: personal_pit["投手名"] = personal_pit["選手名"]
                        else: personal_pit["投手名"] = personal_pit["投手名"].replace("", pd.NA).fillna(personal_pit["選手名"])
                    personal_pit["投手名"] = personal_pit["投手名"].fillna("不明")

                    summary_list = []
                    for p_name, group in personal_pit.groupby("投手名", sort=False):
                        balls = pd.to_numeric(group["球数"], errors='coerce').fillna(0).sum()
                        runs = pd.to_numeric(group["失点"], errors='coerce').fillna(0).sum()
                        er = pd.to_numeric(group["自責点"], errors='coerce').fillna(0).sum()
                        
                        total_hits = 0; total_so = 0; total_bb = 0
                        for _, row in group.iterrows():
                            raw_h = int(row.get("被安打", 0)) if pd.notna(row.get("被安打", 0)) else 0
                            raw_so = int(row.get("奪三振", 0)) if pd.notna(row.get("奪三振", 0)) else 0
                            raw_bb = int(row.get("与四球", 0)) if pd.notna(row.get("与四球", 0)) else 0
                            res = str(row.get("結果", ""))
                            r_type = str(row.get("種別", ""))

                            if res == "まとめ" or "まとめ" in str(row.get("イニング", "")):
                                total_hits += raw_h; total_so += raw_so; total_bb += raw_bb
                            elif "ダミー" in r_type: continue
                            else:
                                if res in ["安打", "単打", "二塁打", "三塁打", "本塁打"]: total_hits += 1
                                elif res in ["三振", "振り逃げ"]: total_so += 1
                                elif res in ["四球", "死球"]: total_bb += 1
                        
                        total_outs = 0
                        if "アウト数" in group.columns: total_outs += pd.to_numeric(group["アウト数"], errors='coerce').fillna(0).sum()
                        elif "投球回" in group.columns: total_outs += pd.to_numeric(group["投球回"], errors='coerce').fillna(0).sum() * 3
                        
                        fin = f"{int(total_outs//3)}"
                        frac = int(total_outs % 3)
                        if frac == 1: fin += " 1/3"
                        elif frac == 2: fin += " 2/3"

                        final_res = "-"
                        if "勝敗" in group.columns:
                            r_str = str(group["勝敗"].astype(str).unique())
                            if "勝" in r_str: final_res = "勝"
                            elif "負" in r_str: final_res = "負"
                            elif "S" in r_str: final_res = "S"
                            elif "H" in r_str: final_res = "H"
                        
                        summary_list.append({"投手名": p_name, "結果": final_res, "回": fin, "球数": int(balls), "被安": int(total_hits), "奪三": int(total_so), "四死": int(total_bb), "失点": int(runs), "自責": int(er)})
                    
                    st.table(pd.DataFrame(summary_list).set_index("投手名")[["結果", "回", "球数", "被安", "奪三", "四死", "失点", "自責"]])
                else:
                    st.caption("※ 個人投手成績なし")