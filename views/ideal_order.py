import datetime
import streamlit as st
import pandas as pd
from config.settings import ALL_PLAYERS

def calculate_saber_metrics(stats):
    """集計された成績データからセイバーメトリクス指標を算出する"""
    stats["PA"] = stats["AB"] + stats["BB"] + stats["SF"]
    stats["AVG"] = stats.apply(lambda x: x["Hit"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
    stats["OBP"] = stats.apply(lambda x: (x["Hit"] + x["BB"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
    stats["SLG"] = stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
    stats["OPS"] = stats["OBP"] + stats["SLG"]
    stats["K_rate"] = stats.apply(lambda x: x["SO"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
    
    # RC (Runs Created) の算出
    stats["RC"] = stats.apply(
        lambda x: ((x["Hit"] + x["BB"]) * x["TB"]) / (x["AB"] + x["BB"]) if (x["AB"] + x["BB"]) > 0 else 0, 
        axis=1
    )

    # 打順選出用の独自スコア
    stats["Score_1"] = stats["OBP"] + (stats["SB"] * 0.02) - (stats["K_rate"] * 0.5)
    stats["Score_3"] = stats["OPS"] - (stats["K_rate"] * 0.5)
    stats["Score_9"] = stats["OBP"] + (stats["SB"] * 0.02)
    
    return stats

def assign_and_display_lineup(stats, pos_df, selected_players, season_pa_dict=None):
    """指標に基づいて打順と守備位置を割り当て、画面に描画する"""
    used_players = []
    lineup = {}

    def assign_player(order, sort_col):
        available = stats[~stats["選手名"].isin(used_players)].sort_values(sort_col, ascending=False)
        if not available.empty:
            p = available.iloc[0]
            used_players.append(p["選手名"])
            lineup[order] = p
        else:
            lineup[order] = None

    # 最も重要な役割から順番に確保（優先順位アルゴリズム）
    assign_player(2, "OPS")      # 2番: OPS1位（チーム最強）
    assign_player(4, "SLG")      # 4番: SLG1位（長打力最優先）
    assign_player(1, "Score_1")  # 1番: OBP + 走塁 - 三振（1位）
    assign_player(5, "SLG")      # 5番: SLG2位
    assign_player(3, "Score_3")  # 3番: OPS2〜4位相当 + 三振少ない
    assign_player(9, "Score_9")  # 9番: OBP + 走塁（8番より先に確保）
    assign_player(6, "OPS")      # 6番: OPS上位残り
    assign_player(7, "OBP")      # 7番: OBPが比較的高い選手
    assign_player(8, "OPS")      # 8番: 残り

    # 10〜15番打者の割り当て (最大15名の打順に対応)
    for i in range(10, 16):
        assign_player(i, "OPS")

    # ==========================================
    # 守備位置の自動推論と割り当て
    # ==========================================
    valid_positions = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
    
    # 対象データから過去に守ったポジションを集計
    p_df = pos_df[pos_df["選手名"].isin(used_players) & pos_df["位置"].isin(valid_positions)]
    pos_counts = p_df.groupby(["選手名", "位置"]).size().reset_index(name="count")
    pos_counts = pos_counts.sort_values("count", ascending=False)
    
    assigned_positions = {}
    available_positions = set(valid_positions)
    
    # 1. 経験のあるポジションを優先的に割り当て
    for _, row in pos_counts.iterrows():
        player = row["選手名"]
        pos = row["位置"]
        if player not in assigned_positions and pos in available_positions:
            assigned_positions[player] = pos
            available_positions.remove(pos)
            
    # 2. 割り当てられなかった選手に対して、空いているポジションを適当に割り当て、9枠埋まったらDH/控とする
    for player in used_players:
        if player not in assigned_positions:
            if available_positions:
                pos = available_positions.pop()
                assigned_positions[player] = pos
            else:
                assigned_positions[player] = "DH/控"

    # ==========================================
    # 画面への描画
    # ==========================================
    roles_info = {
        1: ("最強のチャンスメーカー", "OBP1位 ＋ 走塁上位 ＋ 三振率低", "Score_1"),
        2: ("チーム最強打者", "OPS1位（または総合1位）", "OPS"),
        3: ("確実性の高いポイントゲッター", "OPS上位 ＋ 三振率低", "Score_3"),
        4: ("最大のダメージソース", "SLG1位（長打力最優先）", "SLG"),
        5: ("4番のプロテクター", "SLG2位", "SLG"),
        6: ("第2のクリーンナップ", "OPS上位の残り", "OPS"),
        7: ("下位打線の起点", "OBPが比較的高い選手", "OBP"),
        8: ("繋ぎ役", "残り選手", "OPS"),
        9: ("第2の1番打者", "OBP上位 ＋ 走塁上位", "Score_9")
    }

    for i in range(10, 16):
        roles_info[i] = ("優秀なリザーブ/追加打者", "OPS上位（残り選手）", "OPS")

    st.markdown("#### 🎯 最適化されたスタメンオーダー")
    
    for i in range(1, 16):
        if i not in lineup or lineup[i] is None:
            continue

        role_name, desc, sort_col = roles_info[i]
        p = lineup[i]
        player_name = p['選手名']
        assigned_pos = assigned_positions.get(player_name, "不明")

        st.markdown(f"##### {i}番 ({assigned_pos}): {role_name}")
        st.caption(f"選出基準: {desc}")
        
        # シーズン打席数の追加表示判定
        season_pa_text = ""
        if season_pa_dict is not None:
            s_pa = season_pa_dict.get(player_name, 0)
            season_pa_text = f" | 今季打席数: **{s_pa}**"

        st.success(
            f"**{player_name}**\n\n"
            f"評価値({sort_col}): **{p[sort_col]:.3f}** | "
            f"打率: {p['AVG']:.3f} | 出塁率: {p['OBP']:.3f} | 長打率: {p['SLG']:.3f} | OPS: {p['OPS']:.3f} | RC: **{p['RC']:.2f}**\n\n"
            f"本塁打: {int(p['HR'])} | 打点: {int(p['RBI'])} | 盗塁: {int(p['SB'])} | 三振率: {p['K_rate']:.3f}{season_pa_text}"
        )
    
    st.divider()

    # 配置外（規定打席未到達など）のプレイヤーを表示
    unassigned = [p for p in selected_players if p not in used_players]
    if unassigned:
        st.info(f"📌 **条件未到達等のため配置外の選手**: {', '.join(unassigned)}")


def show_ideal_order_tab(df_batting):
    st.markdown("### 🧠 選択選手から理想オーダー作成")
    st.write("本日参加するメンバーを選択すると、成績のセイバーメトリクス指標と過去の守備機会から、最適なスタメンと守備位置を自動生成します。")

    # 打撃入力ページで選択された「ベンチメンバー」をデフォルト値として取得
    default_players = st.session_state.get("persistent_bench", [])
    
    # 最大15名まで対応可能なマルチセレクト
    selected_players = st.multiselect("本日参加するメンバーを選択", ALL_PLAYERS, default=default_players, key="ideal_order_players_widget")

    if not selected_players:
        st.info("選手を選択してください。")
        return

    if df_batting.empty:
        st.warning("分析する打撃データがありません。")
        return

    # ==========================================
    # データの前処理
    # ==========================================
    df_calc = df_batting[df_batting["選手名"] != "チーム記録"].copy()
    df_calc["結果"] = df_calc["結果"].astype(str).str.replace(r"\s+", "", regex=True)

    # 各種フラグ・数値化
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
    
    # 打席(PA)フラグを作成
    df_calc["is_pa"] = ((df_calc["is_ab"] == 1) | (df_calc["is_bb"] == 1) | (df_calc["is_sf"] == 1)).astype(int)

    for c in ["打点", "盗塁"]:
        df_calc[c] = pd.to_numeric(df_calc[c], errors='coerce').fillna(0)

    # 選択された選手のみに絞り込み
    df_selected = df_calc[df_calc["選手名"].isin(selected_players)].copy()

    if df_selected.empty:
        st.warning("選択された選手の打席データがありません。")
        return

    # 今シーズンの打席数を算出（辞書形式で保持）
    df_selected["日付_dt"] = pd.to_datetime(df_selected["日付"], errors="coerce")
    current_year = datetime.datetime.now().year
    df_this_season = df_selected[df_selected["日付_dt"].dt.year == current_year]
    
    season_pa_series = df_this_season.groupby("選手名")["is_pa"].sum()
    season_pa_dict = season_pa_series.to_dict()

    # タブで「通算成績」と「直近10打席」を分ける
    tab_all, tab_recent = st.tabs(["📊 通算成績オーダー", "🔥 直近10打席オーダー"])

    # ---------------------------------------------------------
    # 1. 通算成績オーダー
    # ---------------------------------------------------------
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

        # 通算オーダーは最低10打数の適用
        stats_all = stats_all[stats_all["AB"] >= 10]

        if not stats_all.empty:
            stats_all = calculate_saber_metrics(stats_all)
            assign_and_display_lineup(stats_all, df_selected, selected_players, season_pa_dict=season_pa_dict)
        else:
            st.warning("規定打数（10打数）に到達している選択選手がいません。")

    # ---------------------------------------------------------
    # 2. 直近10打席オーダー
    # ---------------------------------------------------------
    with tab_recent:
        st.write("各選手の直近10打席（四死球・犠飛含む）の成績をベースにした、現在の調子重視のオーダーです。")
        
        # 日付と打順でソートし、時系列順にする
        df_selected["打順_num"] = pd.to_numeric(df_selected["打順"], errors="coerce")
        df_sorted = df_selected.sort_values(by=["日付_dt", "打順_num"], ascending=[True, True])
        
        # 打席(PA)データのみを抽出
        df_pa = df_sorted[df_sorted["is_pa"] == 1]
        
        # 各選手の直近10打席を取得
        df_recent10 = df_pa.groupby("選手名").tail(10)
        
        stats_recent = df_recent10.groupby("選手名").agg({
            "is_ab": "sum", "is_hit": "sum", "is_bb": "sum", "is_sf": "sum",
            "bases": "sum", "盗塁": "sum", "打点": "sum", "is_hr": "sum", "is_so": "sum"
        }).reset_index()

        stats_recent = stats_recent.rename(columns={
            "is_ab": "AB", "is_hit": "Hit", "is_bb": "BB", "is_sf": "SF",
            "bases": "TB", "盗塁": "SB", "打点": "RBI", "is_hr": "HR", "is_so": "SO"
        })

        # 直近オーダーは打席が0の選手のみ除外（10打席未満でも算出する）
        stats_recent = stats_recent[(stats_recent["AB"] + stats_recent["BB"] + stats_recent["SF"]) > 0]

        if not stats_recent.empty:
            stats_recent = calculate_saber_metrics(stats_recent)
            assign_and_display_lineup(stats_recent, df_recent10, selected_players, season_pa_dict=season_pa_dict)
        else:
            st.warning("直近の打席データを持つ選択選手がいません。")