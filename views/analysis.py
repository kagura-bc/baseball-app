import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from config.settings import OFFICIAL_GAME_TYPES

# =========================================================
# 共通関数
# =========================================================

# ▼▼▼ 追加: 固定で除外するメンバーのリスト ▼▼▼
FIXED_EXCLUDE_LIST = [
    "助っ人1", "助っ人2", "依田裕樹", "小峠海晴"
]

def normalize_name(name):
    """名前からスペースを除去する"""
    return str(name).replace(" ", "").replace("　", "").strip()

def get_exclude_set():
    """Secretsから除外リストを読み込み、固定リストと結合して集合(set)にして返す"""
    # secrets.tomlから取得（存在しない場合は空リスト）
    raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
    
    # ▼▼▼ 修正: secretsのリストと固定リストを結合する ▼▼▼
    combined_list = list(raw_hidden) + FIXED_EXCLUDE_LIST
    
    return {normalize_name(n) for n in combined_list}

def filter_players(df, exclude_set):
    """データフレームから除外対象を除去する関数"""
    if "選手名" not in df.columns:
        return df
    
    # チーム記録は残すフラグ
    is_team_record = df["選手名"].astype(str).str.contains("チーム記録", na=False)
    
    # 名前の正規化
    clean_names = df["選手名"].apply(normalize_name)
    
    # フィルタリング
    mask = is_team_record | (~clean_names.isin(exclude_set))
    
    return df[mask]

# =========================================================
# メインの表示関数
# =========================================================
def show_analysis_page(df_batting, df_pitching):
    st.title("📈 データ分析 & 傾向")

    # ★ここで一回だけ除外リストを作成（これがどこでも使えるようになります）
    exclude_set = get_exclude_set()

    if df_batting.empty and df_pitching.empty:
        st.info("分析するデータがありません。")
        return

    # ★フィルター関数に作成した exclude_set を渡す
    df_b = filter_players(df_batting.copy(), exclude_set)
    df_p = filter_players(df_pitching.copy(), exclude_set)

    # =========================================================
    # ▼▼▼ 追加: analysis.py 側でも is_ab や is_hit を計算する ▼▼▼
    # =========================================================
    
    # データが空の場合でもエラーにならないよう、集計に必要な列をすべて0で作っておく
    required_columns = ["is_hit", "is_ab", "is_hr", "is_so", "is_1b", "is_2b", "is_3b", "is_bb", "is_sf", "bases", "打点", "盗塁", "得点"]
    for col in required_columns:
        if col not in df_b.columns:
            df_b[col] = 0

    if not df_b.empty and "結果" in df_b.columns:
        # 空白除去
        df_b["結果"] = df_b["結果"].astype(str).str.replace(r"\s+", "", regex=True)

        # 安打判定
        df_b["is_hit"] = df_b["結果"].str.contains("単打|二塁打|三塁打|本塁打", na=False).astype(int)
        
        # 打数(AB)判定
        non_ab_pattern = "四球|死球|四死球|犠打|犠飛|打撃妨害|得点|盗塁|牽制|代走|走塁|暴投|捕逸|ボーク|守備|交代"
        is_valid = ~df_b["結果"].isin(["", "nan", "None", "-"])
        is_not_excluded = ~df_b["結果"].str.contains(non_ab_pattern, na=False)
        df_b["is_ab"] = (is_valid & is_not_excluded).astype(int)

        # その他のフラグ
        df_b["is_hr"] = df_b["結果"].str.contains("本塁打", na=False).astype(int)
        df_b["is_so"] = df_b["結果"].str.contains("三振", na=False).astype(int)
        df_b["is_1b"] = df_b["結果"].str.contains("単打", na=False).astype(int)
        df_b["is_2b"] = df_b["結果"].str.contains("二塁打", na=False).astype(int)
        df_b["is_3b"] = df_b["結果"].str.contains("三塁打", na=False).astype(int)
        df_b["is_bb"] = df_b["結果"].str.contains("四球|死球|四死球", na=False).astype(int)
        df_b["is_sf"] = df_b["結果"].str.contains("犠飛", na=False).astype(int)
        
        # 塁打
        df_b["bases"] = (
            df_b["is_1b"] * 1 + df_b["is_2b"] * 2 + df_b["is_3b"] * 3 + df_b["is_hr"] * 4
        )

        # 打点・盗塁・得点を安全に数値化
        for c in ["打点", "盗塁", "得点"]:
            df_b[c] = pd.to_numeric(df_b[c], errors='coerce').fillna(0)

    # =========================================================
    # 🚑 名前の強力クリーニング
    # =========================================================
    df_b["選手名"] = df_b["選手名"].astype(str).str.replace("　", " ").str.strip()
    
    def normalize_names(name_list):
        return [str(n).replace("　", " ").strip() for n in name_list]
    
    # ---------------------------------------------------------
    # 日付変換とYear列の作成
    # ---------------------------------------------------------
    df_b["Date"] = pd.to_datetime(df_b["日付"], errors='coerce')
    df_p["Date"] = pd.to_datetime(df_p["日付"], errors='coerce')

    df_b["Year"] = df_b["Date"].dt.year.astype(str).str.replace('.0', '', regex=False)
    df_p["Year"] = df_p["Date"].dt.year.astype(str).str.replace('.0', '', regex=False)

    years = sorted([y for y in df_b["Year"].unique() if y not in ['nan', 'NaT']], reverse=True)
    c1, c2 = st.columns(2)
    selected_year = c1.selectbox("対象年度", ["全期間"] + list(years))
    
    game_types = ["すべて", "公式戦のみ", "練習試合のみ"]
    selected_type = c2.selectbox("試合種別", game_types)

    if selected_year != "全期間":
        df_b = df_b[df_b["Year"] == selected_year]
        df_p = df_p[df_p["Year"] == selected_year]
    
    if selected_type == "公式戦のみ":
        df_b = df_b[df_b["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        df_p = df_p[df_p["試合種別"].isin(OFFICIAL_GAME_TYPES)]
    elif selected_type == "練習試合のみ":
        df_b = df_b[df_b["試合種別"] == "練習試合"]
        df_p = df_p[df_p["試合種別"] == "練習試合"]

    # ---------------------------------------------------------
    # ゲーム単位のデータセット作成 (得点計算 + FirstScore判定)
    # ---------------------------------------------------------
    games_list = []
    # 試合種別も含めてグループ化
    for (d, opp, m_type), g_b in df_b.groupby(["Date", "対戦相手", "試合種別"]):
        g_p = df_p[(df_p["Date"] == d) & (df_p["対戦相手"] == opp) & (df_p["試合種別"] == m_type)]
        
        # 1. チーム記録行と個人行を分離して計算
        is_team_rec = g_b["選手名"].astype(str).str.contains("チーム記録", na=False)
        team_rows = g_b[is_team_rec]
        indiv_rows = g_b[~is_team_rec]
        
        if not team_rows.empty:
            my_score = pd.to_numeric(team_rows["得点"], errors='coerce').fillna(0).sum()
        else:
            my_score = pd.to_numeric(indiv_rows["得点"], errors='coerce').fillna(0).sum()

        is_p_team_rec = g_p["選手名"].astype(str).str.contains("チーム記録", na=False)
        p_team_rows = g_p[is_p_team_rec]
        p_indiv_rows = g_p[~is_p_team_rec]

        if not p_team_rows.empty:
            opp_score = pd.to_numeric(p_team_rows["失点"], errors='coerce').fillna(0).sum()
        else:
            opp_score = pd.to_numeric(p_indiv_rows["失点"], errors='coerce').fillna(0).sum()

        # 2. 勝敗判定
        res = "Win" if my_score > opp_score else ("Lose" if my_score < opp_score else "Draw")

        # 3. 先制判定 (FirstScoreの計算)
        def get_inn_num(t):
            t = str(t).replace("回", "")
            return int(t) if t.isdigit() else 99

        my_inn_scores = g_b[g_b["イニング"].astype(str).str.contains("回")].copy()
        my_inn_scores["InnNum"] = my_inn_scores["イニング"].apply(get_inn_num)
        my_score_inns = my_inn_scores[pd.to_numeric(my_inn_scores["得点"], errors='coerce') > 0].sort_values("InnNum")
        min_my_inn = my_score_inns["InnNum"].iloc[0] if not my_score_inns.empty else 99

        opp_inn_scores = g_p[g_p["イニング"].astype(str).str.contains("回")].copy()
        opp_inn_scores["InnNum"] = opp_inn_scores["イニング"].apply(get_inn_num)
        opp_score_inns = opp_inn_scores[pd.to_numeric(opp_inn_scores["失点"], errors='coerce') > 0].sort_values("InnNum")
        min_opp_inn = opp_score_inns["InnNum"].iloc[0] if not opp_score_inns.empty else 99

        first_score_team = "自チーム" if min_my_inn < min_opp_inn else ("相手" if min_opp_inn < min_my_inn else "なし(0-0)")

        # 4. 辞書に追加 (FirstScore を忘れずに入れています)
        games_list.append({
            "Date": d, "Opponent": opp, "MyScore": my_score, 
            "OppScore": opp_score, "Result": res, "FirstScore": first_score_team
        })
    
    df_games = pd.DataFrame(games_list)

    # ---------------------------------------------------------
    # タブ構成
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 チーム傾向", "🆚 対戦相手別", "⏱️ イニング・先制率", "🔍 詳細投打分析", "🧠 理想オーダー", "🤝 チーム貢献度"])

    # =========================================================
    # Tab 1: チーム傾向 
    # =========================================================
    with tab1:
        if df_games.empty:
            st.warning("データ不足のため表示できません")
        else:
            st.markdown("### 🦅 KAGURA チームステータス")
            total_runs = df_games["MyScore"].sum()
            total_lost = df_games["OppScore"].sum()
            wins = len(df_games[df_games["Result"]=="Win"])
            total_g = len(df_games)
            actual_rate = wins / total_g if total_g > 0 else 0
            
            pyth_rate = 0.0
            if (total_runs + total_lost) > 0:
                pyth_rate = (total_runs**2) / ((total_runs**2) + (total_lost**2))
            
            luck_diff = actual_rate - pyth_rate
            
            if luck_diff > 0.1: luck_msg = "🌟 豪運！接戦に強い！"
            elif luck_diff > 0.05: luck_msg = "🍀 勝ち運あり"
            elif luck_diff > -0.05: luck_msg = "⚖️ 実力通り"
            elif luck_diff > -0.1: luck_msg = "☁️ 少しツキがないかも"
            else: luck_msg = "☔ 不運...次は勝てる！"

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("試合数", f"{total_g} 試合", f"{wins}勝")
            k2.metric("勝率", f"{actual_rate:.3f}", f"貯金 {wins - (total_g - wins - len(df_games[df_games['Result']=='Draw']))}")
            k3.metric("平均得点", f"{df_games['MyScore'].mean():.1f}", delta=f"失点 {df_games['OppScore'].mean():.1f}", delta_color="normal")
            k4.metric("チームの運勢", luck_msg, f"期待勝率 {pyth_rate:.3f}")

            st.divider()

            st.markdown("### 🔥 勝ち方のスタイル診断")
            c_style = alt.Chart(df_games).mark_circle(size=100).encode(
                x=alt.X("MyScore", title="自チーム得点", scale=alt.Scale(domain=[0, max(15, df_games['MyScore'].max())])),
                y=alt.Y("OppScore", title="相手チーム得点", scale=alt.Scale(domain=[0, max(15, df_games['OppScore'].max())])),
                color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=["#ef4444", "#3b82f6", "#9ca3af"]), legend=alt.Legend(title="勝敗")),
                tooltip=["Date", "Opponent", "MyScore", "OppScore", "Result"]
            ).interactive()

            avg_my = df_games["MyScore"].mean()
            avg_opp = df_games["OppScore"].mean()
            rule_x = alt.Chart(pd.DataFrame({'x': [avg_my]})).mark_rule(color="gray", strokeDash=[3,3]).encode(x='x')
            rule_y = alt.Chart(pd.DataFrame({'y': [avg_opp]})).mark_rule(color="gray", strokeDash=[3,3]).encode(y='y')
            
            text_data = pd.DataFrame([
                {"x": 14, "y": 1, "text": "💎 圧勝ゾーン", "col": "gray"},
                {"x": 1, "y": 14, "text": "💀 完敗ゾーン", "col": "gray"},
                {"x": 14, "y": 14, "text": "🔥 乱打戦", "col": "gray"},
                {"x": 1, "y": 1, "text": "🛡️ 投手戦", "col": "gray"},
            ])
            text_layer = alt.Chart(text_data).mark_text(align='center', baseline='middle', fontSize=14, fontWeight='bold', opacity=0.3).encode(
                x='x', y='y', text='text', color='col'
            )

            st.altair_chart(c_style + rule_x + rule_y + text_layer, use_container_width=True)

            st.divider()
            col_v1, col_v2 = st.columns([1.5, 1])
            with col_v1:
                st.markdown("### ✨ KAGURAの『勝利の法則』")
                score_bins = df_games.copy()
                score_win_rate = score_bins.groupby("MyScore").agg(
                    GameCount=("Result", "count"),
                    WinCount=("Result", lambda x: (x=="Win").sum())
                ).reset_index()
                score_win_rate["WinRate"] = score_win_rate["WinCount"] / score_win_rate["GameCount"]

                base_chart = alt.Chart(score_win_rate).encode(x=alt.X("MyScore:O", title="得点"))
                bar_c = base_chart.mark_bar(opacity=0.3, color="#64748b").encode(y=alt.Y("GameCount", title="試合回数"))
                line_c = base_chart.mark_line(point=True, color="#e11d48").encode(
                    y=alt.Y("WinRate", title="勝率", axis=alt.Axis(format="%")),
                    tooltip=["MyScore", "GameCount", alt.Tooltip("WinRate", format=".0%")]
                )
                st.altair_chart((bar_c + line_c).resolve_scale(y='independent'), use_container_width=True)

            with col_v2:
                magic_num = 0
                for index, row in score_win_rate.iterrows():
                    if row["WinRate"] >= 0.8:
                        magic_num = int(row["MyScore"])
                        break
                
                st.markdown(f"""
                <div style="background-color:#f1f5f9; padding:15px; border-radius:10px; text-align:center; margin-top:20px;">
                    <div style="font-size:16px; color:#64748b;">勝利のマジックナンバー</div>
                    <div style="font-size:48px; font-weight:bold; color:#e11d48;">{magic_num}点</div>
                    <div style="font-size:14px;">{magic_num}点以上取った時の勝率は<br>驚異の <strong>{int(score_win_rate[score_win_rate['MyScore']>=magic_num]['WinRate'].mean()*100)}%</strong> です！</div>
                </div>
                """, unsafe_allow_html=True)

                st.write("")
                st.markdown("**📅 直近5試合の勝敗**")
                recent = df_games.sort_values("Date", ascending=False).head(5)
                cols = st.columns(5)
                for i, (_, r) in enumerate(recent.iterrows()):
                    icon = "🔴" if r["Result"] == "Win" else "🔵" if r["Result"] == "Lose" else "⚪"
                    cols[i].markdown(f"<div style='text-align:center; font-size:24px;'>{icon}</div>", unsafe_allow_html=True)
                    cols[i].caption(f"{r['Date'].strftime('%m/%d')}")

    # =========================================================
    # Tab 2: 対戦相手別
    # =========================================================
    with tab2:
        if df_games.empty:
            st.warning("データなし")
        else:
            st.markdown("##### 🔍 対戦相手別成績とデバッグ")
            
            # --- データのクレンジングと集計準備 ---
            # 1. 重複排除 (DateとOpponentが同じなら同一試合とみなす)
            # ここで drop_duplicates を使うことで、もしdf_gamesに重複があっても1試合1行にします
            df_clean = df_games.drop_duplicates(subset=["Date", "Opponent"]).copy()
            
            # 2. 数値変換
            df_clean["MyScore"] = pd.to_numeric(df_clean["MyScore"], errors='coerce').fillna(0)
            df_clean["OppScore"] = pd.to_numeric(df_clean["OppScore"], errors='coerce').fillna(0)
            
            # 3. [デバッグ表示] 計算対象のデータを確認
            # ここでDarkLegionの行が1行だけであることを確認してください
            with st.expander("データの計算内訳を確認する（デバッグ）"):
                st.write("計算に使われているデータ（DarkLegionのみ）:")
                st.dataframe(df_clean[df_clean["Opponent"] == "DarkLegion"])
                st.caption("※ここが1行で、得点が正しい数値（10など）になっていれば、平均も正しく計算されます。")

            # 4. 対戦相手別に集計
            opp_stats = df_clean.groupby("Opponent").agg(
                試合数=("Result", "count"), 
                勝利=("Result", lambda x: (x=="Win").sum()), 
                敗戦=("Result", lambda x: (x=="Lose").sum()),
                引分=("Result", lambda x: (x=="Draw").sum()), 
                平均得点=("MyScore", "mean"), 
                平均失点=("OppScore", "mean")
            ).reset_index()
            
            # 5. 勝率計算
            opp_stats["勝率"] = opp_stats.apply(
                lambda x: x["勝利"] / (x["勝利"] + x["敗戦"]) if (x["勝利"] + x["敗戦"]) > 0 else 0, 
                axis=1
            )
            
            # 6. 並び替え
            opp_stats = opp_stats.sort_values("試合数", ascending=False).reset_index(drop=True)

            # 7. 表示
            st.dataframe(
                opp_stats.style.format({"平均得点": "{:.1f}", "平均失点": "{:.1f}", "勝率": "{:.3f}"})
                         .background_gradient(subset=["勝率"], cmap="Reds"),
                use_container_width=True,
                hide_index=True
            )

            # 8. グラフ描画
            opp_stats["得失差"] = opp_stats["平均得点"] - opp_stats["平均失点"]
            bar_diff = (
                alt.Chart(opp_stats)
                .mark_bar()
                .encode(
                    x=alt.X("Opponent:N", sort="-y", title="対戦相手"),
                    y=alt.Y("得失差:Q", title="平均得失点差"),
                    color=alt.condition(alt.datum.得失差 > 0, alt.value("#e11d48"), alt.value("#1e40af")),
                    tooltip=[
                        alt.Tooltip("Opponent:N", title="対戦相手"),
                        alt.Tooltip("試合数:Q", title="試合数"),
                        alt.Tooltip("平均得点:Q", title="平均得点", format=".1f"),
                        alt.Tooltip("平均失点:Q", title="平均失点", format=".1f"),
                        alt.Tooltip("得失差:Q", title="得失差", format=".1f"),
                        alt.Tooltip("勝率:Q", title="勝率", format=".3f")
                    ]
                )
                .properties(height=400)
            )
            st.altair_chart(bar_diff, use_container_width=True)


    # =========================================================
    # Tab 3: イニング・先制率
    # =========================================================
    with tab3:
        c3_1, c3_2 = st.columns(2)
        with c3_1:
            st.markdown("##### ⏱️ 先制時の勝率")
            if not df_games.empty:
                games_first = df_games[df_games["FirstScore"] == "自チーム"]
                if not games_first.empty:
                    w = len(games_first[games_first["Result"]=="Win"])
                    l = len(games_first[games_first["Result"]=="Lose"])
                    d = len(games_first[games_first["Result"]=="Draw"])
                    rate = w / (w+l) if (w+l) > 0 else 0
                    st.metric("先制した試合数", f"{len(games_first)}試合", f"勝率: {rate:.3f}")
                    
                    df_f_res = pd.DataFrame({"Result": ["Win", "Lose", "Draw"], "Count": [w, l, d]})
                    pie_f = alt.Chart(df_f_res).mark_arc(innerRadius=40).encode(
                        theta="Count", color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=["#e11d48", "#1e40af", "#94a3b8"])), tooltip=["Result", "Count"]
                    )
                    st.altair_chart(pie_f, use_container_width=True)
                else:
                    st.info("先制した試合がありません")

                st.markdown("##### 😱 先制された時の勝率")
                games_opp_first = df_games[df_games["FirstScore"] == "相手"]
                if not games_opp_first.empty:
                    w2 = len(games_opp_first[games_opp_first["Result"]=="Win"])
                    l2 = len(games_opp_first[games_opp_first["Result"]=="Lose"])
                    d2 = len(games_opp_first[games_opp_first["Result"]=="Draw"])
                    rate2 = w2 / (w2+l2) if (w2+l2) > 0 else 0
                    st.metric("先制された試合数", f"{len(games_opp_first)}試合", f"勝率: {rate2:.3f}")

                    df_f_opp_res = pd.DataFrame({"Result": ["Win", "Lose", "Draw"], "Count": [w2, l2, d2]})
                    pie_f_opp = alt.Chart(df_f_opp_res).mark_arc(innerRadius=40).encode(
                        theta="Count", color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=["#e11d48", "#1e40af", "#94a3b8"])), tooltip=["Result", "Count"]
                    )
                    st.altair_chart(pie_f_opp, use_container_width=True)
                else:
                    st.info("先制された試合がありません")

        with c3_2:
            st.markdown("##### 🔢 イニング別得失点")
            def aggregate_innings(df_raw, score_col):
                df_i = df_raw.copy()
                df_i = df_i[df_i["イニング"].astype(str).str.match(r"^[1-9]回$")]
                df_i["得点"] = pd.to_numeric(df_i[score_col], errors='coerce').fillna(0)
                return df_i.groupby("イニング")["得点"].sum()

            inn_scores = aggregate_innings(df_b, "得点")
            inn_lost = aggregate_innings(df_p, "失点")
            
            df_inn = pd.DataFrame({"得点": inn_scores, "失点": inn_lost}).fillna(0).reset_index()
            df_inn["InnNum"] = df_inn["イニング"].apply(lambda x: int(x.replace("回", "")))
            df_inn = df_inn.sort_values("InnNum")

            df_inn_melt = df_inn.melt(id_vars=["イニング", "InnNum"], value_vars=["得点", "失点"], var_name="Type", value_name="Runs")
            
            bar_inn = alt.Chart(df_inn_melt).mark_bar().encode(
                x=alt.X("イニング", sort=alt.EncodingSortField(field="InnNum", order="ascending")),
                y="Runs",
                color=alt.Color("Type", scale=alt.Scale(domain=["得点", "失点"], range=["#e11d48", "#1e40af"])),
                column="Type",
                tooltip=["イニング", "Runs"]
            )
            st.altair_chart(bar_inn, use_container_width=True)
            st.dataframe(df_inn[["イニング", "得点", "失点"]].set_index("イニング").T, use_container_width=True)
    
    # =========================================================
    # Tab 4: 詳細投打データ分析（2026年以降） ★改修箇所★
    # =========================================================
    with tab4:
        st.markdown("## 🔍 詳細投打データ分析 (2026年以降)")
        st.caption("※詳細な記録を取り始めた2026年以降のデータを集計しています。打球の種類ごとの傾向を追加しました。")

        df_b_detail = df_batting[pd.to_datetime(df_batting["日付"], errors='coerce').dt.year >= 2026].copy() if not df_batting.empty else pd.DataFrame()
        df_p_detail = df_pitching[pd.to_datetime(df_pitching["日付"], errors='coerce').dt.year >= 2026].copy() if not df_pitching.empty else pd.DataFrame()

        # ▼▼▼ 追加: 外野のゴロ失策（ヒット＆エラー等での2重カウント回避）を除外 ▼▼▼
        def remove_outfield_goro_error(df):
            if df.empty or "打球方向" not in df.columns or "結果" not in df.columns:
                return df
            # 打球方向が外野であり、かつ結果に「失策」と「ゴロ」が両方含まれる行を判定
            is_outfield = df["打球方向"].astype(str).str.strip().isin(["左", "中", "右"])
            is_error = df["結果"].astype(str).str.contains("失策", na=False)
            is_goro = df["結果"].astype(str).str.contains("ゴロ", na=False)
            
            # 条件に合致する行（外野ゴロエラー）を除外
            return df[~(is_outfield & is_error & is_goro)].copy()

        df_b_detail = remove_outfield_goro_error(df_b_detail)
        df_p_detail = remove_outfield_goro_error(df_p_detail)
        # ▲▲▲ 追加ここまで ▲▲▲

        # ▼▼▼ 追加: 打球種類の判定関数 ▼▼▼
        def classify_hit_type(res):
            res = str(res)
            if "ゴロ" in res or "併殺" in res: return "ゴロ"
            elif "フライ" in res or "犠飛" in res or "飛" in res: return "フライ"
            elif "ライナー" in res or "直" in res: return "ライナー"
            elif "三振" in res or "四球" in res or "死球" in res or "四死球" in res: return "非打球"
            elif any(x in res for x in ["単打", "二塁打", "三塁打", "本塁打", "安"]): return "安打"
            else: return "その他"

        if not df_b_detail.empty and "結果" in df_b_detail.columns:
            df_b_detail["打球種類"] = df_b_detail["結果"].apply(classify_hit_type)
        if not df_p_detail.empty and "結果" in df_p_detail.columns:
            df_p_detail["打球種類"] = df_p_detail["結果"].apply(classify_hit_type)

        # 共通のカラースケール定義
        hit_type_color_scale = alt.Scale(
            domain=["ゴロ", "フライ", "ライナー", "安打", "非打球", "その他"],
            range=["#eab308", "#3b82f6", "#22c55e", "#ef4444", "#64748b", "#9ca3af"]
        )
        pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
        # ▲▲▲ 追加ここまで ▲▲▲

        detail_menu = st.selectbox(
            "📂 見たい分析項目を選んでください", 
            ["チーム全体の傾向", "個人の打撃分析", "個人の投手分析"],
            key="detail_analysis_menu"
        )
        st.divider()

        # --- チーム全体の傾向 ---
        if detail_menu == "チーム全体の傾向":
            st.markdown("#### 🏢 チーム全体のプレースタイル")
            
            st.markdown("##### チーム打球傾向 (アウトの内訳)")
            if not df_b_detail.empty:
                t_goro = len(df_b_detail[df_b_detail["結果"].astype(str).str.contains("ゴロ|併殺打")])
                t_fly = len(df_b_detail[df_b_detail["結果"].astype(str).str.contains("フライ|犠飛")])
                t_so = len(df_b_detail[df_b_detail["結果"].astype(str).str.contains("三振")])
                
                df_t_out = pd.DataFrame({"種類": ["ゴロアウト", "フライアウト", "三振"], "数": [t_goro, t_fly, t_so]})
                if df_t_out["数"].sum() > 0:
                    pie_t_out = alt.Chart(df_t_out).mark_arc(innerRadius=40).encode(
                        theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロアウト", "フライアウト", "三振"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
                    ).properties(height=300)
                    st.altair_chart(pie_t_out, use_container_width=True)
                else:
                    st.caption("データがありません")
            else:
                st.caption("2026年以降の打撃データがありません")
                    
            st.write("")
            st.markdown("##### チーム投手陣のアウト取得傾向")
            if not df_p_detail.empty:
                df_p_out_only = df_p_detail[~df_p_detail["結果"].astype(str).str.contains("失策|振り逃げ", na=False)]
                
                p_goro = len(df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("ゴロ|併殺打")])
                p_fly = len(df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("フライ")])
                p_so = len(df_p_out_only[df_p_out_only["結果"].astype(str).str.contains("三振")])
                
                df_p_out = pd.DataFrame({"種類": ["ゴロで打たせてとる", "フライアウト", "三振で奪う"], "数": [p_goro, p_fly, p_so]})
                if df_p_out["数"].sum() > 0:
                    pie_p_out = alt.Chart(df_p_out).mark_arc(innerRadius=40).encode(
                        theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロで打たせてとる", "フライアウト", "三振で奪う"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
                    ).properties(height=300)
                    st.altair_chart(pie_p_out, use_container_width=True)
                else:
                    st.caption("詳細な投手データがありません")
            else:
                st.caption("2026年以降の投手データがありません")

            st.write("")
            st.markdown("##### 🏟️ ポジション別の打球方向と種類")
            
            c_dir1, c_dir2 = st.columns(2)
            
            with c_dir1:
                st.markdown("**▼ チーム打撃 (どこへ・どんな打球を打っているか)**")
                if "打球方向" in df_b_detail.columns:
                    b_dir_data = df_b_detail[df_b_detail["打球方向"].notna() & (df_b_detail["打球方向"] != "") & (df_b_detail["打球方向"] != "nan")].copy()
                    if not b_dir_data.empty:
                        b_dir_data["方向"] = b_dir_data["打球方向"].astype(str).str.strip()
                        b_dir_counts = b_dir_data.groupby(["方向", "打球種類"]).size().reset_index(name="数")
                        
                        bar_b_dir = alt.Chart(b_dir_counts).mark_bar().encode(
                            x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("数:Q", title="打球数"),
                            color=alt.Color("打球種類:N", scale=hit_type_color_scale),
                            tooltip=["方向", "打球種類", "数"]
                        ).properties(height=280)
                        st.altair_chart(bar_b_dir, use_container_width=True)
                    else:
                        st.caption("データがありません")
            
            with c_dir2:
                st.markdown("**▼ チーム投手陣 (どこへ・どんな打球を打たせているか)**")
                if "打球方向" in df_p_detail.columns:
                    p_dir_data = df_p_detail[df_p_detail["打球方向"].notna() & (df_p_detail["打球方向"] != "") & (df_p_detail["打球方向"] != "nan")].copy()
                    if not p_dir_data.empty:
                        p_dir_data["方向"] = p_dir_data["打球方向"].astype(str).str.strip()
                        p_dir_counts = p_dir_data.groupby(["方向", "打球種類"]).size().reset_index(name="数")
                        
                        bar_p_dir = alt.Chart(p_dir_counts).mark_bar().encode(
                            x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                            y=alt.Y("数:Q", title="打球数"),
                            color=alt.Color("打球種類:N", scale=hit_type_color_scale),
                            tooltip=["方向", "打球種類", "数"]
                        ).properties(height=280)
                        st.altair_chart(bar_p_dir, use_container_width=True)
                    else:
                        st.caption("データがありません")

        # --- 個人の打撃分析 ---
        elif detail_menu == "個人の打撃分析":
            if not df_b_detail.empty:
                players_b = sorted(df_b_detail[df_b_detail["選手名"] != "チーム記録"]["選手名"].dropna().unique())
                if players_b:
                    target_b_player = st.selectbox("分析する打者を選択", players_b, key="ana_bat_player")
                    my_b = df_b_detail[df_b_detail["選手名"] == target_b_player].copy()
                    
                    if not my_b.empty:
                        st.markdown(f"#### {target_b_player} の打球傾向（方向×種類）")
                        def show_player_direction_chart(data_df, title_label):
                            if "打球方向" not in data_df.columns: return
                            valid_df = data_df[data_df["打球方向"].notna() & (data_df["打球方向"] != "") & (data_df["打球方向"] != "nan")].copy()
                            if not valid_df.empty:
                                valid_df["方向"] = valid_df["打球方向"].astype(str).str.strip()
                                dir_counts = valid_df.groupby(["方向", "打球種類"]).size().reset_index(name="数")
                                
                                bar_dir = alt.Chart(dir_counts).mark_bar().encode(
                                    x=alt.X("方向:N", sort=pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                                    y=alt.Y("数:Q", title="打球数"),
                                    color=alt.Color("打球種類:N", scale=hit_type_color_scale),
                                    tooltip=["方向", "打球種類", "数"]
                                ).properties(height=250)
                                st.altair_chart(bar_dir, use_container_width=True)
                            else:
                                st.caption(f"（{title_label} の方向データはありません）")

                        st.markdown("**■ 全体 (安打・凡退含む)**")
                        show_player_direction_chart(my_b, "全体")
                        
                        hit_results = ["単打", "二塁打", "三塁打", "本塁打"]
                        out_results = ["凡退(ゴロ)", "凡退(フライ)", "併殺打", "野選", "失策"]
                        st.markdown("**■ 安打時**")
                        show_player_direction_chart(my_b[my_b["結果"].isin(hit_results)], "安打時")
                        st.markdown("**■ 凡退・失策時**")
                        show_player_direction_chart(my_b[my_b["結果"].isin(out_results)], "凡退時")
                        
                        st.divider()
                        st.markdown(f"#### {target_b_player} のゴロ/フライ比率 (GO/AO)")
                        my_goro = len(my_b[my_b["結果"].astype(str).str.contains("ゴロ|併殺打")])
                        my_fly = len(my_b[my_b["結果"].astype(str).str.contains("フライ|犠飛")])
                        st.metric("ゴロアウト数", my_goro)
                        st.metric("フライアウト数", my_fly)
                        if my_fly > 0:
                            st.metric("GO/AO (ゴロ÷フライ)", f"{my_goro / my_fly:.2f}", help="1.0以上ならゴロヒッター、未満ならフライヒッターと言えます。")
                        else:
                            st.write("※ フライアウトが0のため比率計算不可")
                    else:
                        st.write("該当選手のデータなし")
                else:
                    st.write("対象となる選手がいません")
            else:
                st.info("2026年以降の打撃データがありません")

        # --- 個人の投手分析 ---
        elif detail_menu == "個人の投手分析":
            if not df_p_detail.empty:
                players_p = sorted(df_p_detail[(df_p_detail["選手名"] != "チーム記録") & (df_p_detail["選手名"].notna())]["選手名"].unique())
                if players_p:
                    target_p_player = st.selectbox("分析する投手を選択", players_p, key="ana_pit_player")
                my_p = df_p_detail[df_p_detail["選手名"] == target_p_player].copy()
                if not my_p.empty:
                    st.markdown(f"#### {target_p_player} のアウトの取り方")
                    my_p_out_only = my_p[~my_p["結果"].astype(str).str.contains("失策", na=False)]
                    
                    out_goro = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("ゴロ|併殺打")])
                    out_fly = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("フライ")])
                    out_so = len(my_p_out_only[my_p_out_only["結果"].astype(str).str.contains("三振")])
                    
                    df_my_p_out = pd.DataFrame({"種類": ["ゴロ", "フライ", "三振"], "数": [out_goro, out_fly, out_so]})
                    if df_my_p_out["数"].sum() > 0:
                        pie_my_p = alt.Chart(df_my_p_out).mark_arc(innerRadius=50).encode(
                            theta="数", color=alt.Color("種類", scale=alt.Scale(domain=["ゴロ", "フライ", "三振"], range=["#eab308", "#3b82f6", "#ef4444"])), tooltip=["種類", "数"]
                        ).properties(height=300)
                        st.altair_chart(pie_my_p, use_container_width=True)
                    else:
                        st.info("詳細なアウトデータがありません。")

                    st.write("")
                    st.divider()
                    st.markdown(f"#### {target_p_player} の打たせた打球方向と種類")
                    
                    if "打球方向" in my_p.columns:
                        valid_p_df = my_p[my_p["打球方向"].notna() & 
                                          (my_p["打球方向"] != "") & 
                                          (my_p["打球方向"] != "nan") & 
                                          (my_p["打球方向"] != "---")].copy()
                        
                        if not valid_p_df.empty:
                            valid_p_df["方向"] = valid_p_df["打球方向"].astype(str).str.strip()
                            
                            if "打球種類" not in valid_p_df.columns:
                                valid_p_df["打球種類"] = "その他"
                                
                            def determine_hit_type(res, current_type):
                                res_s = str(res)
                                if "本塁打" in res_s: return "本塁打"
                                if "二塁打" in res_s or "三塁打" in res_s: return "長打"
                                if "単打" in res_s or "安打" in res_s: return "単打"
                                
                                if current_type != "その他" and pd.notna(current_type) and current_type != "":
                                    return current_type 
                                    
                                if "ゴロ" in res_s: return "ゴロ"
                                if "フライ" in res_s or "飛" in res_s: return "フライ"
                                if "直" in res_s or "ライナー" in res_s: return "ライナー"
                                return "その他"
                                
                            valid_p_df["打球種類"] = valid_p_df.apply(lambda row: determine_hit_type(row["結果"], row.get("打球種類")), axis=1)

                            p_indiv_dir_counts = valid_p_df.groupby(["方向", "打球種類"]).size().reset_index(name="数")
                            
                            if not p_indiv_dir_counts.empty:
                                safe_pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                                
                                bar_p_dir_indiv = alt.Chart(p_indiv_dir_counts).mark_bar().encode(
                                    x=alt.X("方向:N", sort=safe_pos_order, title="ポジション", axis=alt.Axis(labelAngle=0)),
                                    y=alt.Y("数:Q", title="打球数"),
                                    color=alt.Color("打球種類:N", scale=alt.Scale(
                                        domain=["ゴロ", "フライ", "ライナー", "単打", "長打", "本塁打", "その他"], 
                                        range=["#eab308", "#3b82f6", "#22c55e", "#ef4444", "#a855f7", "#ec4899", "#9ca3af"]
                                    )),
                                    tooltip=["方向", "打球種類", "数"]
                                ).properties(height=250)
                                
                                st.altair_chart(bar_p_dir_indiv, use_container_width=True)
                            else:
                                st.caption("有効な打球方向のデータがありません。")
                        else:
                            st.caption("打球方向のデータがありません。")
                    else:
                        st.caption("打球方向の列が見つかりません。")
                        
                        st.write("")
                        st.divider()
                        st.markdown(f"#### {target_p_player} の被安打・四死球の傾向")
                        hit_1 = len(my_p[my_p["結果"].astype(str).str.contains("単打|安打")])
                        hit_2 = len(my_p[my_p["結果"].astype(str).str.contains("二塁打")])
                        hit_3 = len(my_p[my_p["結果"].astype(str).str.contains("三塁打")])
                        hit_hr = len(my_p[my_p["結果"].astype(str).str.contains("本塁打")])
                        give_bb = len(my_p[my_p["結果"].astype(str).str.contains("四球|死球")])
                        
                        df_my_p_hit = pd.DataFrame({
                            "結果": ["単打", "長打(二・三塁打)", "本塁打", "四死球"], "数": [hit_1, hit_2 + hit_3, hit_hr, give_bb]
                        })
                        if df_my_p_hit["数"].sum() > 0:
                            bar_my_p = alt.Chart(df_my_p_hit).mark_bar().encode(
                                x=alt.X("結果:N", sort=["単打", "長打(二・三塁打)", "本塁打", "四死球"]), y="数:Q", color=alt.Color("結果:N", legend=None), tooltip=["結果", "数"]
                            ).properties(height=300)
                            st.altair_chart(bar_my_p, use_container_width=True)
                        else:
                            st.info("被安打・四死球の詳細データがありません。")
                else:
                    st.write("該当選手のデータなし")
            else:
                st.write("対象となる投手がいません")
        else:
            st.info("2026年以降の投手データがありません")

    with tab5:
        st.markdown("### 🤖 統計データに基づく推奨オーダー")
        
        # 1. 複数のリストを取得して統合
        raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
        fixed_list = st.secrets.get("FIXED_EXCLUDE_LIST", [])
        
        # 【重要】リストを結合し、さらにそれぞれを正規化する
        # これにより、データフレーム側の正規化された名前と完全にマッチさせます
        all_exclude_names = raw_hidden + fixed_list
        exclude_set = {normalize_name(n) for n in all_exclude_names}

        if not df_b.empty:
            # 1. データのクレンジング
            df_calc = df_b[df_b["選手名"] != "チーム記録"].copy()
            
            # 正規化した名前でフィルタリング
            # (apply(normalize_name) は上で定義した共通関数を使用)
            df_calc["_temp_norm"] = df_calc["選手名"].apply(normalize_name)
            
            # 【重要】正規化された同士を比較
            df_calc = df_calc[~df_calc["_temp_norm"].isin(exclude_set)]

            if df_calc.empty:
                st.warning("除外設定の結果、表示できるデータがなくなりました。")
            else:
                # 2. 基本スタッツの集計
                # ... (以下、元の計算処理) ...
                hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
                df_calc["Hit"] = df_calc["結果"].isin(hit_cols).astype(int)
                df_calc["BB"] = df_calc["結果"].isin(["四球", "死球"]).astype(int)
                df_calc["AB"] = df_calc["結果"].isin(hit_cols + ["凡退", "三振", "失策", "併殺打", "野選"]).astype(int)
                df_calc["PA"] = 1 
                
                tb_map = {"単打":1, "二塁打":2, "三塁打":3, "本塁打":4}
                df_calc["TB"] = df_calc["結果"].map(tb_map).fillna(0)
                df_calc["TB"] = pd.to_numeric(df_calc["TB"], errors='coerce').fillna(0)
                df_calc["SB"] = pd.to_numeric(df_calc["盗塁"], errors='coerce').fillna(0)
                
                stats = df_calc.groupby("選手名").agg({
                    "PA": "sum", "AB": "sum", "Hit": "sum", "BB": "sum", "TB": "sum", "SB": "sum"
                }).reset_index()
                
                # 3. 最低打席数フィルタ
                max_pa = int(stats["PA"].max()) if not stats.empty else 0
                default_pa = min(20, max_pa)
                min_pa = st.slider("対象とする最低打席数", 0, max_pa, default_pa)
                stats = stats[stats["PA"] >= min_pa]

                if not stats.empty:
                    # 4. 指標計算
                    stats["OBP"] = stats.apply(lambda x: (x["Hit"] + x["BB"]) / x["PA"] if x["PA"] > 0 else 0, axis=1)
                    stats["SLG"] = stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                    stats["OPS"] = stats["OBP"] + stats["SLG"]
                    
                    candidates = stats.copy()
                    used_players = []

                    # 5. 打順生成ロジック
                    def pick_player(df_source, sort_col, role_name, description):
                        available = df_source[~df_source["選手名"].isin(used_players)].sort_values(sort_col, ascending=False)
                        st.markdown(f"##### {len(used_players)+1}番: {role_name}")
                        st.caption(description)
                        
                        if not available.empty:
                            p = available.iloc[0]
                            st.success(f"**{p['選手名']}** ({sort_col}: {p[sort_col]:.3f})")
                            used_players.append(p["選手名"])
                        else:
                            st.info("候補選手なし")
                    
                    st.divider()
                    candidates["LeadOff"] = candidates["OBP"] + (candidates["SB"] * 0.05)
                    
                    pick_player(candidates, "LeadOff", "リードオフマン", "出塁率と走塁能力が高い選手")
                    pick_player(candidates, "OBP", "チャンスメーカー", "チーム一の出塁率で後続に繋ぐ")
                    pick_player(candidates, "OPS", "強打の3番", "走者を返す能力と長打力")
                    pick_player(candidates, "SLG", "主砲", "チームNo.1の長打力で一気に走者を返す")
                    pick_player(candidates, "OPS", "ポイントゲッター", "チャンスで回ってくるためOPS重視")
                    
                    for i in range(6, 10):
                        pick_player(candidates, "OPS", f"{i}番打者", "総合的な打撃力で繋ぐ")
                else:
                    st.info("条件を満たす選手がいません。")
        else:
            st.info("データがありません。")
            
    with tab6:
        st.markdown("### 🤝 チーム貢献度分析")
        st.caption("「試合に参加すること」は最大の貢献です。出席率と成績をクロス分析し、チームの支柱を見つけます。")

        # ==========================================
        # ★徹底デバッグ＆除外リスト読み込み★
        # ==========================================
        # secretsから直接取得
        raw_hidden = st.secrets.get("HIDDEN_PLAYERS_TOTAL", [])
        
        # もしこれがリストでなければ（誤って辞書などになっていれば）空リストにする
        if not isinstance(raw_hidden, list):
            raw_hidden = []
            
        # 比較用にスペース除去したリストを作成
        exclude_list_no_space = [str(n).replace(" ", "").replace("　", "").strip() for n in raw_hidden]

        # 🛠️ 開発中のみ表示：除外リストがどうなっているか確認
        with st.expander("🛠️ 除外設定の確認"):
            st.write("設定された除外リスト:", raw_hidden)
            st.write("比較用のクリーンリスト:", exclude_list_no_space)

        if not df_b.empty and not df_games.empty:
            total_games_count = len(df_games)

            # 選手データの元データ（クリーニング）
            df_contrib = df_b[df_b["選手名"] != "チーム記録"].copy()
            df_contrib["_clean_name"] = df_contrib["選手名"].astype(str).str.replace(r"\s+", "", regex=True)
            
            # ★除外処理：ここで確実にカット★
            df_contrib = df_contrib[~df_contrib["_clean_name"].isin(exclude_list_no_space)]
            
            if df_contrib.empty:
                st.warning("現在、除外設定により表示可能なデータがありません。")
            else:
                # 貢献度分析の計算
                hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
                df_contrib["Hit"] = df_contrib["結果"].isin(hit_cols).astype(int)
                df_contrib["BB"] = df_contrib["結果"].isin(["四球", "死球"]).astype(int)
                df_contrib["AB"] = df_contrib["結果"].isin(hit_cols + ["凡退", "三振", "失策", "併殺打", "野選"]).astype(int)
                df_contrib["TB"] = 0
                df_contrib.loc[df_contrib["結果"]=="単打", "TB"] = 1
                df_contrib.loc[df_contrib["結果"]=="二塁打", "TB"] = 2
                df_contrib.loc[df_contrib["結果"]=="三塁打", "TB"] = 3
                df_contrib.loc[df_contrib["結果"]=="本塁打", "TB"] = 4

                contrib_stats = df_contrib.groupby("選手名").agg({
                    "Date": "nunique", "Hit": "sum", "BB": "sum", "AB": "sum", "TB": "sum"
                }).rename(columns={"Date": "出場試合数"}).reset_index()

                contrib_stats["出席率"] = (contrib_stats["出場試合数"] / total_games_count) * 100
                contrib_stats["OBP"] = (contrib_stats["Hit"] + contrib_stats["BB"]) / (contrib_stats["AB"] + contrib_stats["BB"] + 1e-9)
                contrib_stats["SLG"] = contrib_stats["TB"] / (contrib_stats["AB"] + 1e-9)
                contrib_stats["OPS"] = contrib_stats["OBP"] + contrib_stats["SLG"]

                # 貢献度マトリクス表示
                chart_contrib = alt.Chart(contrib_stats).mark_circle(size=150).encode(
                    x=alt.X("出席率", title="出席率 (%)", scale=alt.Scale(domain=[0, 105])),
                    y=alt.Y("OPS", title="OPS (打撃貢献度)"),
                    color=alt.condition(alt.datum.出席率 >= 50, alt.value("#e11d48"), alt.value("#3b82f6")),
                    tooltip=["選手名", "出場試合数", alt.Tooltip("出席率", format=".1f"), alt.Tooltip("OPS", format=".3f")]
                ).interactive()
                st.altair_chart(chart_contrib, use_container_width=True)

                # 鉄人ランキング
                st.markdown("#### 🏅 鉄人ランキング (出席数)")
                iron_men = contrib_stats.sort_values(["出場試合数", "OPS"], ascending=[False, False]).head(20)
                display_df = iron_men[["選手名", "出場試合数", "出席率"]].copy()
                display_df["出席率"] = display_df["出席率"].map("{:.1f}%".format)
                st.table(display_df.reset_index(drop=True))

            # =========================================================
            # 長期未参加リスト
            # =========================================================
            st.divider()
            st.markdown("#### ⚠️ 長期未参加・公式戦登録見直し候補")

            # 背番号データ読み込み
            player_numbers_dict = st.secrets.get("PLAYER_NUMBERS", {})
            valid_numbered_players = {name for name, num in player_numbers_dict.items() 
                                    if num is not None and str(num).strip() != ""}

            # 生データ全期間
            # ※df_batting, df_pitching が定義されていない場合は、
            # ここで session_state から取得するか、関数に渡すようにしてください
            df_all = pd.concat([
                df_batting[df_batting["選手名"] != "チーム記録"],
                df_pitching[df_pitching["選手名"] != "チーム記録"]
            ]).copy()
            df_all["Date_all"] = pd.to_datetime(df_all["日付"], errors='coerce')
            df_all["_clean_name"] = df_all["選手名"].astype(str).str.replace(r"\s+", "", regex=True)

            # 有効選手抽出
            all_players = [p for p in df_all["選手名"].unique() if p in valid_numbered_players]

            # ★ここで確実に除外★
            all_players = [p for p in all_players if p.replace(" ", "").replace("　", "") not in exclude_list_no_space]

            if not all_players:
                st.info("対象となる選手（背番号登録あり）が見つかりません。")
            else:
                df_period = df_all[df_all["選手名"].isin(all_players)].copy()
                df_last_act = df_period.groupby("選手名")["Date_all"].max().reset_index()
                df_last_off = df_period[df_period["試合種別"].isin(OFFICIAL_GAME_TYPES)].groupby("選手名")["Date_all"].max().reset_index()
                
                df_res = pd.merge(df_last_act.rename(columns={"Date_all": "最終活動日"}), 
                                df_last_off.rename(columns={"Date_all": "最終公式戦日"}), on="選手名", how="left")
                
                today = pd.Timestamp.now()
                df_res["days_since_off"] = (today - df_res["最終公式戦日"]).dt.days
                df_alert = df_res[(df_res["days_since_off"] >= 365) | (df_res["最終公式戦日"].isna())].copy()
                
                if not df_alert.empty:
                    # 日付表示用文字列を作成
                    df_alert["最終公式戦日_str"] = df_alert["最終公式戦日"].dt.strftime('%Y/%m/%d').fillna("公式戦出場なし")
                    df_alert["最終活動日_str"] = df_alert["最終活動日"].dt.strftime('%Y/%m/%d').fillna("活動記録なし")
                    
                    # 不参加期間の計算ロジック
                    df_alert["days_since_off"] = (today - df_alert["最終公式戦日"]).dt.days
                    df_alert["days_since_act"] = (today - df_alert["最終活動日"]).dt.days
                    
                    def format_days_span(days):
                        if pd.isna(days) or days < 0: return "未出場"
                        years = days // 365
                        months = (days % 365) // 30
                        if years > 0: return f"{int(years)}年 {int(months)}ヶ月"
                        elif months > 0: return f"{int(months)}ヶ月"
                        else: return f"{int(days)}日"

                    df_alert["公式戦未参加期間"] = df_alert["days_since_off"].apply(format_days_span)
                    df_alert["全活動未参加期間"] = df_alert["days_since_act"].apply(format_days_span)
                    
                    # --- 参加試合数カウントのロジック（修正版） ---
                    one_year_ago = today - pd.Timedelta(days=365)
                    # 全データから直近1年を抽出
                    df_last_year = df_all[df_all["Date_all"] >= one_year_ago]
                    
                    # .size() ではなく .nunique() を使用して、日付ベースでカウントする
                    participation_counts = df_last_year.groupby("選手名")["Date_all"].nunique().reset_index(name="直近1年参加数")
                    
                    # df_alertに結合
                    df_alert = pd.merge(df_alert, participation_counts, on="選手名", how="left")
                    df_alert["直近1年参加数"] = df_alert["直近1年参加数"].fillna(0).astype(int)
                    # --------------------------------------------
                    
                    # ソート処理
                    df_alert = df_alert.sort_values(by="days_since_act", ascending=False)
                    
                    st.error(f"🚨 見直し候補選手が {len(df_alert)} 名います。")
                    
                    # 表示用列の定義
                    display_cols = ["選手名", "最終公式戦日_str", "公式戦未参加期間", "最終活動日_str", "全活動未参加期間", "直近1年参加数"]
                    display_names = {
                        "最終公式戦日_str": "最後の公式戦",
                        "公式戦未参加期間": "公式戦不参加期間",
                        "最終活動日_str": "最後の活動日",
                        "全活動未参加期間": "全活動不参加期間",
                        "直近1年参加数": "直近1年参加数"
                    }
                    
                    st.dataframe(
                        df_alert[display_cols].rename(columns=display_names), 
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.success("🎉 2年以上公式戦に参加していない対象選手はいません。")
        else:
            st.warning("分析に必要なデータが不足しています。")