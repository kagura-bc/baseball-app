import streamlit as st
import pandas as pd
from config.settings import OFFICIAL_GAME_TYPES
from utils.ui import render_scoreboard
import re

# ★ 集計計算を共通化
def calc_metrics(df):
    if df.empty:
        return {"games":0, "wins":0, "losses":0, "draws":0, "win_pct":0.0, "avg":0.0, "avg_runs":0.0, "hr":0, "sb":0, "era":0.0, "avg_lost":0.0, "diff":0, "err":0, "total_score":0, "total_lost":0}
    
    wins = 0; losses = 0; draws = 0
    total_score = 0; total_lost = 0
    total_ab = 0; total_hits = 0; total_hr = 0; total_sb = 0; total_er = 0; total_ip = 0.0
    total_errors = 0
    
    for _, row in df.iterrows():
        s = row.get("得点", 0)
        l = row.get("失点", 0)
        total_score += s
        total_lost += l
        total_ab += row.get("打数", 0) 
        total_hits += row.get("安打", 0)
        total_hr += row.get("本塁打", 0)
        total_sb += row.get("盗塁", 0)
        total_er += row.get("自責点", 0)
        total_ip += row.get("投球回", 0)
        total_errors += row.get("失策", 0)
        
        if s > l: wins += 1
        elif s < l: losses += 1
        else: draws += 1
            
    total_games = wins + losses + draws
    return {
        "games": total_games, "wins": wins, "losses": losses, "draws": draws,
        "win_pct": wins / total_games if total_games > 0 else 0.0,
        "avg": total_hits / total_ab if total_ab > 0 else 0.0,
        "avg_runs": total_score / total_games if total_games > 0 else 0.0,
        "hr": total_hr, "sb": total_sb,
        "era": (total_er * 7) / total_ip if total_ip > 0 else 0.0,
        "avg_lost": total_lost / total_games if total_games > 0 else 0.0,
        "diff": total_score - total_lost, "err": total_errors,
        "total_score": total_score, "total_lost": total_lost
    }

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
            valid_batting = group[group["イニング"] != "まとめ入力"]
            runs = pd.to_numeric(valid_batting["得点"], errors='coerce').fillna(0).sum()
            is_team_record = False

        # 2. スタッツの計算 (打席ごとのカウントロジック)
        individuals = group[group["選手名"] != "チーム記録"]
        total_hits = 0; total_ab = 0; total_hr = 0; total_sb = 0

        if not individuals.empty:
            # 凡退、失策、併殺打など、打数としてカウントすべきものを定義
            ab_results = [
                "単打", "二塁打", "三塁打", "本塁打", "三振", 
                "凡退", "失策", "併殺打", "野選", "振り逃げ三振", "犠飛"
            ]
            hit_results = ["単打", "二塁打", "三塁打", "本塁打", "安打"]

            for _, row in individuals.iterrows():
                res_str = str(row.get("結果", "")).strip()
                
                # 数値の取得（空欄や文字列は0になる）
                ab_val = pd.to_numeric(row.get("打数", 0), errors='coerce')
                hits_val = pd.to_numeric(row.get("安打", 0), errors='coerce')
                hr_val = pd.to_numeric(row.get("本塁打", 0), errors='coerce')
                sb_val = pd.to_numeric(row.get("盗塁", 0), errors='coerce')
                
                ab = int(ab_val) if pd.notna(ab_val) else 0
                hits = int(hits_val) if pd.notna(hits_val) else 0
                hr = int(hr_val) if pd.notna(hr_val) else 0
                sb = int(sb_val) if pd.notna(sb_val) else 0
                
                if ab > 0 or hits > 0:
                    # まとめ入力などで数値が存在する場合は優先加算
                    total_ab += ab
                    total_hits += hits
                    total_hr += hr
                    total_sb += sb
                else:
                    # 詳細入力の場合：文字から判定して加算
                    # 「凡退」が含まれていれば打数カウント
                    if res_str in ab_results or "凡退" in res_str or "失策" in res_str:
                        total_ab += 1
                    
                    if res_str in hit_results:
                        total_hits += 1
                        if res_str == "本塁打":
                            total_hr += 1
                    
                    total_sb += sb

        # 先攻後攻の判定
        top_bottom = "不明"
        if "イニング" in group.columns:
            innings = group["イニング"].dropna().astype(str).tolist()
            if any("表" in i for i in innings):
                top_bottom = "先攻"
            elif any("裏" in i for i in innings):
                top_bottom = "後攻"
        
        if top_bottom == "不明" and is_team_record:
            p_info = str(team_rec_rows.iloc[0].get("位置", ""))
            if "後攻" in p_info or "裏" in p_info:
                top_bottom = "後攻"
            elif "先攻" in p_info or "表" in p_info:
                top_bottom = "先攻"

        gr = group["グラウンド"].iloc[0] if not group.empty else ""
        key = (d_str, opp, m_type)

        if key not in games_map:
            games_map[key] = {
                "日付": d_str, "対戦相手": opp, "試合種別": m_type, "グラウンド": gr,
                "先攻後攻": top_bottom,
                "得点": 0, "失点": 0, "打数": 0, "安打": 0, "本塁打": 0, "盗塁": 0,
                "自責点": 0, "投球回": 0.0, "失策": 0,
                "has_team_record": False
            }
        
        games_map[key]["得点"] = runs
        games_map[key]["打数"] = total_ab
        games_map[key]["安打"] = total_hits
        games_map[key]["本塁打"] = total_hr
        games_map[key]["盗塁"] = total_sb
        games_map[key]["先攻後攻"] = top_bottom
        if is_team_record:
            games_map[key]["has_team_record"] = True

    # --- B. 投手データから集計 ---
    df_p_work = df_pitching.copy()
    df_p_work["DateStr"] = pd.to_datetime(df_p_work["日付"]).dt.strftime('%Y-%m-%d')

    for (d_str, opp, m_type), group in df_p_work.groupby(["DateStr", "対戦相手", "試合種別"]):
        team_rec_rows = group[group["選手名"] == "チーム記録"]
        if not team_rec_rows.empty:
            runs_allowed = pd.to_numeric(team_rec_rows["失点"], errors='coerce').fillna(0).sum()
            col_errors = pd.to_numeric(team_rec_rows["失策"], errors='coerce').fillna(0).sum() if "失策" in team_rec_rows.columns else 0
        else:
            runs_allowed = pd.to_numeric(group["失点"], errors='coerce').fillna(0).sum()
            col_errors = pd.to_numeric(group["失策"], errors='coerce').fillna(0).sum() if "失策" in group.columns else 0
            
        res_errors = group["結果"].astype(str).str.contains("失策").sum() if "結果" in group.columns else 0
        errors = col_errors + res_errors

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
                "先攻後攻": "不明",
                "得点": 0, "失点": 0, "打数": 0, "安打": 0, "本塁打": 0, "盗塁": 0,
                "自責点": 0, "投球回": 0.0, "失策": 0,
                "has_team_record": False
            }
            
        if games_map[key]["先攻後攻"] == "不明":
            tb_pitch = "不明"
            if "イニング" in group.columns:
                innings = group["イニング"].dropna().astype(str).tolist()
                if any("表" in i for i in innings):
                    tb_pitch = "後攻"
                elif any("裏" in i for i in innings):
                    tb_pitch = "先攻"
            games_map[key]["先攻後攻"] = tb_pitch
        
        games_map[key]["失点"] = runs_allowed
        games_map[key]["自責点"] += er
        games_map[key]["投球回"] += outs
        games_map[key]["失策"] = errors

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
        prev_display = pd.DataFrame()

        if target_year != "通算":
            df_display = df_display[df_display["Year"] == target_year]
            prev_year_str = str(int(target_year) - 1)
            prev_display = df_team_stats[df_team_stats["Year"] == prev_year_str]

        if target_type == "全種別": pass
        elif target_type == "公式戦 (トータル)":
            df_display = df_display[df_display["試合種別"].isin(OFFICIAL_GAME_TYPES)]
            if not prev_display.empty:
                prev_display = prev_display[prev_display["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        else:
            df_display = df_display[df_display["試合種別"] == target_type]
            if not prev_display.empty:
                prev_display = prev_display[prev_display["試合種別"] == target_type]
    else:
        df_display = pd.DataFrame()
        prev_display = pd.DataFrame()

    st.divider()

    # 3. 集計 & メトリクス
    curr = calc_metrics(df_display)
    prev = calc_metrics(prev_display)
    
    viewer_options = []
    if not df_display.empty:
        for index, row in df_display.iterrows():
            s = row["得点"]; l = row["失点"]
            res_txt = "-"
            if s > l: res_txt = " 🔴 勝ち"
            elif s < l: res_txt = " 🔵 敗け"
            else: res_txt = " △ 引き分け"
            df_display.at[index, "勝敗"] = res_txt
            d_str = row["日付"].strftime('%Y-%m-%d')
            label = f"{d_str} vs {row['対戦相手']} ({res_txt}) - {row['試合種別']}"
            viewer_options.append(label)

    has_prev = not prev_display.empty
    
    # ★ 「良し悪し（改善・悪化）」による色分け
    # 防御率・失策・敗戦などは「inverse（マイナスが緑）」に設定
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("試合数", f"{curr['games']}", delta=int(curr['games'] - prev['games']) if has_prev else None)
    m2.metric("勝利", f"{curr['wins']}", delta=int(curr['wins'] - prev['wins']) if has_prev else None)
    m3.metric("敗戦", f"{curr['losses']}", delta=int(curr['losses'] - prev['losses']) if has_prev else None, delta_color="inverse")
    m4.metric("引分", f"{curr['draws']}", delta=int(curr['draws'] - prev['draws']) if has_prev else None, delta_color="off")
    m5.metric("勝率", f"{curr['win_pct']:.3f}", delta=f"{(curr['win_pct'] - prev['win_pct']):+.3f}" if has_prev else None)

    st.markdown("#####   ⚔️   攻撃スタッツ")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("チーム打率", f"{curr['avg']:.3f}", delta=f"{(curr['avg'] - prev['avg']):+.3f}" if has_prev else None)
    a2.metric("平均得点", f"{curr['avg_runs']:.2f}", delta=f"{(curr['avg_runs'] - prev['avg_runs']):+.2f}" if has_prev else None)
    a3.metric("本塁打数", f"{int(curr['hr'])} 本", delta=int(curr['hr'] - prev['hr']) if has_prev else None)
    a4.metric("盗塁数", f"{int(curr['sb'])} 個", delta=int(curr['sb'] - prev['sb']) if has_prev else None)

    st.markdown("#####   🛡️   守備スタッツ")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("チーム防御率", f"{curr['era']:.2f}", delta=f"{(curr['era'] - prev['era']):+.2f}" if has_prev else None, delta_color="inverse")
    d2.metric("平均失点", f"{curr['avg_lost']:.2f}", delta=f"{(curr['avg_lost'] - prev['avg_lost']):+.2f}" if has_prev else None, delta_color="inverse")
    d3.metric("得失点差", f"{int(curr['diff']):+d}", delta=int(curr['diff'] - prev['diff']) if has_prev else None)
    d4.metric("総失策数", f"{int(curr['err'])} 個", delta=int(curr['err'] - prev['err']) if has_prev else None, delta_color="inverse")

    # 4. 試合履歴
    st.subheader(" 📋  試合履歴")
    if not df_display.empty:
        cols = ["日付", "対戦相手", "先攻後攻", "得点", "失点", "失策", "勝敗", "試合種別", "グラウンド"]
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
                tb_val = target_row.get("先攻後攻", "不明")
                
                match_bat = df_batting[(pd.to_datetime(df_batting["日付"]).dt.strftime('%Y-%m-%d') == target_date_str) & (df_batting["対戦相手"] == target_opp)].copy()
                match_pit = df_pitching[(pd.to_datetime(df_pitching["日付"]).dt.strftime('%Y-%m-%d') == target_date_str) & (df_pitching["対戦相手"] == target_opp)].copy()

                if tb_val == "先攻":
                    detected_top = True
                elif tb_val == "後攻":
                    detected_top = False
                else:
                    detected_top = True
                    tr_row = match_bat[match_bat["選手名"] == "チーム記録"]
                    if not tr_row.empty:
                        p_info = str(tr_row.iloc[0]["位置"])
                        if "後攻" in p_info or "裏" in p_info: detected_top = False

                opp_errors = match_bat["結果"].astype(str).str.contains("失策").sum()
                my_errors = target_row.get("失策", 0)

                if has_team_rec:
                    sb_bat = match_bat[match_bat["選手名"] == "チーム記録"].copy()
                    sb_pit = match_pit[match_pit["選手名"] == "チーム記録"].copy()
                    sb_pit["失策"] = my_errors
                    sb_bat["失策"] = opp_errors
                else:
                    sb_bat = match_bat.copy()
                    sb_pit = match_pit.copy()
                    
                    if "失策" not in sb_pit.columns:
                        sb_pit["失策"] = 0
                    if not sb_pit.empty:
                        sb_pit.iloc[0, sb_pit.columns.get_loc("失策")] = my_errors
                        
                    if "失策" not in sb_bat.columns:
                        sb_bat["失策"] = 0
                    if not sb_bat.empty:
                        sb_bat.iloc[0, sb_bat.columns.get_loc("失策")] = opp_errors

                # 🌟 スコアボード用トップアンカー
                st.markdown("<div id='viewer-top' style='scroll-margin-top: 100px;'></div>", unsafe_allow_html=True)

                render_scoreboard(sb_bat, sb_pit, target_date_str, target_row["試合種別"], target_row["グラウンド"], target_opp, is_top_first=detected_top)

                st.divider()
                st.markdown("#### 🏏  打撃成績")
                
                if "スコアラー" in match_bat.columns:
                    valid_scorers = match_bat["スコアラー"].dropna()
                    valid_scorers = valid_scorers[valid_scorers != ""]
                    scorer_name = valid_scorers.iloc[0] if not valid_scorers.empty else "未登録"
                else:
                    scorer_name = "未登録"
                
                st.markdown(f"<div style='text-align: right; color: gray; font-size: 14px; margin-top: -35px; margin-bottom: 10px;'>📝 スコアラー: {scorer_name}</div>", unsafe_allow_html=True)

                personal_bat = match_bat[match_bat["選手名"] != "チーム記録"].copy()
                
                if not personal_bat.empty:
                    active_mask = personal_bat["イニング"] != "ベンチ"
                    active_players = personal_bat.loc[active_mask, "選手名"].unique()
                    
                    df_active = personal_bat[(personal_bat["選手名"].isin(active_players)) & (personal_bat["イニング"] != "ベンチ")].copy()
                    df_bench = personal_bat[~personal_bat["選手名"].isin(active_players)].copy()

                    if not df_active.empty:
                        summary_list = []
                        df_active["選手名_統一"] = df_active["選手名"].astype(str).str.replace(r'[\s ]+', '', regex=True)
                        
                        for player_key, player_group in df_active.groupby("選手名_統一", sort=False):
                            player_name = player_group["選手名"].iloc[0]
                            order_val = player_group["打順"].iloc[0] if "打順" in player_group.columns else ""
                            
                            pos_col = "守備位置" if "守備位置" in player_group.columns else ("守備" if "守備" in player_group.columns else ("位置" if "位置" in player_group.columns else None))
                            seen_pos = []
                            pos_map = {"1":"投", "2":"捕", "3":"一", "4":"二", "5":"三", "6":"遊", "7":"左", "8":"中", "9":"右", "10":"指", "DH":"指"}

                            def get_inn_order(inn_str):
                                m = re.search(r'(\d+)回(表|裏)', str(inn_str))
                                if m:
                                    return int(m.group(1)) * 2 + (0 if m.group(2) == "表" else 1)
                                return 999

                            events = []

                            if pos_col:
                                for _, row in player_group.iterrows():
                                    inn = str(row.get("イニング", ""))
                                    p_val = str(row.get(pos_col, ""))
                                    events.append({"inning": inn, "order": get_inn_order(inn), "pos": p_val, "source": "batting"})

                            for _, row in match_pit.iterrows():
                                inn = str(row.get("イニング", ""))
                                
                                if str(row.get("選手名", "")) == player_name:
                                    events.append({"inning": inn, "order": get_inn_order(inn), "pos": "投", "source": "fielding"})
                                    
                                fielders = str(row.get("処理野手", "")).split("・")
                                positions = str(row.get("守備位置", "")).split("-")
                                
                                if player_name in fielders:
                                    idx = fielders.index(player_name)
                                    if idx < len(positions):
                                        p_val = positions[idx]
                                        events.append({"inning": inn, "order": get_inn_order(inn), "pos": p_val, "source": "fielding"})

                            events.sort(key=lambda x: x["order"])
                            first_batting_pos = None

                            for ev in events:
                                p_clean = ev["pos"].strip().replace(".0", "")
                                if p_clean in pos_map:
                                    p_clean = pos_map[p_clean]
                                
                                if p_clean and p_clean not in ["nan", "None", "", "-"]:
                                    if ev["source"] == "batting" and first_batting_pos is None:
                                        first_batting_pos = p_clean
                                    
                                    if ev["source"] == "batting" and len(seen_pos) > 0 and p_clean == first_batting_pos and p_clean != seen_pos[-1]:
                                        continue
                                        
                                    if not seen_pos or seen_pos[-1] != p_clean:
                                        seen_pos.append(p_clean)

                            pos_val = "".join(seen_pos)
                            
                            pa_list = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "凡退(ゴロ)", "凡退(フライ)", "失策(ゴロ)", "失策(フライ)", "併殺打", "野選", "振り逃げ三振", "打撃妨害"]
                            res_col = player_group.get("結果")
                            tpa = res_col.isin(pa_list).sum() if res_col is not None else 0
                            
                            sb_col = player_group.get("盗塁")
                            sb = int(pd.to_numeric(sb_col, errors='coerce').fillna(0).sum()) if sb_col is not None else 0
                            run_col = player_group.get("得点")
                            run = int(pd.to_numeric(run_col, errors='coerce').fillna(0).sum()) if run_col is not None else 0
                            
                            history_texts = []
                            count = 0
                            pa_list_for_history = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "失策(ゴロ)", "失策(フライ)", "併殺打", "野選", "振り逃げ三振", "打撃妨害"]
                            
                            if res_col is not None:
                                for _, row in player_group.iterrows():
                                    res = str(row.get("結果", ""))
                                    if res in pa_list_for_history:
                                        count += 1
                                        p_dir = str(row.get("打球方向", ""))
                                        if pd.isna(row.get("打球方向")) or p_dir in ["None", "nan"]:
                                            p_dir = ""
                                            
                                        res_short = {
                                            "単打":"安", "二塁打":"二", "三塁打":"三", "本塁打":"本", 
                                            "三振":"振", "凡退(ゴロ)":"ゴ", "凡退(フライ)":"飛", "四球":"四", 
                                            "死球":"死", "犠打(ゴロ)":"犠", "犠打(フライ)":"犠", "犠飛":"犠飛", "振り逃げ三振":"逃", "打撃妨害":"妨",
                                            "失策(ゴロ)":"失", "失策(フライ)":"失", "併殺打":"併", "野選":"野"
                                        }.get(res, res[:1])
                                        
                                        rbi_raw = pd.to_numeric(row.get("打点", 0), errors='coerce')
                                        rbi_val = int(rbi_raw) if pd.notna(rbi_raw) else 0
                                        
                                        disp_text = f"{p_dir}{res_short}"
                                        
                                        is_hit = res in ["単打", "二塁打", "三塁打", "本塁打", "安打"]
                                        
                                        if is_hit:
                                            if rbi_val > 0:
                                                item_str = f"<span style='color: #dc2626; font-weight: bold;'>{count}({disp_text}･{rbi_val}打点)</span>"
                                            else:
                                                item_str = f"<span style='color: #2563eb; font-weight: bold;'>{count}({disp_text})</span>"
                                        else:
                                            item_str = f"{count}({disp_text})"
                                            
                                        history_texts.append(item_str)
                            
                            extra = []
                            if sb > 0: extra.append(f"盗{sb}")
                            if run > 0: 
                                extra.append(f"<span style='color: #16a34a; font-weight: bold;'>得{run}</span>")
                            extra_str = f" [{', '.join(extra)}]" if extra else ""
                            
                            summary_str = " ".join(history_texts) + extra_str
                            
                            summary_list.append({
                                "打順": order_val, 
                                "守備": pos_val, 
                                "選手名": player_name, 
                                "打席": tpa, 
                                "成績詳細": summary_str
                            })

                        df_summary = pd.DataFrame(summary_list)
                        
                        temp_orders = []
                        for i in range(len(df_summary)):
                            current_val = df_summary.at[i, "打順"]
                            temp_orders.append(i + 1 if current_val == 999 else current_val)
                        df_summary["打順"] = temp_orders
                        df_summary = df_summary.sort_values("打順")
                        df_summary["打順"] = df_summary["打順"].astype(int).astype(str)
                        
                        table_html = (
                            "<div style='overflow-x: auto;'>"
                            "<table style='border-collapse: collapse; border: 2px solid #000000; width: 100%; margin-bottom: 20px; font-family: sans-serif; background-color: white;'>"
                            "<thead><tr style='background-color: #e0e0e0;'>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>打順</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>守備</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>選手名</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>打席</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: left; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>成績詳細</th>"
                            "</tr></thead><tbody>"
                        )
                        
                        for _, row in df_summary.iterrows():
                            table_html += (
                                "<tr>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold;'><b>{row['打順']}</b></td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['守備']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['選手名']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['打席']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: left; color: #000000;'>{row['成績詳細']}</td>"
                                "</tr>"
                            )
                            
                        table_html += "</tbody></table></div>"
                        st.markdown(table_html, unsafe_allow_html=True)
                    else:
                        st.info("出場選手の記録がありません")

                    if not df_bench.empty:
                        st.write("")
                        st.markdown("##### 🚌  ベンチ入りメンバー")
                        st.success(", ".join(df_bench["選手名"].unique().tolist()))
                else:
                    st.caption("※ 個人打撃成績なし")

                st.write("")
                st.markdown("#### ⚾  投手成績")
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
                                elif res in ["三振", "振り逃げ三振"]: total_so += 1
                                elif res in ["四球", "死球"]: total_bb += 1
                        
                        total_outs = 0
                        if "アウト数" in group.columns: total_outs += pd.to_numeric(group["アウト数"], errors='coerce').fillna(0).sum()
                        elif "投球回" in group.columns: total_outs += pd.to_numeric(group["投球回"], errors='coerce').fillna(0).sum() * 3
                        
                        fin = f"{int(total_outs//3)}"
                        frac = int(total_outs % 3)
                        if frac == 1: fin += " 1/3"
                        elif frac == 2: fin += " 2/3"

                        final_res = "-"
                        
                        if "勝" in group.columns and pd.to_numeric(group["勝"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "勝"
                        elif "負" in group.columns and pd.to_numeric(group["負"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "負"
                        elif "敗" in group.columns and pd.to_numeric(group["敗"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "負"
                        elif "セーブ" in group.columns and pd.to_numeric(group["セーブ"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "S"
                        elif "S" in group.columns and pd.to_numeric(group["S"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "S"
                        elif "ホールド" in group.columns and pd.to_numeric(group["ホールド"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "H"
                        elif "H" in group.columns and pd.to_numeric(group["H"], errors='coerce').fillna(0).sum() > 0:
                            final_res = "H"
                        else:
                            for col in ["勝敗", "責任"]:
                                if col in group.columns:
                                    r_str = "".join(group[col].dropna().astype(str).tolist())
                                    if "勝" in r_str or "○" in r_str: final_res = "勝"
                                    elif "負" in r_str or "敗" in r_str or "●" in r_str: final_res = "負"
                                    elif "S" in r_str or "セーブ" in r_str: final_res = "S"
                                    elif "H" in r_str or "ホールド" in r_str: final_res = "H"
                                    if final_res != "-":
                                        break
                        
                        summary_list.append({"投手名": p_name, "結果": final_res, "回": fin, "球数": int(balls), "被安": int(total_hits), "奪三": int(total_so), "四死": int(total_bb), "失点": int(runs), "自責": int(er)})
                    
                    st.table(pd.DataFrame(summary_list).set_index("投手名")[["結果", "回", "球数", "被安", "奪三", "四死", "失点", "自責"]])

                    st.write("")
                    st.markdown("##### 📊 全イニング 対戦詳細履歴（守備）")
                    
                    # 🌟 画面右下に追従（フローティング）表示する「スコア画面に戻る」ボタン
                    st.markdown(
                        """
                        <style>
                        .floating-top-btn {
                            position: fixed;
                            bottom: 30px;
                            right: 30px;
                            z-index: 99999;
                            background-color: #1e3a8a;
                            color: white !important;
                            padding: 12px 20px;
                            border-radius: 30px;
                            text-decoration: none !important;
                            font-weight: bold;
                            font-size: 15px;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                            transition: all 0.2s ease-in-out;
                        }
                        .floating-top-btn:hover {
                            background-color: #2563eb;
                            transform: scale(1.05);
                            box-shadow: 0 6px 16px rgba(0,0,0,0.4);
                        }
                        </style>
                        <a href="#viewer-top" class="floating-top-btn">⬆ スコア画面に戻る</a>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    history_df = match_pit[
                        match_pit["種別"].str.contains("詳細", na=False)
                    ].copy()

                    if not history_df.empty:
                        for inn in [f"{i}回" for i in range(1, 10)] + ["延長"]:
                            inn_df = history_df[history_df["イニング"].astype(str).str.startswith(inn)]
                            if not inn_df.empty:
                                inn_id = inn.replace("回", "")
                                st.markdown(f"<div id='inning-{inn_id}' style='scroll-margin-top: 100px;'></div>", unsafe_allow_html=True)
                                
                                st.write(f"**【{inn}】**")
                                display_items = []
                                for _, row in inn_df.iterrows():
                                    b_idx = str(row["種別"]).split(":")[1].replace("番打者", "") if ":" in str(row["種別"]) else "?"
                                    
                                    raw_res = str(row.get('結果', ''))
                                    pos_str = str(row.get('打球方向', '')) or str(row.get('守備位置', ''))
                                    
                                    if pos_str and pos_str not in ["nan", "None", ""]:
                                        raw_res = f"{raw_res}({pos_str})"
                                    
                                    fielder_str = str(row.get('処理野手', ''))
                                    if fielder_str and fielder_str not in ["nan", "None", ""]:
                                        res_text = f"{raw_res} [{fielder_str}]"
                                    else:
                                        res_text = raw_res
                                        
                                    runs = pd.to_numeric(row.get('失点', 0), errors='coerce')
                                    runs = int(runs) if pd.notna(runs) else 0
                                    if runs > 0:
                                        res_text = f"{res_text} 💥失点{runs}"
                                        
                                    display_items.append({
                                        "打順": f"{b_idx}番", 
                                        "投手": row["選手名"], 
                                        "結果": res_text
                                    })
                                
                                df_disp = pd.DataFrame(display_items).T
                                
                                def highlight_timely(val):
                                    if isinstance(val, str) and "💥失点" in val:
                                        return "color: red; font-weight: bold;"
                                    return ""
                                
                                try:
                                    styled_df = df_disp.style.map(highlight_timely)
                                except AttributeError:
                                    styled_df = df_disp.style.applymap(highlight_timely)
                                    
                                st.dataframe(styled_df, use_container_width=True)
                    else:
                        st.caption("詳細データはまだありません。")
                else:
                    st.caption("※ 個人投手成績なし")