import streamlit as st
import pandas as pd
from config.settings import ALL_PLAYERS

def show_ideal_order_tab(df_batting):
    st.markdown("### 🧠 選択選手から理想オーダー作成")
    st.write("本日参加するメンバーを選択すると、通算成績のセイバーメトリクス指標と過去の守備機会から、最適なスタメンと守備位置を自動生成します。")

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
    # データの前処理と指標の計算
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

    for c in ["打点", "盗塁"]:
        df_calc[c] = pd.to_numeric(df_calc[c], errors='coerce').fillna(0)

    # 選択された選手のみに絞り込み
    df_selected = df_calc[df_calc["選手名"].isin(selected_players)]

    if df_selected.empty:
        st.warning("選択された選手の打席データがありません。")
        return

    # 成績の集計
    stats = df_selected.groupby("選手名").agg({
        "is_ab": "sum", "is_hit": "sum", "is_bb": "sum", "is_sf": "sum",
        "bases": "sum", "盗塁": "sum", "打点": "sum", "is_hr": "sum", "is_so": "sum"
    }).reset_index()

    stats = stats.rename(columns={
        "is_ab": "AB", "is_hit": "Hit", "is_bb": "BB", "is_sf": "SF",
        "bases": "TB", "盗塁": "SB", "打点": "RBI", "is_hr": "HR", "is_so": "SO"
    })

    # 規定打数（10打数）の適用
    stats = stats[stats["AB"] >= 10]

    if stats.empty:
        st.warning("規定打数（10打数）に到達している選択選手がいません。")
        return

    # セイバーメトリクス指標の算出
    stats["PA"] = stats["AB"] + stats["BB"] + stats["SF"]
    stats["AVG"] = stats.apply(lambda x: x["Hit"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
    stats["OBP"] = stats.apply(lambda x: (x["Hit"] + x["BB"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
    stats["SLG"] = stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
    stats["OPS"] = stats["OBP"] + stats["SLG"]
    stats["K_rate"] = stats.apply(lambda x: x["SO"] / x["PA"] if x["PA"] > 0 else 0, axis=1)
    
    # ★追加: RC (Runs Created) の算出
    stats["RC"] = stats.apply(
        lambda x: ((x["Hit"] + x["BB"]) * x["TB"]) / (x["AB"] + x["BB"]) if (x["AB"] + x["BB"]) > 0 else 0, 
        axis=1
    )

    # 打順選出用の独自スコア (RCも参考に加味可能ですが、ここではベースのスコアを維持)
    stats["Score_1"] = stats["OBP"] + (stats["SB"] * 0.02) - (stats["K_rate"] * 0.5)
    stats["Score_3"] = stats["OPS"] - (stats["K_rate"] * 0.5)
    stats["Score_9"] = stats["OBP"] + (stats["SB"] * 0.02)

    # ==========================================
    # 役割ごとのオーダー割り当て
    # ==========================================
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
    # ★追加: 守備位置の自動推論と割り当て
    # ==========================================
    valid_positions = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
    
    # 選出された選手が過去に守ったポジションの回数を集計
    pos_df = df_batting[df_batting["選手名"].isin(used_players) & df_batting["位置"].isin(valid_positions)]
    pos_counts = pos_df.groupby(["選手名", "位置"]).size().reset_index(name="count")
    
    # 守備経験が多い順にソート（競合時は経験回数が多い選手が優先される）
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
        
        # RCの表示を追加
        st.success(
            f"**{player_name}**\n\n"
            f"評価値({sort_col}): **{p[sort_col]:.3f}** | "
            f"打率: {p['AVG']:.3f} | 出塁率: {p['OBP']:.3f} | 長打率: {p['SLG']:.3f} | OPS: {p['OPS']:.3f} | RC: **{p['RC']:.2f}**\n\n"
            f"本塁打: {int(p['HR'])} | 打点: {int(p['RBI'])} | 盗塁: {int(p['SB'])} | 三振率: {p['K_rate']:.3f}"
        )
    
    st.divider()

    # 配置外（規定打席未到達など）のプレイヤーを表示
    unassigned = [p for p in selected_players if p not in used_players]
    if unassigned:
        st.info(f"📌 **規定打数(10打数)未到達の選択選手**: {', '.join(unassigned)}")