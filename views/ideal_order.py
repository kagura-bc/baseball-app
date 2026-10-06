import datetime
import re
import pandas as pd
import streamlit as st
from utils.players import get_active_players
from utils.ui import fmt_player_name


def local_fmt(name):
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))


def clean_name(n):
    """名前から背番号表記 (2) や余分な空白を取り除いて正規化する"""
    return re.sub(r'[\s ]+', '', str(n)).split("(")[0].strip()


def calculate_saber_metrics(stats):
    """集計された成績データからセイバーメトリクス指標とRC、各専用スコアを算出する"""
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

    stats["Score_1"] = (
        stats["OBP"] * 2.0
        + stats["RC_per_PA"] * 0.5
        + stats["SB"] * 0.02
        - stats["K_rate"] * 0.8
    )
    stats["Score_2"] = (
        stats["OPS"] * 2.5
        + stats["OBP"] * 1.0
        + stats["RC_per_PA"] * 0.5
    )
    stats["Score_3"] = (
        stats["OPS"] * 3.0
        + stats["RC_per_PA"] * 0.6
    )
    stats["Score_4"] = (
        stats["OPS"] * 2.2
        + stats["SLG"] * 0.8
    )
    stats["Score_5"] = (
        stats["OPS"] * 2.0
        + stats["SLG"] * 0.4
    )
    stats["Score_6"] = (
        stats["OPS"] * 1.8
        + stats["RC_per_PA"] * 0.4
    )
    stats["Score_7"] = (
        stats["OBP"] * 1.5
        + stats["OPS"] * 0.7
    )
    stats["Score_8"] = (
        stats["OPS"] * 1.3
        + stats["OBP"] * 0.3
    )
    stats["Score_9"] = (
        stats["OBP"] * 2.0
        + stats["SB"] * 0.02
        - stats["K_rate"] * 0.6
    )
    
    for i in range(10, 16):
        stats[f"Score_{i}"] = stats["OPS"]
        
    return stats


def calc_consecutive_hitless(df_calc):
    """全打撃ログを時系列ソートし、最新打席から遡って現在の連続無安打数（打席/打数）を算出する"""
    if df_calc.empty:
        return {}
        
    df_sorted = df_calc.sort_values(by=["日付_dt", "打順_num"], ascending=[True, True])
    
    hitless_dict = {}
    for player, group in df_sorted.groupby("選手名"):
        pa_df = group[group["is_pa"] == 1]
        c_pa = 0
        if not pa_df.empty:
            for _, row in pa_df.iloc[::-1].iterrows():
                if row["is_hit"] == 1:
                    break
                c_pa += 1
                
        ab_df = group[group["is_ab"] == 1]
        c_ab = 0
        if not ab_df.empty:
            for _, row in ab_df.iloc[::-1].iterrows():
                if row["is_hit"] == 1:
                    break
                c_ab += 1
                
        hitless_dict[player] = {"ab": c_ab, "pa": c_pa}
        
    return hitless_dict


def assign_and_display_lineup(stats, pos_df, selected_players, season_pa_dict=None, df_pitching=None, hitless_dict=None):
    """投手成績データの投手名から厳格に投手を選出し、スタメンオーダーと守備位置を自動決定する"""
    used_players = []
    lineup = {}
    assigned_positions = {}

    cleaned_selected = [clean_name(p) for p in selected_players]
    raw_name_map = {clean_name(p): p for p in selected_players}

    # 1. 投手成績（df_pitching）の解析と投手経験者の抽出
    pitcher_experienced_set = set()
    ace_player_clean = None

    if df_pitching is not None and not df_pitching.empty:
        df_p = df_pitching.copy()
        p_col = "投手名" if "投手名" in df_p.columns else ("選手名" if "選手名" in df_p.columns else None)
        
        if p_col:
            df_p["選手名_clean"] = df_p[p_col].apply(clean_name)
            df_p_calc = df_p[df_p["選手名_clean"] != "チーム記録"].copy()
            pitcher_experienced_set = set(df_p_calc["選手名_clean"].dropna().unique())

            # 個人成績と同等の「アウト数」「奪三振」導出ロジック
            res_str = df_p_calc["結果"].astype(str) if "結果" in df_p_calc.columns else pd.Series([""] * len(df_p_calc))
            outs = pd.Series(0, index=df_p_calc.index)
            dp_mask = res_str.str.contains("併殺", na=False)
            outs[dp_mask] = 2

            normal_out_mask = (
                res_str.str.contains("凡退|三振|犠打|犠飛|走塁死|盗塁死", na=False) &
                ~res_str.str.contains("失策|得点|進塁|盗塁|安打|単打|二塁打|三塁打|本塁打|四球|死球|暴投|捕逸|ボーク", na=False)
            )
            outs[normal_out_mask] = 1

            if "アウト数" in df_p_calc.columns and df_p_calc["アウト数"].sum() > 0:
                df_p_calc["outs_calc"] = pd.to_numeric(df_p_calc["アウト数"], errors='coerce').fillna(outs)
            else:
                df_p_calc["outs_calc"] = outs

            df_p_calc["so_calc"] = res_str.isin(["三振", "振り逃げ三振"]).astype(int)
            if "自責点" in df_p_calc.columns:
                df_p_calc["er_calc"] = pd.to_numeric(df_p_calc["自責点"], errors='coerce').fillna(0)
            else:
                df_p_calc["er_calc"] = 0

            # 選択メンバー内の投手データ集計
            df_p_sel = df_p_calc[df_p_calc["選手名_clean"].isin(cleaned_selected)]

            if not df_p_sel.empty:
                p_agg = df_p_sel.groupby("選手名_clean").agg(
                    outs=("outs_calc", "sum"),
                    er=("er_calc", "sum"),
                    so=("so_calc", "sum")
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
                # 投手スコア順、同点の場合は投球イニング（outs）順でソート
                p_sorted = p_agg.sort_values(by=["Pitching_Score", "outs"], ascending=[False, False])
                if not p_sorted.empty:
                    ace_player_clean = p_sorted.iloc[0]["選手名_clean"]

    # 2. バックアップ選出（スコアが未計算の場合でも投手経験者から選出）
    if not ace_player_clean:
        exp_selected = [p for p in cleaned_selected if p in pitcher_experienced_set]
        if exp_selected:
            ace_player_clean = exp_selected[0]

    # stats 側の選手名表現（`stats['選手名']`）とマッチング
    stats["選手名_clean"] = stats["選手名"].apply(clean_name)
    ace_player_in_stats = None
    if ace_player_clean:
        match_stats = stats[stats["選手名_clean"] == ace_player_clean]
        if not match_stats.empty:
            ace_player_in_stats = match_stats.iloc[0]["選手名"]

    def assign_player(order, sort_col, force_ace=False):
        if force_ace and ace_player_in_stats and ace_player_in_stats not in used_players:
            ace_row = stats[stats["選手名"] == ace_player_in_stats]
            if not ace_row.empty:
                used_players.append(ace_player_in_stats)
                lineup[order] = ace_row.iloc[0]
                return

        available = stats[~stats["選手名"].isin(used_players)].sort_values(sort_col, ascending=False)
        if not available.empty:
            p = available.iloc[0]
            used_players.append(p["選手名"])
            lineup[order] = p
        else:
            lineup[order] = None

    # 打順（1〜9番スタメン＋10〜15番控え）決定
    assign_player(3, "Score_3")
    assign_player(1, "Score_1")
    assign_player(2, "Score_2")
    assign_player(4, "Score_4")
    assign_player(5, "Score_5")
    assign_player(6, "Score_6")
    assign_player(7, "Score_7")
    assign_player(8, "Score_8")
    assign_player(9, "Score_9", force_ace=True)

    for i in range(10, 16):
        assign_player(i, "OPS")

    # 3. 守備位置の割り当て
    starters_9 = [lineup[i]["選手名"] for i in range(1, 10) if i in lineup and lineup[i] is not None]
    
    if ace_player_in_stats and ace_player_in_stats in starters_9:
        assigned_positions[ace_player_in_stats] = "投"
    elif ace_player_in_stats:
        assigned_positions[ace_player_in_stats] = "投"

    if "投" in assigned_positions.values():
        remaining_positions = ["捕", "一", "二", "三", "遊", "左", "中", "右"]
    else:
        remaining_positions = ["捕", "一", "二", "三", "遊", "左", "中", "右", "DH/控"]

    unassigned_starters = [p for p in starters_9 if p not in assigned_positions]
    available_pos = set(remaining_positions)

    # 野手守備データ（pos_df）からの優先マッチング
    pos_col = "位置" if pos_df is not None and "位置" in pos_df.columns else ("守備位置" if pos_df is not None and "守備位置" in pos_df.columns else None)
    if pos_df is not None and not pos_df.empty and pos_col:
        pos_df["選手名_clean"] = pos_df["選手名"].apply(clean_name) if "選手名" in pos_df.columns else pos_df.iloc[:, 0].apply(clean_name)
        p_df = pos_df[pos_df["選手名_clean"].isin([clean_name(p) for p in unassigned_starters]) & pos_df[pos_col].isin(remaining_positions)]
        if not p_df.empty:
            pos_counts = p_df.groupby(["選手名_clean", pos_col]).size().reset_index(name="count")
            pos_counts = pos_counts.sort_values("count", ascending=False)
            
            for _, row in pos_counts.iterrows():
                p_clean = row["選手名_clean"]
                pos = row[pos_col]
                # unassigned_starters から対応する元の名前を取得
                orig_player = next((p for p in unassigned_starters if clean_name(p) == p_clean), None)
                if orig_player and orig_player in unassigned_starters and pos in available_pos:
                    assigned_positions[orig_player] = pos
                    available_pos.remove(pos)
                    unassigned_starters.remove(orig_player)

    # 残りのスタメン選手に空いている野手ポジションを割り当て
    for player in list(unassigned_starters):
        if available_pos:
            assigned_positions[player] = available_pos.pop()

    # 控え選手（10〜15番）は「DH/控」に割り当て
    for i in range(10, 16):
        if i in lineup and lineup[i] is not None:
            p_name = lineup[i]["選手名"]
            if p_name not in assigned_positions:
                assigned_positions[p_name] = "DH/控"

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

    for i in range(10, 16):
        roles_info[i] = ("優秀なリザーブ/追加打者", "OPS上位（残り選手）", "OPS")

    st.markdown("#### 🎯 スタメンオーダー ＆ 守備位置")
    
    if not ace_player_clean:
        st.warning("⚠️ 選択されたメンバーの中に投手成績データが記録されている選手が含まれていません。投手ポジションは未割り当てです。")

    for i in range(1, 16):
        if i not in lineup or lineup[i] is None:
            continue

        role_name, desc, sort_col = roles_info[i]
        p = lineup[i]
        player_name = p['選手名']
        c_player_name = clean_name(player_name)
        assigned_pos = assigned_positions.get(player_name, "不明")

        st.markdown(f"##### {i}番 ({assigned_pos}): {role_name}")
        st.caption(f"選出基準: {desc}")
        
        season_pa_text = ""
        if season_pa_dict is not None:
            s_pa = season_pa_dict.get(player_name, season_pa_dict.get(c_player_name, 0))
            season_pa_text = f" | 今季打席数: **{s_pa}**"

        hitless_text = ""
        if hitless_dict:
            h_info = hitless_dict.get(player_name) or hitless_dict.get(c_player_name)
            if h_info:
                c_pa = h_info["pa"]
                c_ab = h_info["ab"]
                if c_pa == 0:
                    hitless_text = " | 状態: **✨ 直近打席で安打あり**"
                elif c_pa >= 10:
                    hitless_text = f" | 状態: **⚠️ {c_pa}打席（{c_ab}打数）連続無安打**"
                else:
                    hitless_text = f" | 状態: **📉 {c_pa}打席（{c_ab}打数）連続無安打**"

        pitcher_text = ""
        if assigned_pos == "投" and df_pitching is not None and not df_pitching.empty:
            p_col_show = "投手名" if "投手名" in df_pitching.columns else "選手名"
            p_rows = df_pitching[(df_pitching[p_col_show].apply(clean_name) == c_player_name) & (df_pitching[p_col_show] != "チーム記録")]
            if not p_rows.empty:
                res_s = p_rows["結果"].astype(str) if "結果" in p_rows.columns else pd.Series([""] * len(p_rows))
                p_outs = pd.Series(0, index=p_rows.index)
                p_outs[res_s.str.contains("併殺", na=False)] = 2
                p_outs[res_s.str.contains("凡退|三振|犠打|犠飛|走塁死|盗塁死", na=False) & ~res_s.str.contains("失策|得点|進塁|盗塁|安打|単打|二塁打|三塁打|本塁打|四球|死球|暴投|捕逸|ボーク", na=False)] = 1
                
                outs_sum = pd.to_numeric(p_rows["アウト数"], errors='coerce').fillna(p_outs).sum() if "アウト数" in p_rows.columns else p_outs.sum()
                ip_val = outs_sum / 3.0
                
                run_col = "自責点" if "自責点" in p_rows.columns else ("失点" if "失点" in p_rows.columns else None)
                er_sum = pd.to_numeric(p_rows[run_col], errors='coerce').fillna(0).sum() if run_col and run_col in p_rows.columns else 0
                era = (er_sum * 7) / ip_val if ip_val > 0 else 0.0
                
                so_val = res_s.isin(["三振", "振り逃げ三振"]).sum()
                if "奪三振" in p_rows.columns:
                    so_val = max(so_val, pd.to_numeric(p_rows["奪三振"], errors='coerce').fillna(0).sum())
                
                ip_str = f"{int(ip_val//1)}.{int(round((ip_val%1)*3))}"
                pitcher_text = f"\n\n⚾ **【通算投手成績】** 投球回(IP): {ip_str} | 防御率(ERA): {era:.2f} | 奪三振: {int(so_val)}"

        score_val = p.get(sort_col, 0)
        st.success(
            f"**{player_name}**\n\n"
            f"評価値({sort_col}): **{score_val:.3f}** | "
            f"打率: {p['AVG']:.3f} | 出塁率: {p['OBP']:.3f} | 長打率: {p['SLG']:.3f} | OPS: {p['OPS']:.3f} | RC/PA: {p['RC_per_PA']:.3f}\n\n"
            f"本塁打: {int(p['HR'])} | 打点: {int(p['RBI'])} | 盗塁: {int(p['SB'])} | 三振率: {p['K_rate']:.3f}{season_pa_text}{hitless_text}{pitcher_text}"
        )
    
    st.divider()

    used_players_clean = [clean_name(u) for u in used_players]
    unassigned = [p for p in selected_players if clean_name(p) not in used_players_clean]
    
    if unassigned:
        st.info(f"📌 **条件未到達等のため配置外の選手**: {', '.join(unassigned)}")


def show_ideal_order_tab(df_batting, df_pitching=None):
    ALL_PLAYERS, PLAYER_NUMBERS = get_active_players()
    st.session_state["shared_player_numbers"] = PLAYER_NUMBERS

    st.markdown("### 🧠 選択選手から理想オーダー作成")
    st.write("本日参加するメンバーを選択すると、成績のセイバーメトリクス指標と過去の守備機会から、最適なスタメンと守備位置を自動生成します。")

    if "ideal_order_selected_players" not in st.session_state:
        st.session_state["ideal_order_selected_players"] = []

    sel_count = len(st.session_state.get("ideal_order_selected_players", []))
    popover_label = f"👥 本日参加するメンバーを選択 (選択中: {sel_count}人) 🔽"

    with st.popover(popover_label, use_container_width=True):
        st.markdown("##### 👥 参加メンバーをタップして選択（複数選択可）")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("全選択", use_container_width=True, key="select_all_ideal"):
                st.session_state["ideal_order_selected_players"] = list(ALL_PLAYERS)
                st.rerun()
        with col_c2:
            if st.button("クリア", use_container_width=True, key="clear_ideal"):
                st.session_state["ideal_order_selected_players"] = []
                st.rerun()

        st.markdown("---")
        
        st.pills(
            "本日参加するメンバーを選択",
            ALL_PLAYERS,
            format_func=local_fmt,
            selection_mode="multi",
            key="ideal_order_selected_players",
            label_visibility="collapsed"
        )

    selected_players = st.session_state.get("ideal_order_selected_players", [])

    if not selected_players:
        st.info("選手を選択してください。")
        return

    if df_batting.empty:
        st.warning("分析する打撃データがありません。")
        return

    # 打撃データ・投手データの両方で「選手名」列を補正・統一
    b_p_col = "打者名" if "打者名" in df_batting.columns else "選手名"
    df_batting["選手名"] = df_batting[b_p_col]

    if df_pitching is not None and not df_pitching.empty:
        p_p_col = "投手名" if "投手名" in df_pitching.columns else "選手名"
        df_pitching["選手名"] = df_pitching[p_p_col]

    df_calc = df_batting[df_batting["選手名"] != "チーム記録"].copy()
    df_calc["結果"] = df_calc["結果"].astype(str).str.replace(r"\s+", "", regex=True)

    hit_pattern = "単打|二塁打|三塁打|本塁打"
    df_calc["is_hit"] = df_calc["結果"].str.contains(hit_pattern, na=False).astype(int)
    non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
    df_calc["is_ab"] = (~df_calc["結果"].isin(["", "nan", "None", "-"]) & ~df_calc["結果"].str.contains(non_ab_pattern, na=False)).astype(int)
    
    df_calc["is_bb"] = df_calc["結果"].str.contains("四球|死球|四死球", na=False).astype(int)
    df_calc["is_sf"] = df_calc["結果"].str.contains("犠飛", na=False).astype(int)
    df_calc["is_so"] = df_calc["結果"].str.contains("三振", na=False).astype(int)
    df_calc["is_hr"] = df_calc["結果"].str.contains("本塁打", na=False).astype(int)
    df_calc["is_1b"] = df_calc["結果"].str.contains("単打", na=False).astype(int)
    df_calc["is_2b"] = df_calc["結果"].str.contains("二塁打", na=False).astype(int)
    df_calc["is_3b"] = df_calc["結果"].str.contains("三塁打", na=False).astype(int)
    df_calc["bases"] = df_calc["is_1b"] + (df_calc["is_2b"] * 2) + (df_calc["is_3b"] * 3) + (df_calc["is_hr"] * 4)
    df_calc["is_pa"] = ((df_calc["is_ab"] == 1) | (df_calc["is_bb"] == 1) | (df_calc["is_sf"] == 1)).astype(int)

    # 打点
    if "打点" in df_calc.columns:
        df_calc["打点"] = pd.to_numeric(df_calc["打点"], errors='coerce').fillna(0)
    else:
        df_calc["打点"] = 0

    # 盗塁
    res_str = df_calc["結果"].astype(str)
    steal_mask = (res_str == "盗塁") | (res_str.str.contains("盗塁") & ~res_str.str.contains("盗塁死"))
    if "盗塁" in df_batting.columns:
        df_calc["盗塁"] = pd.to_numeric(df_batting["盗塁"], errors='coerce').fillna(0) + steal_mask.astype(int)
    else:
        df_calc["盗塁"] = steal_mask.astype(int)

    df_calc["日付_dt"] = pd.to_datetime(df_calc.get("日付", ""), errors="coerce")
    df_calc["打順_num"] = pd.to_numeric(df_calc.get("打順", 0), errors="coerce")

    # 各選手の連続無安打数を算出
    hitless_dict = calc_consecutive_hitless(df_calc)

    cleaned_selected_players = [clean_name(p) for p in selected_players]
    df_calc["選手名_clean"] = df_calc["選手名"].astype(str).apply(clean_name)
    
    df_selected = df_calc[df_calc["選手名_clean"].isin(cleaned_selected_players)].copy()

    if df_selected.empty:
        st.warning("選択された選手の打席データがありません。")
        return

    current_year = datetime.datetime.now().year
    df_this_season = df_selected[df_selected["日付_dt"].dt.year == current_year]
    
    season_pa_series = df_this_season.groupby("選手名")["is_pa"].sum()
    season_pa_dict = season_pa_series.to_dict()

    tab_all, tab_recent = st.tabs(["📊 通算成績オーダー", "🔥 直近10打席オーダー"])

    with tab_all:
        st.write("全期間の通算成績をベースにした理想オーダーです。（※規定打数10打数以上の選手が対象）")
        
        stats_all = df_selected.groupby("選手名").agg({
            "is_ab": "sum", "is_hit": "sum", "is_bb": "sum", "is_sf": "sum",
            "bases": "sum", "盗塁": "sum", "打点": "sum", "is_hr": "sum", "is_so": "sum"
        }).reset_index()

        stats_all = stats_all.rename(columns={
            "is_ab": "AB", "is_hit": "Hit", "is_bb": "BB", "is_sf": "SF",
            "bases": "TB", "盗塁": "SB", "打点": "RBI", "is_hr": "HR", "is_so": "SO"
        })

        stats_all = stats_all[stats_all["AB"] >= 10]

        if not stats_all.empty:
            stats_all = calculate_saber_metrics(stats_all)
            assign_and_display_lineup(stats_all, df_selected, selected_players, season_pa_dict=season_pa_dict, df_pitching=df_pitching, hitless_dict=hitless_dict)
        else:
            st.warning("規定打数（10打数）に到達している選択選手がいません。")

    with tab_recent:
        st.write("各選手の直近10打席（四死球・犠飛含む）の成績をベースにした、現在の調子重視のオーダーです。")
        
        df_sorted = df_selected.sort_values(by=["日付_dt", "打順_num"], ascending=[True, True])
        df_pa = df_sorted[df_sorted["is_pa"] == 1]
        df_recent10 = df_pa.groupby("選手名").tail(10)
        
        stats_recent = df_recent10.groupby("選手名").agg({
            "is_ab": "sum", "is_hit": "sum", "is_bb": "sum", "is_sf": "sum",
            "bases": "sum", "盗塁": "sum", "打点": "sum", "is_hr": "sum", "is_so": "sum"
        }).reset_index()

        stats_recent = stats_recent.rename(columns={
            "is_ab": "AB", "is_hit": "Hit", "is_bb": "BB", "is_sf": "SF",
            "bases": "TB", "盗塁": "SB", "打点": "RBI", "is_hr": "HR", "is_so": "SO"
        })

        stats_recent = stats_recent[(stats_recent["AB"] + stats_recent["BB"] + stats_recent["SF"]) > 0]

        if not stats_recent.empty:
            stats_recent = calculate_saber_metrics(stats_recent)
            assign_and_display_lineup(stats_recent, df_recent10, selected_players, season_pa_dict=season_pa_dict, df_pitching=df_pitching, hitless_dict=hitless_dict)
        else:
            st.warning("直近の打席データを持つ選択選手がいません。")