import datetime
import streamlit as st
import pandas as pd
from config.settings import ALL_PLAYERS


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


def assign_and_display_lineup(stats, pos_df, selected_players, season_pa_dict=None, df_pitching=None):
    """投手部門・貢献度ランキング(通算/総合貢献度タブの投手評価)のトップをエースとして特定し、打順を配置する"""
    used_players = []
    lineup = {}
    assigned_positions = {}

    # 🌟 1. 「投手部門・貢献度ランキング」の評価ロジックに基づいてエースを自動選出
    ace_player = None
    if df_pitching is not None and not df_pitching.empty:
        df_p_calc = df_pitching[df_pitching["選手名"] != "チーム記録"].copy()
        df_p_sel = df_p_calc[df_p_calc["選手名"].isin(selected_players)] if selected_players else df_p_calc
        if not df_p_sel.empty:
            for c in ["自責点", "失点", "アウト数", "is_so", "奪三振"]:
                if c not in df_p_sel.columns:
                    df_p_sel[c] = 0
                df_p_sel[c] = pd.to_numeric(df_p_sel[c], errors='coerce').fillna(0)
            
            temp_so = df_p_sel["結果"].isin(["三振", "振り逃げ三振"]).astype(int) if "結果" in df_p_sel.columns else 0
            df_p_sel["total_so"] = df_p_sel[["奪三振", "is_so"]].max(axis=1) if "奪三振" in df_p_sel.columns else temp_so

            p_agg = df_p_sel.groupby("選手名").agg(
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
            p_sorted = p_agg.sort_values(by="Pitching_Score", ascending=False)
            if not p_sorted.empty and p_sorted.iloc[0]["Pitching_Score"] > 0:
                ace_player = p_sorted.iloc[0]["選手名"]

    if not ace_player and pos_df is not None and not pos_df.empty:
        p_pitchers = pos_df[(pos_df["選手名"].isin(selected_players)) & (pos_df["位置"] == "投")]
        if not p_pitchers.empty:
            ace_counts = p_pitchers.groupby("選手名").size().reset_index(name="count")
            ace_player = ace_counts.sort_values("count", ascending=False).iloc[0]["選手名"]

    if not ace_player and selected_players:
        ace_player = selected_players[0]

    if ace_player:
        assigned_positions[ace_player] = "投"

    def assign_player(order, sort_col, force_ace=False):
        if force_ace and ace_player and ace_player not in used_players:
            ace_row = stats[stats["選手名"] == ace_player]
            if not ace_row.empty:
                used_players.append(ace_player)
                lineup[order] = ace_row.iloc[0]
                return

        available = stats[~stats["選手名"].isin(used_players)].sort_values(sort_col, ascending=False)
        if not available.empty:
            p = available.iloc[0]
            used_players.append(p["選手名"])
            lineup[order] = p
        else:
            lineup[order] = None

    # 🌟 打順は打撃成績に応じて決定（上位から順に評価し、投手が未選出の場合は最後に9番に配置）
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

    valid_positions = ["捕", "一", "二", "三", "遊", "左", "中", "右"]
    other_used = [p for p in used_players if p != ace_player]
    p_df = pos_df[pos_df["選手名"].isin(other_used) & pos_df["位置"].isin(valid_positions)] if pos_df is not None and not pos_df.empty else pd.DataFrame()
    
    if not p_df.empty:
        pos_counts = p_df.groupby(["選手名", "位置"]).size().reset_index(name="count")
        pos_counts = pos_counts.sort_values("count", ascending=False)
    else:
        pos_counts = pd.DataFrame(columns=["選手名", "位置", "count"])
    
    available_positions = set(valid_positions)
    
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

    for i in range(10, 16):
        roles_info[i] = ("優秀なリザーブ/追加打者", "OPS上位（残り選手）", "OPS")

    st.markdown("#### 🎯 投手最優先選出 ＆ スタメンオーダー")
    
    for i in range(1, 16):
        if i not in lineup or lineup[i] is None:
            continue

        role_name, desc, sort_col = roles_info[i]
        p = lineup[i]
        player_name = p['選手名']
        assigned_pos = assigned_positions.get(player_name, "不明")

        st.markdown(f"##### {i}番 ({assigned_pos}): {role_name}")
        st.caption(f"選出基準: {desc}")
        
        season_pa_text = ""
        if season_pa_dict is not None:
            s_pa = season_pa_dict.get(player_name, 0)
            season_pa_text = f" | 今季打席数: **{s_pa}**"

        # 🌟 投手成績を確実に「通算成績（アウト数・自責点ベース）」で計算・表記
        pitcher_text = ""
        if assigned_pos == "投" and df_pitching is not None and not df_pitching.empty:
            p_rows = df_pitching[(df_pitching["選手名"] == player_name) & (df_pitching["選手名"] != "チーム記録")]
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
            f"本塁打: {int(p['HR'])} | 打点: {int(p['RBI'])} | 盗塁: {int(p['SB'])} | 三振率: {p['K_rate']:.3f}{season_pa_text}{pitcher_text}"
        )
    
    st.divider()

    unassigned = [p for p in selected_players if p not in used_players]
    if unassigned:
        st.info(f"📌 **条件未到達等のため配置外の選手**: {', '.join(unassigned)}")

def show_ideal_order_tab(df_batting, df_pitching=None):
    st.markdown("### 🧠 選択選手から理想オーダー作成")
    st.write("本日参加するメンバーを選択すると、成績のセイバーメトリクス指標と過去の守備機会から、最適なスタメンと守備位置を自動生成します。")

    default_players = st.session_state.get("persistent_bench", [])
    selected_players = st.multiselect("本日参加するメンバーを選択", ALL_PLAYERS, default=default_players, key="ideal_order_players_widget")

    if not selected_players:
        st.info("選手を選択してください。")
        return

    if df_batting.empty:
        st.warning("分析する打撃データがありません。")
        return

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

    for c in ["打点", "盗塁"]:
        df_calc[c] = pd.to_numeric(df_calc[c], errors='coerce').fillna(0)

    df_selected = df_calc[df_calc["選手名"].isin(selected_players)].copy()

    if df_selected.empty:
        st.warning("選択された選手の打席データがありません。")
        return

    df_selected["日付_dt"] = pd.to_datetime(df_selected["日付"], errors="coerce")
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
            assign_and_display_lineup(stats_all, df_selected, selected_players, season_pa_dict=season_pa_dict, df_pitching=df_pitching)
        else:
            st.warning("規定打数（10打数）に到達している選択選手がいません。")

    with tab_recent:
        st.write("各選手の直近10打席（四死球・犠飛含む）の成績をベースにした、現在の調子重視のオーダーです。")
        
        df_selected["打順_num"] = pd.to_numeric(df_selected["打順"], errors="coerce")
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
            assign_and_display_lineup(stats_recent, df_recent10, selected_players, season_pa_dict=season_pa_dict, df_pitching=df_pitching)
        else:
            st.warning("直近の打席データを持つ選択選手がいません。")