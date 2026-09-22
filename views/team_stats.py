import re
import pandas as pd
import streamlit as st

from config.settings import OFFICIAL_GAME_TYPES
from utils.players import get_stats_active_players
from utils.ui import render_scoreboard


# ★ イニング文字列を計算用数値に変換する関数
def parse_inn_order(inn_str):
    s = str(inn_str).strip()
    if not s or s in ["nan", "None", "まとめ入力", "ベンチ", "試合前"]:
        return 9999
    m = re.search(r'(\d+)', s)
    num = int(m.group(1)) if m else 99
    is_ext = 100 if "延長" in s else 0
    sub = 0 if "表" in s else (1 if "裏" in s else 0.5)
    return is_ext + num * 2 + sub


# ★ 集計計算を共通化
def calc_metrics(df):
    if df.empty:
        return {
            "games": 0, "wins": 0, "losses": 0, "draws": 0,
            "win_pct": 0.0, "avg": 0.0, "avg_runs": 0.0,
            "hr": 0, "sb": 0, "era": 0.0, "avg_lost": 0.0,
            "diff": 0, "err": 0, "total_score": 0, "total_lost": 0
        }

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

        if s > l:
            wins += 1
        elif s < l:
            losses += 1
        else:
            draws += 1

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

    # 1. データ準備 & 初期キーチェック
    expected_bat_cols = [
        "日付", "イニング", "打順", "打者名", "投手名", "選手名", "位置", "守備位置",
        "結果", "打球方向", "打点", "得点", "グラウンド", "対戦相手", "試合種別", "スコアラー",
        "球数", "ストライク", "ボール", "盗塁"
    ]
    for col in expected_bat_cols:
        if col not in df_batting.columns:
            df_batting[col] = ""

    expected_pit_cols = [
        "日付", "イニング", "投手名", "打順", "打者名", "選手名", "結果",
        "失点", "自責点", "被安打", "奪三振", "アウト数", "種別", "対戦相手", "試合種別", "グラウンド"
    ]
    for col in expected_pit_cols:
        if col not in df_pitching.columns:
            df_pitching[col] = ""

    if df_batting.empty and df_pitching.empty:
        st.info("データがまだありません。")
        return

    games_map = {}

    # --- A. 打撃データから集計 ---
    df_b_work = df_batting.copy()
    df_b_work["DateStr"] = pd.to_datetime(df_b_work["日付"], errors='coerce').dt.strftime('%Y-%m-%d')

    b_p_col = "打者名" if "打者名" in df_b_work.columns else "選手名"

    for (d_str, opp, m_type), group in df_b_work.groupby(["DateStr", "対戦相手", "試合種別"]):
        if not d_str or pd.isna(d_str):
            continue

        team_rec_rows = group[(group[b_p_col] == "チーム記録") | (group.get("選手名", "") == "チーム記録")]
        is_team_record = False
        runs = 0
        team_rec_hits = 0
        team_rec_ab = 0
        team_rec_hr = 0

        if not team_rec_rows.empty:
            is_team_record = True
            runs = pd.to_numeric(team_rec_rows["得点"], errors='coerce').fillna(0).sum()
            
            # 結果列から単打などのチーム記録を集計
            hit_results = ["単打", "二塁打", "三塁打", "本塁打", "安打"]
            ab_results = ["単打", "二塁打", "三塁打", "本塁打", "三振", "凡退", "失策", "併殺打", "野選", "振り逃げ三振", "犠飛"]
            
            for _, r_row in team_rec_rows.iterrows():
                r_str = str(r_row.get("結果", "")).strip()
                if r_str in hit_results:
                    team_rec_hits += 1
                    team_rec_ab += 1
                    if r_str == "本塁打":
                        team_rec_hr += 1
                elif r_str in ab_results or "凡退" in r_str or "失策" in r_str:
                    team_rec_ab += 1
        else:
            valid_batting = group[group["イニング"] != "まとめ入力"] if "イニング" in group.columns else group
            runs = pd.to_numeric(valid_batting["得点"], errors='coerce').fillna(0).sum()

        individuals = group[(group[b_p_col] != "チーム記録") & (group.get("選手名", "") != "チーム記録")]
        total_hits = team_rec_hits; total_ab = team_rec_ab; total_hr = team_rec_hr; total_sb = 0

        if not individuals.empty:
            ab_results = [
                "単打", "二塁打", "三塁打", "本塁打", "三振", 
                "凡退", "失策", "併殺打", "野選", "振り逃げ三振", "犠飛"
            ]
            hit_results = ["単打", "二塁打", "三塁打", "本塁打", "安打"]

            for _, row in individuals.iterrows():
                res_str = str(row.get("結果", "")).strip()

                ab_val = pd.to_numeric(row.get("打数", 0), errors='coerce')
                hits_val = pd.to_numeric(row.get("安打", 0), errors='coerce')
                hr_val = pd.to_numeric(row.get("本塁打", 0), errors='coerce')

                ab = int(ab_val) if pd.notna(ab_val) else 0
                hits = int(hits_val) if pd.notna(hits_val) else 0
                hr = int(hr_val) if pd.notna(hr_val) else 0

                # 🌟 盗塁数の判定ロジック強化（「盗塁」列の数値 または 「結果」列が"盗塁"）
                sb_val = pd.to_numeric(row.get("盗塁", 0), errors='coerce')
                if pd.notna(sb_val) and sb_val > 0:
                    sb = int(sb_val)
                elif res_str == "盗塁" or ("盗塁" in res_str and "盗塁死" not in res_str):
                    sb = 1
                else:
                    sb = 0

                if ab > 0 or hits > 0:
                    total_ab += ab
                    total_hits += hits
                    total_hr += hr
                    total_sb += sb
                else:
                    if res_str in ab_results or "凡退" in res_str or "失策" in res_str:
                        total_ab += 1

                    if res_str in hit_results:
                        total_hits += 1
                        if res_str == "本塁打":
                            total_hr += 1

                    total_sb += sb

        top_bottom = "不明"
        if "イニング" in group.columns:
            innings = group["イニング"].dropna().astype(str).tolist()
            if any("表" in i for i in innings):
                top_bottom = "先攻"
            elif any("裏" in i for i in innings):
                top_bottom = "後攻"

        if top_bottom == "不明" and is_team_record and not team_rec_rows.empty:
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

    # --- B. 投手データから集計 (【修正箇所】投球回／アウト数の自動判定を強化) ---
    df_p_work = df_pitching.copy()
    df_p_work["DateStr"] = pd.to_datetime(df_p_work["日付"], errors='coerce').dt.strftime('%Y-%m-%d')

    p_p_col = "投手名" if "投手名" in df_p_work.columns else "選手名"

    # アウト数カウント用の判定用リスト
    out_1 = ["凡退", "凡退(ゴロ)", "凡退(フライ)", "三振", "振り逃げ三振", "犠打", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "牽制死"]
    out_2 = ["併殺打", "併殺"]

    for (d_str, opp, m_type), group in df_p_work.groupby(["DateStr", "対戦相手", "試合種別"]):
        if not d_str or pd.isna(d_str):
            continue

        # 🌟 仕様変更：「失点」列の数値を直接合計してチーム総失点とする
        if "失点" in group.columns:
            runs_allowed = int(pd.to_numeric(group["失点"], errors='coerce').fillna(0).sum())
        else:
            runs_allowed = 0

        # 失策（エラー）の集計
        col_errors = pd.to_numeric(group["失策"], errors='coerce').fillna(0).sum() if "失策" in group.columns else 0
        res_errors = group["結果"].astype(str).str.contains("失策").sum() if "結果" in group.columns else 0
        errors = col_errors + res_errors

        individuals_p = group[(group[p_p_col] != "チーム記録") & (group.get("選手名", "") != "チーム記録")]

        er = 0; outs = 0.0
        if not individuals_p.empty:
            if "自責点" in individuals_p.columns:
                er = pd.to_numeric(individuals_p["自責点"], errors='coerce').fillna(0).sum()

            total_outs = 0
            for _, r in individuals_p.iterrows():
                res = str(r.get("結果", "")).strip()
                r_type = str(r.get("種別", "")).strip()
                raw_outs = pd.to_numeric(r.get("アウト数", 0), errors='coerce')

                # A. まとめ入力行
                if res == "まとめ" or r_type == "まとめ":
                    if pd.notna(raw_outs) and raw_outs > 0:
                        total_outs += int(raw_outs)
                    elif "投球回" in r and pd.notna(pd.to_numeric(r.get("投球回"), errors='coerce')):
                        total_outs += int(pd.to_numeric(r.get("投球回"), errors='coerce') * 3)
                # B. スタメン・交代等
                elif "ダミー" in r_type or "スタメン" in res or "交代" in res or "ベンチ" in res:
                    continue
                # C. 通常のプレイ行（アウト数判定）
                else:
                    if pd.notna(raw_outs) and raw_outs > 0:
                        total_outs += int(raw_outs)
                    elif res in out_1:
                        total_outs += 1
                    elif res in out_2:
                        total_outs += 2

            outs = total_outs / 3

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
        df_team_stats["日付"] = pd.to_datetime(df_team_stats["日付"], errors='coerce')
        df_team_stats = df_team_stats.sort_values("日付", ascending=False)

    # 2. フィルタリング
        if not df_team_stats.empty:
            df_team_stats["Year"] = df_team_stats["日付"].dt.year.astype(str)
            all_years = sorted([y for y in df_team_stats["Year"].unique() if y and y != "nan"], reverse=True)

            c_filter1, c_filter2 = st.columns(2)
            with c_filter1:
                # 🌟 データが存在する場合は最新年（インデックス 1）をデフォルトに設定
                default_idx = 1 if len(all_years) > 0 else 0
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
            try:
                prev_year_str = str(int(target_year) - 1)
                prev_display = df_team_stats[df_team_stats["Year"] == prev_year_str]
            except ValueError:
                prev_display = pd.DataFrame()

        if target_type == "全種別":
            pass
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
            if s > l:
                res_txt = " 🔴 勝ち"
            elif s < l:
                res_txt = " 🔵 敗け"
            else:
                res_txt = " △ 引き分け"
            df_display.at[index, "勝敗"] = res_txt
            d_str = row["日付"].strftime('%Y-%m-%d') if pd.notna(row["日付"]) else ""
            label = f"{d_str} vs {row['対戦相手']} ({res_txt}) - {row['試合種別']}"
            viewer_options.append(label)

    has_prev = not prev_display.empty

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
        df_disp_show = df_display.copy()
        df_disp_show["日付"] = pd.to_datetime(df_disp_show["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        cols = ["日付", "対戦相手", "先攻後攻", "得点", "失点", "失策", "勝敗", "試合種別", "グラウンド"]
        st.dataframe(df_disp_show[cols], use_container_width=True, hide_index=True)
    else:
        st.write("履歴データがありません")

    # 5. 試合詳細ビューワー
    st.markdown("### 📝 試合詳細ビューワー")

    if viewer_options:
        if "detail_selector_pill" not in st.session_state or st.session_state["detail_selector_pill"] not in viewer_options:
            st.session_state["detail_selector_pill"] = viewer_options[0]

        current_selected = st.session_state.get("detail_selector_pill", viewer_options[0])
        viewer_btn_label = f"🟢 {current_selected} 🔽" if current_selected else "詳細を確認したい試合を選択 🔽"

        with st.popover(viewer_btn_label, use_container_width=True):
            st.markdown("##### 📝 詳細を確認したい試合を選択")
            st.pills(
                "試合選択",
                viewer_options,
                key="detail_selector_pill",
                label_visibility="collapsed"
            )

        selected_label = st.session_state.get("detail_selector_pill")

        if selected_label:
            try:
                parts = selected_label.split(" vs ")
                target_date_str = parts[0]
                rest = parts[1]
                target_opp = rest.split(" (")[0]
            except Exception:
                st.error("データの特定に失敗しました。")
                target_date_str = ""; target_opp = ""

            if target_date_str:
                matched_rows = df_display[
                    (pd.to_datetime(df_display["日付"], errors='coerce').dt.strftime('%Y-%m-%d') == target_date_str) & 
                    (df_display["対戦相手"] == target_opp)
                ]

                if matched_rows.empty:
                    st.warning("該当する試合データが見つかりませんでした。")
                    return

                target_row = matched_rows.iloc[0]
                has_team_rec = target_row["has_team_record"]
                tb_val = target_row.get("先攻後攻", "不明")
                target_m_type = target_row.get("試合種別", "")

                df_b_filtered = df_batting.copy()
                df_b_filtered["DateStr"] = pd.to_datetime(df_b_filtered["日付"], errors='coerce').dt.strftime('%Y-%m-%d')

                df_p_filtered = df_pitching.copy()
                df_p_filtered["DateStr"] = pd.to_datetime(df_p_filtered["日付"], errors='coerce').dt.strftime('%Y-%m-%d')

                match_bat = df_b_filtered[
                    (df_b_filtered["DateStr"] == target_date_str) & 
                    (df_b_filtered["対戦相手"] == target_opp) & 
                    (df_b_filtered["試合種別"] == target_m_type)
                ].copy()

                match_pit = df_p_filtered[
                    (df_p_filtered["DateStr"] == target_date_str) & 
                    (df_p_filtered["対戦相手"] == target_opp) & 
                    (df_p_filtered["試合種別"] == target_m_type)
                ].copy()

                if tb_val == "先攻":
                    detected_top = True
                elif tb_val == "後攻":
                    detected_top = False
                else:
                    detected_top = True
                    b_p_name = "打者名" if "打者名" in match_bat.columns else "選手名"
                    tr_row = match_bat[match_bat[b_p_name] == "チーム記録"]
                    if not tr_row.empty:
                        p_info = str(tr_row.iloc[0].get("位置", ""))
                        if "後攻" in p_info or "裏" in p_info:
                            detected_top = False

                opp_errors = match_bat["結果"].astype(str).str.contains("失策").sum() if "結果" in match_bat.columns else 0
                my_errors = target_row.get("失策", 0)

                b_p_name = "打者名" if "打者名" in match_bat.columns else "選手名"
                p_p_name = "投手名" if "投手名" in match_pit.columns else "選手名"

                if has_team_rec:
                    sb_bat = match_bat.copy() # 個人の安打も反映させるため全行コピーに変更
                    sb_pit = match_pit.copy()

                    sb_pit["失策"] = 0
                    if not sb_pit.empty:
                        sb_pit.iloc[0, sb_pit.columns.get_loc("失策")] = my_errors

                    sb_bat["失策"] = 0
                    if not sb_bat.empty:
                        sb_bat.iloc[0, sb_bat.columns.get_loc("失策")] = opp_errors
                else:
                    sb_bat = match_bat.copy()
                    sb_pit = match_pit.copy()

                    sb_pit["失策"] = 0
                    if not sb_pit.empty:
                        sb_pit.iloc[0, sb_pit.columns.get_loc("失策")] = my_errors

                    sb_bat["失策"] = 0
                    if not sb_bat.empty:
                        sb_bat.iloc[0, sb_bat.columns.get_loc("失策")] = opp_errors

                st.markdown("<div id='viewer-top' style='scroll-margin-top: 100px;'></div>", unsafe_allow_html=True)

                # スコアボード描画
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

                personal_bat = match_bat[match_bat[b_p_name] != "チーム記録"].copy()

                if not personal_bat.empty:
                    bench_mask = (
                        (personal_bat.get("結果") == "ベンチ") | 
                        (personal_bat.get("種別") == "ベンチ") | 
                        (personal_bat.get("イニング") == "ベンチ")
                    )

                    df_bench = personal_bat[bench_mask].copy()
                    df_active = personal_bat[~bench_mask].copy()

                    if not df_active.empty:
                        summary_list = []
                        df_active["選手名_統一"] = df_active[b_p_name].astype(str).str.replace(r'[\s ]+', '', regex=True)

                        for player_key, player_group in df_active.groupby("選手名_統一", sort=False):
                            player_name = player_group[b_p_name].iloc[0]
                            order_val = player_group["打順"].iloc[0] if "打順" in player_group.columns else ""

                            pos_map = {
                                "1": "投", "投手": "投", "投": "投",
                                "2": "捕", "捕手": "捕", "捕": "捕",
                                "3": "一", "一塁": "一", "一塁手": "一", "一": "一",
                                "4": "二", "二塁": "二", "二塁手": "二", "二": "二",
                                "5": "三", "三塁": "三", "三塁手": "三", "三": "三",
                                "6": "遊", "遊撃": "遊", "遊撃手": "遊", "遊": "遊",
                                "7": "左", "左翼": "左", "左翼手": "左", "左": "左",
                                "8": "中", "中堅": "中", "中堅手": "中", "中": "中",
                                "9": "右", "右翼": "右", "右翼手": "右", "右": "右",
                                "10": "指", "DH": "指", "指名打者": "指", "指": "指",
                                "打": "打", "代打": "打",
                                "走": "走", "代走": "走"
                            }

                            def get_inn_order(inn_str):
                                m = re.search(r'(\d+)回(表|裏)', str(inn_str))
                                if m:
                                    return int(m.group(1)) * 2 + (0 if m.group(2) == "表" else 1)
                                return 999

                            seen_pos = []; events = []

                            for _, row in player_group.iterrows():
                                inn = str(row.get("イニング", ""))
                                p_val = ""
                                for c in ["位置", "守備位置", "守備"]:
                                    if c in row and pd.notna(row[c]):
                                        v = str(row[c]).strip()
                                        if v:
                                            p_val = v; break
                                if p_val:
                                    events.append({"inning": inn, "order": get_inn_order(inn), "pos": p_val, "source": "batting"})

                            for _, row in match_pit.iterrows():
                                inn = str(row.get("イニング", ""))
                                p_pit_name = str(row.get("投手名", row.get("選手名", "")))
                                if p_pit_name == player_name:
                                    events.append({"inning": inn, "order": get_inn_order(inn), "pos": "投", "source": "fielding"})

                                fielders = str(row.get("処理野手", "")).split("・")
                                positions = str(row.get("守備位置", "")).split("-")

                                if player_name in fielders:
                                    idx = fielders.index(player_name)
                                    if idx < len(positions):
                                        p_val = positions[idx].strip()
                                        if p_val:
                                            events.append({"inning": inn, "order": get_inn_order(inn), "pos": p_val, "source": "fielding"})

                            events.sort(key=lambda x: x["order"])
                            first_batting_pos = None

                            for ev in events:
                                p_raw = ev["pos"].strip().replace(".0", "")
                                
                                if p_raw in pos_map:
                                    p_clean = pos_map[p_raw]

                                    if ev["source"] == "batting" and first_batting_pos is None:
                                        first_batting_pos = p_clean

                                    if ev["source"] == "batting" and len(seen_pos) > 0 and p_clean == first_batting_pos and p_clean != seen_pos[-1]:
                                        continue

                                    if not seen_pos or seen_pos[-1] != p_clean:
                                        seen_pos.append(p_clean)

                            pos_val = "".join(seen_pos) if seen_pos else "―"

                            pa_list = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "凡退(ゴロ)", "凡退(フライ)", "凡退", "失策(ゴロ)", "失策(フライ)", "失策", "併殺打", "野選", "振り逃げ三振", "打撃妨害"]
                            res_col = player_group.get("結果") if "結果" in player_group.columns else None
                            tpa = res_col.isin(pa_list).sum() if res_col is not None else 0

                            # 個人詳細表示での盗塁数の集計補正
                            sb_col = player_group.get("盗塁")
                            sb_num = int(pd.to_numeric(sb_col, errors='coerce').fillna(0).sum()) if sb_col is not None else 0
                            sb_res_count = int(player_group["結果"].astype(str).str.contains("盗塁").sum()) if "結果" in player_group.columns else 0
                            sb = max(sb_num, sb_res_count)

                            run_col = player_group.get("得点")
                            run = int(pd.to_numeric(run_col, errors='coerce').fillna(0).sum()) if run_col is not None else 0

                            history_texts = []
                            count = 0
                            pa_list_for_history = ["凡退(ゴロ)", "凡退(フライ)", "凡退", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "失策(ゴロ)", "失策(フライ)", "失策", "併殺打", "野選", "振り逃げ三振", "打撃妨害"]

                            if res_col is not None:
                                for _, row in player_group.iterrows():
                                    res = str(row.get("結果", ""))
                                    if res in pa_list_for_history:
                                        count += 1
                                        p_dir = str(row.get("打球方向", ""))
                                        if pd.isna(row.get("打球方向")) or p_dir in ["None", "nan"]:
                                            p_dir = ""

                                        res_short = {
                                            "単打": "安", "二塁打": "二", "三塁打": "三", "本塁打": "本",
                                            "三振": "振", "凡退(ゴロ)": "ゴ", "凡退(フライ)": "飛", "凡退": "凡", "四球": "四",
                                            "死球": "死", "犠打(ゴロ)": "犠", "犠打(フライ)": "犠", "犠飛": "犠飛", "振り逃げ三振": "逃", "打撃妨害": "妨",
                                            "失策(ゴロ)": "失", "失策(フライ)": "失", "失策": "失", "併殺打": "併", "野選": "野"
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
                            if sb > 0:
                                extra.append(f"<span style='color: #9333ea; font-weight: bold;'>盗{sb}</span>")
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

                        if not df_summary.empty:
                            match_bat_copy = match_bat.copy()
                            match_bat_copy["選手名_統一"] = match_bat_copy[b_p_name].astype(str).str.replace(r'[\s ]+', '', regex=True)

                            if "イニング" in match_bat_copy.columns:
                                match_bat_copy["inn_order"] = match_bat_copy["イニング"].apply(parse_inn_order)
                            else:
                                match_bat_copy["inn_order"] = 9999

                            match_bat_copy["row_id"] = range(len(match_bat_copy))

                            first_app_bat = match_bat_copy.groupby("選手名_統一").agg(
                                min_inn=("inn_order", "min"),
                                min_row=("row_id", "min")
                            ).reset_index()

                            bat_inn_map = dict(zip(first_app_bat["選手名_統一"], first_app_bat["min_inn"]))
                            bat_row_map = dict(zip(first_app_bat["選手名_統一"], first_app_bat["min_row"]))

                            match_pit_copy = match_pit.copy()
                            p_p_col_temp = "投手名" if "投手名" in match_pit_copy.columns else "選手名"
                            match_pit_copy["選手名_統一"] = match_pit_copy[p_p_col_temp].astype(str).str.replace(r'[\s ]+', '', regex=True)

                            if "イニング" in match_pit_copy.columns:
                                match_pit_copy["inn_order"] = match_pit_copy["イニング"].apply(parse_inn_order)
                            else:
                                match_pit_copy["inn_order"] = 9999

                            match_pit_copy["row_id"] = range(len(match_pit_copy))

                            first_app_pit = match_pit_copy[match_pit_copy["選手名_統一"] != "チーム記録"].groupby("選手名_統一").agg(
                                min_inn=("inn_order", "min"),
                                min_row=("row_id", "min")
                            ).reset_index()

                            pit_inn_map = dict(zip(first_app_pit["選手名_統一"], first_app_pit["min_inn"]))
                            pit_row_map = dict(zip(first_app_pit["選手名_統一"], first_app_pit["min_row"]))

                            df_summary["選手名_統一"] = df_summary["選手名"].astype(str).str.replace(r'[\s ]+', '', regex=True)

                            def calc_first_inn(p_name):
                                b_i = bat_inn_map.get(p_name, 9999)
                                p_i = pit_inn_map.get(p_name, 9999)
                                return min(b_i, p_i)

                            def calc_first_row(p_name):
                                b_i = bat_inn_map.get(p_name, 9999)
                                p_i = pit_inn_map.get(p_name, 9999)
                                b_r = bat_row_map.get(p_name, 9999)
                                p_r = pit_row_map.get(p_name, 9999)
                                if p_i < b_i:
                                    return p_r
                                elif b_i < p_i:
                                    return b_r
                                else:
                                    return min(b_r, p_r)

                            df_summary["登場イニング"] = df_summary["選手名_統一"].apply(calc_first_inn)
                            df_summary["登場行順"] = df_summary["選手名_統一"].apply(calc_first_row)

                            df_summary["打順"] = pd.to_numeric(df_summary["打順"], errors='coerce')

                            df_summary = df_summary.sort_values(["打順", "登場イニング", "登場行順"]).reset_index(drop=True)
                            df_summary["打順"] = df_summary["打順"].fillna(0).astype(int).astype(str).replace("0", "")

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
                        st.success(", ".join(df_bench[b_p_name].unique().tolist()))
                else:
                    st.caption("※ 個人打撃成績なし")

                st.write("")
                st.markdown("#### ⚾  投手成績")
                personal_pit = match_pit[match_pit[p_p_name] != "チーム記録"].copy()
                if not personal_pit.empty:
                    if "投手名" not in personal_pit.columns:
                        personal_pit["投手名"] = personal_pit[p_p_name]
                    else:
                        personal_pit["投手名"] = personal_pit["投手名"].replace("", pd.NA).fillna(personal_pit[p_p_name])
                    personal_pit["投手名"] = personal_pit["投手名"].fillna("不明")

                    if "イニング" in personal_pit.columns:
                        personal_pit["inn_order"] = personal_pit["イニング"].apply(parse_inn_order)
                        personal_pit["row_id"] = range(len(personal_pit))
                        first_pit = personal_pit.groupby("投手名").agg(
                            min_inn=("inn_order", "min"),
                            min_row=("row_id", "min")
                        ).reset_index()
                        pit_order_map = dict(zip(first_pit["投手名"], first_pit["min_inn"] * 10000 + first_pit["min_row"]))
                        personal_pit["pit_sort_order"] = personal_pit["投手名"].map(pit_order_map)
                        personal_pit = personal_pit.sort_values("pit_sort_order")

                    summary_list = []
                    for p_name_val, group in personal_pit.groupby("投手名", sort=False):
                        clean_p_val = re.sub(r'[\s ]+', '', str(p_name_val)).split("(")[0].strip()

                        # 1. 投手シートから球数・ストライク・ボールを取得
                        balls = pd.to_numeric(group.get("球数", 0), errors='coerce').fillna(0).sum()
                        s_cnt = pd.to_numeric(group.get("ストライク", 0), errors='coerce').fillna(0).sum()
                        b_cnt = pd.to_numeric(group.get("ボール", 0), errors='coerce').fillna(0).sum()

                        # 2. 打撃シートから投手名が一致する行を照合
                        if not match_bat.empty and "投手名" in match_bat.columns:
                            match_bat_copy = match_bat.copy()
                            match_bat_copy["_p_name_clean"] = match_bat_copy["投手名"].astype(str).apply(lambda x: re.sub(r'[\s ]+', '', str(x)).split("(")[0].strip())
                            b_sub = match_bat_copy[match_bat_copy["_p_name_clean"] == clean_p_val]
                        else:
                            b_sub = pd.DataFrame()

                        if not b_sub.empty:
                            b_pitches = pd.to_numeric(b_sub.get("球数", 0), errors='coerce').fillna(0).sum()
                            b_strikes = pd.to_numeric(b_sub.get("ストライク", 0), errors='coerce').fillna(0).sum()
                            b_balls = pd.to_numeric(b_sub.get("ボール", 0), errors='coerce').fillna(0).sum()

                            if balls == 0 and b_pitches > 0:
                                balls = b_pitches
                            if s_cnt == 0 and b_strikes > 0:
                                s_cnt = b_strikes
                            if b_cnt == 0 and b_balls > 0:
                                b_cnt = b_balls

                        if balls == 0:
                            balls = s_cnt + b_cnt

                        strike_rate = (s_cnt / balls * 100) if balls > 0 else 0.0
                        strike_rate_str = f"{strike_rate:.1f}%"

                        # 3. 失点と自責点
                        runs = int(pd.to_numeric(group["失点"], errors='coerce').fillna(0).sum()) if "失点" in group.columns else 0

                        er_col = "自責点" if "自責点" in group.columns else ("自責" if "自責" in group.columns else None)
                        er = int(pd.to_numeric(group[er_col], errors='coerce').fillna(0).sum()) if er_col else 0

                        # 4. 結果列からの投球回（アウト数）、被安打、奪三振、四死球の自動集計
                        total_outs = 0; total_hits = 0; total_so = 0; total_bb = 0
                        
                        out_1_det = ["凡退", "凡退(ゴロ)", "凡退(フライ)", "三振", "振り逃げ三振", "犠打", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "牽制死"]
                        out_2_det = ["併殺打", "併殺"]
                        hit_list = ["安打", "単打", "二塁打", "三塁打", "本塁打"]

                        for _, row in group.iterrows():
                            res = str(row.get("結果", "")).strip()
                            r_type = str(row.get("種別", "")).strip()

                            raw_outs = pd.to_numeric(row.get("アウト数", 0), errors='coerce')
                            raw_h = pd.to_numeric(row.get("被安打", 0), errors='coerce')
                            raw_so = pd.to_numeric(row.get("奪三振", 0), errors='coerce')
                            raw_bb = pd.to_numeric(row.get("与四球", 0), errors='coerce')

                            # A. まとめ入力行
                            if res == "まとめ" or r_type == "まとめ":
                                if pd.notna(raw_outs) and raw_outs > 0:
                                    total_outs += int(raw_outs)
                                elif "投球回" in row and pd.notna(pd.to_numeric(row.get("投球回"), errors='coerce')):
                                    total_outs += int(pd.to_numeric(row.get("投球回"), errors='coerce') * 3)

                                if pd.notna(raw_h) and raw_h > 0:
                                    total_hits += int(raw_h)
                                if pd.notna(raw_so) and raw_so > 0:
                                    total_so += int(raw_so)
                                if pd.notna(raw_bb) and raw_bb > 0:
                                    total_bb += int(raw_bb)

                            # B. 非プレイ行
                            elif "ダミー" in r_type or "スタメン" in res or "交代" in res or "ベンチ" in res:
                                continue

                            # C. 個別打者イベント行
                            else:
                                if pd.notna(raw_outs) and raw_outs > 0:
                                    total_outs += int(raw_outs)
                                elif res in out_1_det:
                                    total_outs += 1
                                elif res in out_2_det:
                                    total_outs += 2

                                if pd.notna(raw_h) and raw_h > 0:
                                    total_hits += int(raw_h)
                                elif res in hit_list or "被安打" in str(row.get("被安打", "")) or "被安打" in r_type:
                                    total_hits += 1

                                if pd.notna(raw_so) and raw_so > 0:
                                    total_so += int(raw_so)
                                elif res in ["三振", "振り逃げ三振"]:
                                    total_so += 1

                                if pd.notna(raw_bb) and raw_bb > 0:
                                    total_bb += int(raw_bb)
                                elif res in ["四球", "死球"]:
                                    total_bb += 1

                        fin = f"{int(total_outs // 3)}"
                        frac = int(total_outs % 3)
                        if frac == 1:
                            fin += " 1/3"
                        elif frac == 2:
                            fin += " 2/3"

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
                                    if "勝" in r_str or "○" in r_str:
                                        final_res = "勝"
                                    elif "負" in r_str or "敗" in r_str or "●" in r_str:
                                        final_res = "負"
                                    elif "S" in r_str or "セーブ" in r_str:
                                        final_res = "S"
                                    elif "H" in r_str or "ホールド" in r_str:
                                        final_res = "H"
                                    if final_res != "-":
                                        break

                        summary_list.append({
                            "投手名": p_name_val, "結果": final_res, "回": fin, "球数": int(balls),
                            "S%": strike_rate_str,
                            "被安": int(total_hits), "奪三": int(total_so), "四死": int(total_bb),
                            "失点": int(runs), "自責": int(er)
                        })

                    if summary_list:
                        df_pit_sum = pd.DataFrame(summary_list)
                        pit_table_html = (
                            "<div style='overflow-x: auto;'>"
                            "<table style='border-collapse: collapse; border: 2px solid #000000; width: 100%; margin-bottom: 20px; font-family: sans-serif; background-color: white;'>"
                            "<thead><tr style='background-color: #e0e0e0;'>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>投手名</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>結果</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>回</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>球数</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>S%</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>被安</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>奪三</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>四死</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>失点</th>"
                            "<th style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold; border-bottom: 2px solid #000000;'>自責</th>"
                            "</tr></thead><tbody>"
                        )

                        for _, row in df_pit_sum.iterrows():
                            pit_table_html += (
                                "<tr>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000; font-weight: bold;'><b>{row['投手名']}</b></td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['結果']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['回']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['球数']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['S%']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['被安']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['奪三']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['四死']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['失点']}</td>"
                                f"<td style='border: 1px solid #444444; font-size: 18px; padding: 10px; text-align: center; color: #000000;'>{row['自責']}</td>"
                                "</tr>"
                            )

                        pit_table_html += "</tbody></table></div>"
                        st.markdown(pit_table_html, unsafe_allow_html=True)

                        st.write("")
                        st.markdown("##### 📊 全イニング 攻撃・守備 詳細履歴")

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

                    exclude_res = ["スタメン", "守備変更", "交代", "ベンチ", "試合前", "まとめ入力", "", "nan", "残塁"]
                    exclude_pattern = r"進塁|得点|残塁"

                    if not match_bat.empty:
                        res_s = match_bat["結果"].astype(str).str.strip() if "結果" in match_bat.columns else pd.Series("", index=match_bat.index)
                        type_s = match_bat["種別"].astype(str).str.strip() if "種別" in match_bat.columns else pd.Series("", index=match_bat.index)
                        pos_s = match_bat["位置"].astype(str).str.strip() if "位置" in match_bat.columns else pd.Series("", index=match_bat.index)

                        is_bat_excluded = (
                            res_s.isin(exclude_res) | 
                            res_s.str.contains(exclude_pattern, na=False) |
                            type_s.str.contains(exclude_pattern, na=False) |
                            pos_s.str.contains(exclude_pattern, na=False)
                        )
                        valid_batting_df = match_bat[~is_bat_excluded].copy()
                    else:
                        valid_batting_df = pd.DataFrame()

                    # 修正後の該当ブロック例
                    if not match_pit.empty:
                        mask_pit = (
                            ~match_pit["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"]) &
                            match_pit["打順"].notna()
                        )
                        if "結果" in match_pit.columns:
                            mask_pit = mask_pit & ~match_pit["結果"].astype(str).str.contains(r"進塁|得点|残塁", na=False)
                        valid_pitching_df = match_pit[mask_pit].copy()
                    else:
                        valid_pitching_df = pd.DataFrame()

                    raw_bat_inns = (
                        valid_batting_df["イニング"].dropna().astype(str).tolist()
                        if not valid_batting_df.empty and "イニング" in valid_batting_df.columns
                        else []
                    )
                    raw_pit_inns = (
                        valid_pitching_df["イニング"].dropna().astype(str).tolist()
                        if not valid_pitching_df.empty and "イニング" in valid_pitching_df.columns
                        else []
                    )
                    raw_inns = list(set(raw_bat_inns + raw_pit_inns))

                    exclude_inns = ["まとめ入力", "試合前", "ベンチ", "", "nan", "None"]
                    active_innings = [inn for inn in raw_inns if inn not in exclude_inns]

                    def inning_sort_key(inn):
                        inn_str = str(inn)
                        is_ext = 1 if "延長" in inn_str else 0
                        m = re.search(r'(\d+)', inn_str)
                        num = int(m.group(1)) if m else 99
                        if "表" in inn_str:
                            sub = 0
                        elif "裏" in inn_str:
                            sub = 1
                        else:
                            sub = 2
                        return (is_ext, num, sub)

                    active_innings.sort(key=inning_sort_key)

                    if active_innings:
                        for inn in active_innings:
                            inn_id = inn.replace("回", "").replace("表", "").replace("裏", "")
                            st.markdown(f"<div id='inning-{inn_id}' style='scroll-margin-top: 100px;'></div>", unsafe_allow_html=True)

                            inn_bat_df = valid_batting_df[valid_batting_df["イニング"] == inn] if not valid_batting_df.empty and "イニング" in valid_batting_df.columns else pd.DataFrame()
                            if not inn_bat_df.empty:
                                st.markdown("---")
                                st.markdown(f"### 📍 **{inn}（攻撃）**")
                                bat_items = []
                                for _, row in inn_bat_df.iterrows():
                                    b_order = row.get("打順", "")
                                    try:
                                        b_order_str = f"{int(float(b_order))}番" if pd.notna(b_order) and str(b_order).strip() != "" else ""
                                    except (ValueError, TypeError):
                                        b_order_str = f"{b_order}番" if b_order else ""

                                    p_name = row.get("打者名", row.get("選手名", ""))
                                    res = row.get("結果", "")
                                    direction = row.get("打球方向", "")
                                    rbi = pd.to_numeric(row.get("打点", 0), errors='coerce')
                                    run = pd.to_numeric(row.get("得点", 0), errors='coerce')
                                    sb = pd.to_numeric(row.get("盗塁", 0), errors='coerce')

                                    res_str = str(res)
                                    is_hit = res in ["単打", "二塁打", "三塁打", "本塁打", "安打"]
                                    rbi_val = int(rbi) if pd.notna(rbi) else 0
                                    run_val = int(run) if pd.notna(run) else 0
                                    sb_val = int(sb) if pd.notna(sb) else (1 if "盗塁" in res_str and "盗塁死" not in res_str else 0)

                                    core_text = ""
                                    if direction and str(direction) not in ["---", "nan", "None", ""]:
                                        core_text += f"{direction}"
                                    core_text += f"{res_str}"

                                    if is_hit:
                                        if rbi_val > 0:
                                            formatted_res = f"<span style='color: #dc2626; font-weight: bold;'>{core_text}（打点{rbi_val}）</span>"
                                        else:
                                            formatted_res = f"<span style='color: #2563eb; font-weight: bold;'>{core_text}</span>"
                                    else:
                                        formatted_res = core_text
                                        if rbi_val > 0:
                                            formatted_res += f" ・ <span style='color: #dc2626; font-weight: bold;'>打点{rbi_val}</span>"

                                    extras = []
                                    if sb_val > 0:
                                        extras.append(f"<span style='color: #9333ea; font-weight: bold;'>盗{sb_val}</span>")
                                    if run_val > 0:
                                        extras.append(f"<span style='color: #16a34a; font-weight: bold;'>得{run_val}</span>")

                                    if extras:
                                        formatted_res += f" [{', '.join(extras)}]"

                                    bat_items.append({
                                        "打順": b_order_str,
                                        "選手名": p_name,
                                        "結果": formatted_res
                                    })

                                df_bat_disp = pd.DataFrame(bat_items)
                                table_html = (
                                    "<div style='overflow-x: auto;'>"
                                    "<table style='border-collapse: collapse; border: 1px solid #444444; width: 100%; margin-bottom: 10px; font-family: sans-serif; background-color: white; table-layout: fixed;'>"
                                    "<colgroup>"
                                    "<col style='width: 20%;'>"
                                    "<col style='width: 30%;'>"
                                    "<col style='width: 50%;'>"
                                    "</colgroup>"
                                    "<thead><tr style='background-color: #f0f0f0;'>"
                                    "<th style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000; font-weight: bold;'>打順</th>"
                                    "<th style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000; font-weight: bold;'>選手名</th>"
                                    "<th style='border: 1px solid #444444; padding: 8px; text-align: left; color: #000000; font-weight: bold;'>結果</th>"
                                    "</tr></thead><tbody>"
                                )
                                for _, row in df_bat_disp.iterrows():
                                    table_html += (
                                        "<tr>"
                                        f"<td style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000;'>{row['打順']}</td>"
                                        f"<td style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000;'>{row['選手名']}</td>"
                                        f"<td style='border: 1px solid #444444; padding: 8px; text-align: left; color: #000000;'>{row['結果']}</td>"
                                        "</tr>"
                                    )
                                table_html += "</tbody></table></div>"
                                st.markdown(table_html, unsafe_allow_html=True)

                            inn_pit_df = valid_pitching_df[valid_pitching_df["イニング"] == inn] if not valid_pitching_df.empty and "イニング" in valid_pitching_df.columns else pd.DataFrame()
                            if not inn_pit_df.empty:
                                st.markdown("---")
                                st.markdown(f"### 📍 **{inn}（守備）**")
                                pit_items = []
                                for _, row in inn_pit_df.iterrows():
                                    b_ord_val = row.get("打順")
                                    if pd.notna(b_ord_val) and str(b_ord_val).strip() not in ["", "nan", "None"]:
                                        try:
                                            b_idx = f"{int(float(b_ord_val))}番"
                                        except (ValueError, TypeError):
                                            b_idx = f"{b_ord_val}番"
                                    else:
                                        raw_b_idx = str(row.get("種別", "")).split(":")[1].replace("番打者", "") if ":" in str(row.get("種別", "")) else "?"
                                        try:
                                            b_idx = f"{int(float(raw_b_idx))}番"
                                        except (ValueError, TypeError):
                                            b_idx = f"{raw_b_idx}番" if raw_b_idx != "?" else "?"

                                    raw_res = str(row.get('結果', ''))
                                    pos_str = str(row.get('打球方向', '')) or str(row.get('守備位置', ''))

                                    is_hit_pit = raw_res in ["単打", "二塁打", "三塁打", "本塁打", "安打"]
                                    runs = pd.to_numeric(row.get('失点', 0), errors='coerce')
                                    runs_val = int(runs) if pd.notna(runs) else 0

                                    core_pit = ""
                                    if pos_str and pos_str not in ["nan", "None", ""]:
                                        core_pit = f"{pos_str}"
                                    core_pit += f"{raw_res}"

                                    if is_hit_pit:
                                        if runs_val > 0:
                                            formatted_pit = f"<span style='color: #dc2626; font-weight: bold;'>{core_pit} (失点{runs_val})</span>"
                                        else:
                                            formatted_pit = f"<span style='color: #2563eb; font-weight: bold;'>{core_pit}</span>"
                                    else:
                                        formatted_pit = core_pit
                                        if runs_val > 0:
                                            formatted_pit += f" <span style='color: #dc2626; font-weight: bold;'>💥失点{runs_val}</span>"

                                    fielder_str = str(row.get('処理野手', ''))
                                    if fielder_str and fielder_str not in ["nan", "None", ""]:
                                        formatted_pit += f" [{fielder_str}]"

                                    pitcher_disp_name = row.get("投手名", row.get("選手名", ""))

                                    pit_items.append({
                                        "打順": b_idx, 
                                        "投手": pitcher_disp_name, 
                                        "結果": formatted_pit
                                    })

                                df_pit_disp = pd.DataFrame(pit_items)
                                pit_table_html = (
                                    "<div style='overflow-x: auto;'>"
                                    "<table style='border-collapse: collapse; border: 1px solid #444444; width: 100%; margin-bottom: 10px; font-family: sans-serif; background-color: white; table-layout: fixed;'>"
                                    "<colgroup>"
                                    "<col style='width: 20%;'>"
                                    "<col style='width: 30%;'>"
                                    "<col style='width: 50%;'>"
                                    "</colgroup>"
                                    "<thead><tr style='background-color: #f0f0f0;'>"
                                    "<th style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000; font-weight: bold;'>打順</th>"
                                    "<th style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000; font-weight: bold;'>投手</th>"
                                    "<th style='border: 1px solid #444444; padding: 8px; text-align: left; color: #000000; font-weight: bold;'>結果</th>"
                                    "</tr></thead><tbody>"
                                )
                                for _, row in df_pit_disp.iterrows():
                                    pit_table_html += (
                                        "<tr>"
                                        f"<td style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000;'>{row['打順']}</td>"
                                        f"<td style='border: 1px solid #444444; padding: 8px; text-align: center; color: #000000;'>{row['投手']}</td>"
                                        f"<td style='border: 1px solid #444444; padding: 8px; text-align: left; color: #000000;'>{row['結果']}</td>"
                                        "</tr>"
                                    )
                                pit_table_html += "</tbody></table></div>"
                                st.markdown(pit_table_html, unsafe_allow_html=True)
                    else:
                        st.caption("詳細データはまだありません。")
                else:
                    st.caption("※ 個人投手成績なし")