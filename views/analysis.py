import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from config.settings import OFFICIAL_GAME_TYPES

def show_analysis_page(df_batting, df_pitching):
    st.title("📈 データ分析 & 傾向")

    # ---------------------------------------------------------
    # 0. データ前処理
    # ---------------------------------------------------------
    if df_batting.empty and df_pitching.empty:
        st.info("分析するデータがありません。")
        return

    # コピー作成
    df_b = df_batting.copy()
    df_p = df_pitching.copy()
    
    # 日付変換
    df_b["Date"] = pd.to_datetime(df_b["日付"])
    df_p["Date"] = pd.to_datetime(df_p["日付"])
    df_b["Year"] = df_b["Date"].dt.year.astype(str)

    # フィルタリング（年度・試合種別）
    years = sorted(df_b["Year"].unique(), reverse=True)
    c1, c2 = st.columns(2)
    selected_year = c1.selectbox("対象年度", ["全期間"] + list(years))
    
    game_types = ["すべて", "公式戦のみ", "練習試合のみ"]
    selected_type = c2.selectbox("試合種別", game_types)

    # フィルタ適用
    if selected_year != "全期間":
        df_b = df_b[df_b["Year"] == selected_year]
        df_p = df_p[df_p["Date"].dt.year.astype(str) == selected_year]
    
    if selected_type == "公式戦のみ":
        df_b = df_b[df_b["試合種別"].isin(OFFICIAL_GAME_TYPES)]
        df_p = df_p[df_p["試合種別"].isin(OFFICIAL_GAME_TYPES)]
    elif selected_type == "練習試合のみ":
        df_b = df_b[df_b["試合種別"] == "練習試合"]
        df_p = df_p[df_p["試合種別"] == "練習試合"]

    # ---------------------------------------------------------
    # ゲーム単位のデータセット作成 (勝敗、得点、先攻後攻など)
    # ---------------------------------------------------------
    games_list = []
    # 日付と対戦相手でグルーピング
    for (d, opp), g_b in df_b.groupby(["Date", "対戦相手"]):
        g_p = df_p[(df_p["Date"] == d) & (df_p["対戦相手"] == opp)]
        
        # 得点・失点計算
        # チーム記録行があればそこから、なければ積み上げ
        tm_row = g_b[g_b["選手名"] == "チーム記録"]
        if not tm_row.empty:
            my_score = pd.to_numeric(tm_row["得点"], errors='coerce').sum()
            # 先攻後攻の取得
            pos_info = str(tm_row.iloc[0]["位置"]) # "先攻 (表)" or "後攻 (裏)"
            is_top = "先攻" in pos_info or "表" in pos_info
        else:
            my_score = pd.to_numeric(g_b["得点"], errors='coerce').sum()
            is_top = None # 不明

        tm_p_row = g_p[g_p["選手名"] == "チーム記録"]
        if not tm_p_row.empty:
            opp_score = pd.to_numeric(tm_p_row["失点"], errors='coerce').sum()
        else:
            opp_score = pd.to_numeric(g_p["失点"], errors='coerce').sum()

        # 勝敗
        if my_score > opp_score: res = "Win"
        elif my_score < opp_score: res = "Lose"
        else: res = "Draw"

        # 先制点判定
        # 各イニングの得点をチェック
        first_score_team = None # "My", "Opp", "None"
        
        # イニングリストを数値化してソート
        def get_inn_num(t):
            t = str(t).replace("回", "")
            return int(t) if t.isdigit() else 99

        # 自チームの得点イニング
        my_inn_scores = g_b[g_b["イニング"].astype(str).str.contains("回")].copy()
        my_inn_scores["InnNum"] = my_inn_scores["イニング"].apply(get_inn_num)
        my_score_inns = my_inn_scores[pd.to_numeric(my_inn_scores["得点"], errors='coerce') > 0].sort_values("InnNum")
        min_my_inn = my_score_inns["InnNum"].iloc[0] if not my_score_inns.empty else 99

        # 相手チームの得点イニング
        opp_inn_scores = g_p[g_p["イニング"].astype(str).str.contains("回")].copy()
        opp_inn_scores["InnNum"] = opp_inn_scores["イニング"].apply(get_inn_num)
        opp_score_inns = opp_inn_scores[pd.to_numeric(opp_inn_scores["失点"], errors='coerce') > 0].sort_values("InnNum")
        min_opp_inn = opp_score_inns["InnNum"].iloc[0] if not opp_score_inns.empty else 99

        if min_my_inn < min_opp_inn:
            first_score_team = "自チーム"
        elif min_opp_inn < min_my_inn:
            first_score_team = "相手"
        elif min_my_inn == min_opp_inn and min_my_inn != 99:
            # 同一イニングの場合、先攻後攻で判定
            if is_top is True: first_score_team = "自チーム" # 先攻でその回に点取れば先制
            elif is_top is False: first_score_team = "相手" # 後攻なら相手が先に攻撃している
            else: first_score_team = "不明" # データなし
        else:
            first_score_team = "なし(0-0)"

        games_list.append({
            "Date": d, "Opponent": opp, "MyScore": my_score, "OppScore": opp_score,
            "Result": res, "FirstScore": first_score_team, "IsTop": is_top
        })
    
    df_games = pd.DataFrame(games_list)

    # ---------------------------------------------------------
    # タブ構成
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 チーム傾向", "🆚 対戦相手別", "⏱️ イニング・先制率", "🧠 理想オーダー", "🤝 チーム貢献度"])

    # =========================================================
    # Tab 1: チーム傾向 (わくわくVer.)
    # =========================================================
    with tab1:
        if df_games.empty:
            st.warning("データ不足のため表示できません")
        else:
            # --- 1. トップ指標 (KPI) ---
            st.markdown("### 🦅 KAGURA チームステータス")
            
            # 計算: ピタゴラス勝率 (得失点から見る「本来の実力」)
            # 公式: (得点^2) / (得点^2 + 失点^2)
            total_runs = df_games["MyScore"].sum()
            total_lost = df_games["OppScore"].sum()
            wins = len(df_games[df_games["Result"]=="Win"])
            total_g = len(df_games)
            actual_rate = wins / total_g if total_g > 0 else 0
            
            pyth_rate = 0.0
            if (total_runs + total_lost) > 0:
                pyth_rate = (total_runs**2) / ((total_runs**2) + (total_lost**2))
            
            luck_diff = actual_rate - pyth_rate
            
            # 運のコメント判定
            if luck_diff > 0.1: luck_msg = "🌟 豪運！接戦に強い！"
            elif luck_diff > 0.05: luck_msg = "🍀 勝ち運あり"
            elif luck_diff > -0.05: luck_msg = "⚖️ 実力通り"
            elif luck_diff > -0.1: luck_msg = "☁️ 少しツキがないかも"
            else: luck_msg = "☔ 不運...次は勝てる！"

            # KPI表示
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("試合数", f"{total_g} 試合", f"{wins}勝")
            k2.metric("勝率", f"{actual_rate:.3f}", f"貯金 {wins - (total_g - wins - len(df_games[df_games['Result']=='Draw']))}")
            k3.metric("平均得点", f"{df_games['MyScore'].mean():.1f}", delta=f"失点 {df_games['OppScore'].mean():.1f}", delta_color="normal")
            k4.metric("チームの運勢", luck_msg, f"期待勝率 {pyth_rate:.3f}", help="得失点差から算出した『本来あるべき勝率』との差です。プラスなら勝負強く、マイナスなら不運な負けが多い傾向です。")

            st.divider()

            # --- 2. 試合スタイル分析 (散布図) ---
            st.markdown("### 🔥 勝ち方のスタイル診断")
            st.caption("どんな試合展開が多い？（右上：乱打戦、左下：投手戦）")
            
            # 象限分けのためのデータ作成
            c_style = alt.Chart(df_games).mark_circle(size=100).encode(
                x=alt.X("MyScore", title="自チーム得点", scale=alt.Scale(domain=[0, max(15, df_games['MyScore'].max())])),
                y=alt.Y("OppScore", title="相手チーム得点", scale=alt.Scale(domain=[0, max(15, df_games['OppScore'].max())])),
                color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=["#ef4444", "#3b82f6", "#9ca3af"]), legend=alt.Legend(title="勝敗")),
                tooltip=["Date", "Opponent", "MyScore", "OppScore", "Result"]
            ).interactive()

            # 背景に十字線を入れて象限をわかりやすく
            avg_my = df_games["MyScore"].mean()
            avg_opp = df_games["OppScore"].mean()
            
            rule_x = alt.Chart(pd.DataFrame({'x': [avg_my]})).mark_rule(color="gray", strokeDash=[3,3]).encode(x='x')
            rule_y = alt.Chart(pd.DataFrame({'y': [avg_opp]})).mark_rule(color="gray", strokeDash=[3,3]).encode(y='y')
            
            # テキスト注釈（象限の意味）
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

            # --- 3. 勝利の方程式 (マジックナンバー) ---
            st.divider()
            col_v1, col_v2 = st.columns([1.5, 1])
            
            with col_v1:
                st.markdown("### ✨ KAGURAの『勝利の法則』")
                st.caption("何点取れば勝てる？得点ごとの勝率グラフ")
                
                # 得点ごとの勝率データ作成
                score_bins = df_games.copy()
                # 10点以上は「10+」にまとめるなどの処理も可能だが、まずはそのまま
                score_win_rate = score_bins.groupby("MyScore").agg(
                    GameCount=("Result", "count"),
                    WinCount=("Result", lambda x: (x=="Win").sum())
                ).reset_index()
                score_win_rate["WinRate"] = score_win_rate["WinCount"] / score_win_rate["GameCount"]

                # バーチャートと折れ線（勝率）の複合グラフ
                base_chart = alt.Chart(score_win_rate).encode(x=alt.X("MyScore:O", title="得点"))
                
                bar_c = base_chart.mark_bar(opacity=0.3, color="#64748b").encode(
                    y=alt.Y("GameCount", title="試合回数")
                )
                
                line_c = base_chart.mark_line(point=True, color="#e11d48").encode(
                    y=alt.Y("WinRate", title="勝率", axis=alt.Axis(format="%")),
                    tooltip=["MyScore", "GameCount", alt.Tooltip("WinRate", format=".0%")]
                )
                
                st.altair_chart((bar_c + line_c).resolve_scale(y='independent'), use_container_width=True)

            with col_v2:
                # 魔法の数字を見つける
                magic_num = 0
                for index, row in score_win_rate.iterrows():
                    if row["WinRate"] >= 0.8: # 勝率8割を超えるライン
                        magic_num = int(row["MyScore"])
                        break
                
                st.markdown(f"""
                <div style="background-color:#f1f5f9; padding:15px; border-radius:10px; text-align:center; margin-top:20px;">
                    <div style="font-size:16px; color:#64748b;">勝利のマジックナンバー</div>
                    <div style="font-size:48px; font-weight:bold; color:#e11d48;">{magic_num}点</div>
                    <div style="font-size:14px;">{magic_num}点以上取った時の勝率は<br>驚異の <strong>{int(score_win_rate[score_win_rate['MyScore']>=magic_num]['WinRate'].mean()*100)}%</strong> です！</div>
                </div>
                """, unsafe_allow_html=True)

                # 最近の調子
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
            st.markdown("##### 対戦相手別成績")
            
            opp_stats = df_games.groupby("Opponent").agg(
                試合数=("Result", "count"),
                勝利=("Result", lambda x: (x=="Win").sum()),
                敗戦=("Result", lambda x: (x=="Lose").sum()),
                引分=("Result", lambda x: (x=="Draw").sum()),
                平均得点=("MyScore", "mean"),
                平均失点=("OppScore", "mean")
            ).reset_index()
            
            opp_stats["勝率"] = opp_stats.apply(lambda x: x["勝利"]/(x["勝利"]+x["敗戦"]) if (x["勝利"]+x["敗戦"])>0 else 0, axis=1)
            opp_stats = opp_stats.sort_values("試合数", ascending=False)

            # データ表示
            st.dataframe(
                opp_stats.style.format({"平均得点": "{:.1f}", "平均失点": "{:.1f}", "勝率": "{:.3f}"})
                         .background_gradient(subset=["勝率"], cmap="Reds"),
                use_container_width=True,
                hide_index=True
            )

            # グラフ: 得失点差
            opp_stats["得失差"] = opp_stats["平均得点"] - opp_stats["平均失点"]
            bar_diff = alt.Chart(opp_stats).mark_bar().encode(
                x=alt.X("Opponent", sort="-y", title="対戦相手"),
                y=alt.Y("得失差", title="平均得失点差"),
                color=alt.condition(
                    alt.datum.得失差 > 0,
                    alt.value("#e11d48"),  # 正なら赤
                    alt.value("#1e40af")   # 負なら青
                ),
                tooltip=["Opponent", "試合数", "平均得点", "平均失点", "得失差"]
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
                # 先制した試合
                games_first = df_games[df_games["FirstScore"] == "自チーム"]
                if not games_first.empty:
                    w = len(games_first[games_first["Result"]=="Win"])
                    l = len(games_first[games_first["Result"]=="Lose"])
                    d = len(games_first[games_first["Result"]=="Draw"])
                    rate = w / (w+l) if (w+l) > 0 else 0
                    st.metric("先制した試合数", f"{len(games_first)}試合", f"勝率: {rate:.3f}")
                    
                    # グラフ化
                    df_f_res = pd.DataFrame({"Result": ["Win", "Lose", "Draw"], "Count": [w, l, d]})
                    pie_f = alt.Chart(df_f_res).mark_arc(innerRadius=40).encode(
                        theta="Count",
                        color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=["#e11d48", "#1e40af", "#94a3b8"])),
                        tooltip=["Result", "Count"]
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
                        theta="Count",
                        color=alt.Color("Result", scale=alt.Scale(domain=["Win", "Lose", "Draw"], range=["#e11d48", "#1e40af", "#94a3b8"])),
                        tooltip=["Result", "Count"]
                    )
                    st.altair_chart(pie_f_opp, use_container_width=True)
                else:
                    st.info("先制された試合がありません")

        with c3_2:
            st.markdown("##### 🔢 イニング別得失点")
            # イニング集計
            def aggregate_innings(df_raw, score_col):
                df_i = df_raw.copy()
                # 1〜9回のみ抽出
                df_i = df_i[df_i["イニング"].astype(str).str.match(r"^[1-9]回$")]
                df_i["得点"] = pd.to_numeric(df_i[score_col], errors='coerce').fillna(0)
                return df_i.groupby("イニング")["得点"].sum()

            inn_scores = aggregate_innings(df_b, "得点")
            inn_lost = aggregate_innings(df_p, "失点")
            
            # DataFrame結合
            df_inn = pd.DataFrame({"得点": inn_scores, "失点": inn_lost}).fillna(0).reset_index()
            # "1回" -> 1 にしてソート
            df_inn["InnNum"] = df_inn["イニング"].apply(lambda x: int(x.replace("回", "")))
            df_inn = df_inn.sort_values("InnNum")

            # グラフ用変形
            df_inn_melt = df_inn.melt(id_vars=["イニング", "InnNum"], value_vars=["得点", "失点"], var_name="Type", value_name="Runs")
            
            bar_inn = alt.Chart(df_inn_melt).mark_bar().encode(
                x=alt.X("イニング", sort=alt.EncodingSortField(field="InnNum", order="ascending")),
                y="Runs",
                color=alt.Color("Type", scale=alt.Scale(domain=["得点", "失点"], range=["#e11d48", "#1e40af"])),
                column="Type",
                tooltip=["イニング", "Runs"]
            )
            st.altair_chart(bar_inn, use_container_width=True)
            
            # ヒートマップ風テーブル
            st.dataframe(df_inn[["イニング", "得点", "失点"]].set_index("イニング").T, use_container_width=True)

    # =========================================================
    # Tab 4: 理想オーダー (セイバーメトリクス簡易版)
    # =========================================================
    with tab4:
        st.markdown("### 🧠 統計データに基づく推奨オーダー")
        st.caption("過去の個人成績から、セイバーメトリクスの定石に基づいたオーダー案を提示します。")

        # 個人成績集計
        if not df_b.empty:
            # 必要なカラム計算
            df_calc = df_b[df_b["選手名"] != "チーム記録"].copy()
            
            # ヒット系
            hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
            df_calc["Hit"] = df_calc["結果"].isin(hit_cols).astype(int)
            df_calc["BB"] = df_calc["結果"].isin(["四球", "死球"]).astype(int) # 出塁計算用
            df_calc["AB"] = df_calc["結果"].isin(hit_cols + ["凡退", "三振", "失策", "併殺打", "野選"]).astype(int) # 打数
            df_calc["PA"] = 1 # 打席数
            
            # 塁打
            df_calc["TB"] = 0
            df_calc.loc[df_calc["結果"]=="単打", "TB"] = 1
            df_calc.loc[df_calc["結果"]=="二塁打", "TB"] = 2
            df_calc.loc[df_calc["結果"]=="三塁打", "TB"] = 3
            df_calc.loc[df_calc["結果"]=="本塁打", "TB"] = 4
            
            df_calc["SB"] = pd.to_numeric(df_calc["盗塁"], errors='coerce').fillna(0)
            
            # 集計
            stats = df_calc.groupby("選手名").agg({
                "PA": "sum", "AB": "sum", "Hit": "sum", "BB": "sum", "TB": "sum", "SB": "sum"
            }).reset_index()
            
            # 最低打席数フィルタ
            min_pa = st.slider("対象とする最低打席数", 1, 50, 25)
            stats = stats[stats["PA"] >= min_pa]

            if not stats.empty:
                # 指標計算
                # 出塁率(OBP) = (安打+四死球) / 打席 (※犠飛等は簡易化のため省略)
                stats["OBP"] = (stats["Hit"] + stats["BB"]) / stats["PA"]
                # 長打率(SLG) = 塁打 / 打数
                stats["SLG"] = stats.apply(lambda x: x["TB"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                # OPS
                stats["OPS"] = stats["OBP"] + stats["SLG"]
                # 打率
                stats["AVG"] = stats.apply(lambda x: x["Hit"] / x["AB"] if x["AB"] > 0 else 0, axis=1)
                # 三振率などを考慮する場合、元データで三振を集計する必要あり(今回は簡易版)

                # --- オーダーロジック ---
                candidates = stats.copy()
                lineup = []
                used_players = []

                def pick_player(df, sort_key, role_desc):
                    # まだ選ばれていない選手から
                    available = df[~df["選手名"].isin(used_players)].sort_values(sort_key, ascending=False)
                    if not available.empty:
                        p = available.iloc[0]
                        lineup.append({
                            "打順": len(lineup)+1, 
                            "役割": role_desc, 
                            "選手名": p["選手名"], 
                            "主要指標": f"{sort_key}={p[sort_key]:.3f}",
                            "OPS": f"{p['OPS']:.3f}",
                            "出塁率": f"{p['OBP']:.3f}",
                            "盗塁": int(p['SB'])
                        })
                        used_players.append(p["選手名"])

                # 1番打者評価値の計算：出塁率(OBP) + (盗塁(SB) * 0.02)
                candidates["LeadOffScore"] = candidates["OBP"] + (candidates["SB"] * 0.02)

                # 1番: 出塁率が高く、足が使える
                pick_player(candidates, "LeadOffScore", "チャンスメーカー (出塁+走塁)")

                # 2番: 出塁率が高く、つなげる（現代野球型）
                pick_player(candidates, "OBP", "繋ぎの強打者 (高出塁率)")

                # 3番: チーム最高の打者 (OPS重視)
                pick_player(candidates, "OPS", "最強打者 (高OPS)")

                # 4番: チーム最高の長打力
                pick_player(candidates, "SLG", "主砲 (長打力重視)")

                # 5番: クリーンナップの残り
                pick_player(candidates, "OPS", "ポイントゲッター")

                # 6番〜9番: 残りをOPS順に
                pick_player(candidates, "OPS", "裏クリーンナップ （実は長打力がある）")
                pick_player(candidates, "OPS", "恐怖の伏兵")
                pick_player(candidates, "OPS", "意外性の男")
                pick_player(candidates, "OPS", "第2のリードオフ")

                # 結果表示
                st.table(pd.DataFrame(lineup).set_index("打順"))
                
                st.caption("※ ロジック: 1番(出塁+走塁), 2番(出塁), 3番(OPS), 4番(長打), 5番以降(OPS順) で自動選出しています。")
            else:
                st.warning(f"打席数が {min_pa} 以上の選手がいません。")

        else:
            st.info("データがありません")

    # =========================================================
    # Tab 5: チーム貢献度 (出席率 × 実力)
    # =========================================================
    with tab5:
        st.markdown("### 🤝 チーム貢献度分析")
        st.caption("「試合に参加すること」は最大の貢献です。出席率と成績をクロス分析し、チームの支柱を見つけます。")

        if not df_b.empty and not df_games.empty:
            # 1. データの準備
            total_games_count = len(df_games) # フィルタリングされた期間の全試合数

            # 個人成績の再集計（OPS計算用）
            df_contrib = df_b[df_b["選手名"] != "チーム記録"].copy()
            
            # OPS計算に必要な指標
            hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
            df_contrib["Hit"] = df_contrib["結果"].isin(hit_cols).astype(int)
            df_contrib["BB"] = df_contrib["結果"].isin(["四球", "死球"]).astype(int)
            df_contrib["AB"] = df_contrib["結果"].isin(hit_cols + ["凡退", "三振", "失策", "併殺打", "野選"]).astype(int)
            
            # 塁打
            df_contrib["TB"] = 0
            df_contrib.loc[df_contrib["結果"]=="単打", "TB"] = 1
            df_contrib.loc[df_contrib["結果"]=="二塁打", "TB"] = 2
            df_contrib.loc[df_contrib["結果"]=="三塁打", "TB"] = 3
            df_contrib.loc[df_contrib["結果"]=="本塁打", "TB"] = 4

            # 選手ごとの集計
            contrib_stats = df_contrib.groupby("選手名").agg({
                "Date": "nunique", # ユニークな日付数＝出場試合数
                "Hit": "sum", "BB": "sum", "AB": "sum", "TB": "sum"
            }).rename(columns={"Date": "出場試合数"}).reset_index()

            # 指標計算
            contrib_stats["出席率"] = (contrib_stats["出場試合数"] / total_games_count) * 100
            
            # OPS計算 (簡易版: OBP + SLG)
            contrib_stats["OBP"] = (contrib_stats["Hit"] + contrib_stats["BB"]) / (contrib_stats["AB"] + contrib_stats["BB"] + 1e-9) # ゼロ除算回避
            contrib_stats["SLG"] = contrib_stats["TB"] / (contrib_stats["AB"] + 1e-9)
            contrib_stats["OPS"] = contrib_stats["OBP"] + contrib_stats["SLG"]

            # --- 2. 貢献度マトリクス (散布図) ---
            st.markdown("#### 💎 貢献度マトリクス")
            st.markdown("""
            - **右下 (Grassroots Hero)**: 成績は発展途上だが、**高い出席率でチームを支える重要人物**。
            - **右上 (Core Player)**: 実力もあり参加率も高い、チームの中心。
            - **左上 (Helper)**: 参加は少ないが、来れば活躍する助っ人タイプ。
            """)

            # 散布図の作成
            chart_contrib = alt.Chart(contrib_stats).mark_circle(size=150).encode(
                x=alt.X("出席率", title="出席率 (%)", scale=alt.Scale(domain=[0, 105])),
                y=alt.Y("OPS", title="OPS (打撃貢献度)"),
                color=alt.condition(
                    alt.datum.出席率 >= 50,
                    alt.value("#e11d48"),  # 出席率50%以上は赤色で強調
                    alt.value("#3b82f6")   # その他は青
                ),
                tooltip=["選手名", "出場試合数", alt.Tooltip("出席率", format=".1f"), alt.Tooltip("OPS", format=".3f")]
            ).interactive()

            # 平均線の追加
            mean_att = contrib_stats["出席率"].mean()
            mean_ops = contrib_stats["OPS"].mean()
            
            rule_x = alt.Chart(pd.DataFrame({'x': [mean_att]})).mark_rule(strokeDash=[3,3], color="gray").encode(x='x')
            rule_y = alt.Chart(pd.DataFrame({'y': [mean_ops]})).mark_rule(strokeDash=[3,3], color="gray").encode(y='y')

            st.altair_chart(chart_contrib + rule_x + rule_y, use_container_width=True)

            # --- 3. 鉄人ランキング ---
            st.divider()
            c_rank1, c_rank2 = st.columns(2)

            with c_rank1:
                st.markdown("#### 🏅 鉄人ランキング (出席数)")
                # 出場試合数順にソート
                iron_men = contrib_stats.sort_values(["出場試合数", "OPS"], ascending=[False, False]).head(10)
                
                # 表示用データフレーム作成
                display_df = iron_men[["選手名", "出場試合数", "出席率"]].copy()
                display_df["出席率"] = display_df["出席率"].map("{:.1f}%".format)
                
                st.table(display_df.reset_index(drop=True))

            with c_rank2:
                # 分析コメント
                top_player = iron_men.iloc[0]["選手名"]
                high_attend_count = len(contrib_stats[contrib_stats["出席率"] >= 50])
                
                st.info(f"""
                **📊 分析インサイト**
                
                今回の期間（全 {total_games_count} 試合）において、最もチームに貢献している鉄人は **{top_player}** 選手です。
                
                出席率が **50%** を超えている選手は **{high_attend_count}** 名います。
                この選手たちがチームの活動維持の基盤となっています。
                """)
        else:
            st.warning("分析に必要なデータが不足しています。")