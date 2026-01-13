import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# ==========================================
# 1. ページ・CSS設定
# ==========================================
st.set_page_config(page_title="KAGURA Official Stats", layout="wide", page_icon="⚾")

st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    h1, h2, h3 { color: #1e3a8a; }
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #d90429 !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 定数・辞書定義
# ==========================================
PLAYER_NUMBERS = {
    "佐藤蓮太": "1", "久保田剛志": "2", "開田凌空": "3", "水谷真智": "4",
    "河野潤樹": "5", "渡邉誠也": "7", "岡﨑英一": "8", "中尾建太": "10",
    "内藤洋輔": "11", "大高翼": "13", "小野拓朗": "15", "古屋翔": "17",
    "伊東太建": "18", "渡邉竣太": "19", "山田大貴": "21", "志村裕三": "23",
    "石田貴大": "24", "相原一博": "25", "田中伸延": "26", "坂本昂士": "27",
    "渡辺羽": "28", "石原圭佑": "29", "荒木豊": "31", "永井雄太": "33",
    "小野慎也": "38", "清水智広": "43", "名執雅叶": "51", "山縣諒介": "60",
    "照屋航": "63", "望月駿": "66", "鈴木翔大": "73"
}
all_players = list(PLAYER_NUMBERS.keys())
my_team_fixed = "KAGURA"

# ==========================================
# 3. データベース接続 & 読み込み関数
# ==========================================
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60) # 60秒キャッシュ
def load_data():
    try:
        # 読み込み
        df_b = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="打撃成績")
        df_p = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績")
        
        # カラム補正（エラー回避用）
        if df_b.empty:
             df_b = pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])
        if df_p.empty:
             df_p = pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "処理野手", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "勝敗"])

        # 日付変換
        df_b["日付"] = pd.to_datetime(df_b["日付"], errors='coerce').dt.date
        df_p["日付"] = pd.to_datetime(df_p["日付"], errors='coerce').dt.date
        
        return df_b, df_p
    except:
        return pd.DataFrame(), pd.DataFrame()

df_batting, df_pitching = load_data()

# ==========================================
# 4. ヘルパー関数
# ==========================================
def inning_sort_key(inn_str):
    try:
        return int(str(inn_str).replace("回", ""))
    except:
        return 99 

def render_scoreboard(b_df, p_df, date_txt, m_type, g_name, opp_name, is_top_first=True):
    st.markdown(f"### 📅 {date_txt} ({m_type}) &nbsp;&nbsp; 🏟️ {g_name}")
    st.subheader(f"⚾ {my_team_fixed} vs {opp_name}")
    
    k_inning, opp_inning = [], []
    total_k, total_opp = 0, 0
    
    for i in range(1, 10):
        inn = f"{i}回"
        
        inn_bat_data = b_df[b_df["イニング"] == inn]
        k_runs = int(pd.to_numeric(inn_bat_data["得点"], errors='coerce').sum())
        
        opp_data_inn = p_df[p_df["イニング"] == inn]
        opp_runs = int(pd.to_numeric(opp_data_inn["失点"], errors='coerce').sum())
        
        k_exists = not inn_bat_data.empty
        opp_exists = not opp_data_inn.empty
        
        k_inning.append(str(k_runs) if k_exists else "")
        opp_inning.append(str(opp_runs) if opp_exists else "")
        
        total_k += k_runs
        total_opp += opp_runs

    hit_list = ["単打", "二塁打", "三塁打", "本塁打"]
    k_h = b_df[b_df["結果"].isin(hit_list)].shape[0]
    k_e = p_df[p_df["結果"] == "失策"].shape[0]
    opp_h = p_df[p_df["結果"].isin(hit_list)].shape[0]
    opp_e = b_df[b_df["結果"] == "失策"].shape[0]

    if is_top_first:
        names = [my_team_fixed, opp_name]
        scores = [k_inning, opp_inning]
        R = [int(total_k), int(total_opp)]
        H = [int(k_h), int(opp_h)]
        E = [int(k_e), int(opp_e)]
    else:
        names = [opp_name, my_team_fixed]
        scores = [opp_inning, k_inning]
        R = [int(total_opp), int(total_k)]
        H = [int(opp_h), int(k_h)]
        E = [int(opp_e), int(k_e)]

    score_dict = {"チーム": names}
    for i in range(9):
        score_dict[str(i+1)] = [scores[0][i], scores[1][i]]
    
    score_dict.update({"R": R, "H": H, "E": E})
    st.table(pd.DataFrame(score_dict))

# ==========================================
# 5. サイドバー (閲覧専用)
# ==========================================
st.sidebar.title("⚾ KAGURA Stats")
st.sidebar.info("閲覧専用アプリです")

menu = st.sidebar.radio("MENU", ["🏠 最新試合結果", "🏆 チーム戦績", "📊 個人成績", "👑 歴代記録"])

# ==========================================
# 6. メインコンテンツ
# ==========================================

# --- 🏠 最新試合結果 ---
if menu == "🏠 最新試合結果":
    st.title("📢 最新試合結果")
    
    if not df_batting.empty and not df_pitching.empty:
        # 日付処理
        df_batting["Date"] = pd.to_datetime(df_batting["日付"], errors='coerce')
        latest_date = df_batting["Date"].max()
        
        if pd.notna(latest_date):
            latest_str = latest_date.strftime('%Y-%m-%d')
            
            # 最新日のデータを抽出
            day_b = df_batting[df_batting["Date"] == latest_date]
            day_p = df_pitching[pd.to_datetime(df_pitching["日付"], errors='coerce') == latest_date]
            
            # 情報取得
            opp = day_b["対戦相手"].iloc[0] if "対戦相手" in day_b.columns else "-"
            ground = day_b["グラウンド"].iloc[0] if "グラウンド" in day_b.columns else "-"
            m_type = day_b["試合種別"].iloc[0] if "試合種別" in day_b.columns else "-"
            
            # スコアボード表示
            render_scoreboard(day_b, day_p, latest_str, m_type, ground, opp, is_top_first=True)
            
            st.success(f"最新更新: {latest_str} vs {opp}")
        else:
            st.info("表示できる試合データがありません。")
            
    if st.button("データを更新する"):
        st.cache_data.clear()
        st.rerun()

# --- 🏆 チーム戦績 (修正・統合済み) ---
elif menu == "🏆 チーム戦績":
    st.title("🏆 KAGURA チーム戦績")
    
    if not df_batting.empty and not df_pitching.empty:
        # 年度カラム作成
        df_batting["Year"] = pd.to_datetime(df_batting["日付"]).dt.year.astype(str)
        df_pitching["Year"] = pd.to_datetime(df_pitching["日付"]).dt.year.astype(str)
        
        all_years = sorted(list(set(df_batting["Year"].unique()) | set(df_pitching["Year"].unique())), reverse=True)
        
        # --- フィルタリング ---
        c_year, c_type = st.columns(2)
        target_year = c_year.selectbox("年度 (Season)", ["通算"] + all_years)
        
        available_types = ["全種別"] + [x for x in list(df_batting["試合種別"].unique()) if str(x) != "nan" and x != ""]
        target_type = c_type.selectbox("試合種別", available_types)

        use_ground_filter = st.checkbox("🏟️ グラウンドで絞り込む")
        target_ground = None
        if use_ground_filter:
            available_grounds = [x for x in list(df_batting["グラウンド"].unique()) if str(x) != "nan" and x != ""]
            target_ground = st.selectbox("グラウンド選択", available_grounds)
        
        df_b_target = df_batting.copy()
        df_p_target = df_pitching.copy()

        if target_year != "通算":
            df_b_target = df_b_target[df_b_target["Year"] == target_year]
            df_p_target = df_p_target[df_p_target["Year"] == target_year]

        if target_type != "全種別":
            df_b_target = df_b_target[df_b_target["試合種別"] == target_type]
            df_p_target = df_p_target[df_p_target["試合種別"] == target_type]
        
        if use_ground_filter and target_ground:
            df_b_target = df_b_target[df_b_target["グラウンド"] == target_ground]
            df_p_target = df_p_target[df_p_target["グラウンド"] == target_ground]

        # --- 試合一覧の生成と勝敗集計 ---
        if not df_b_target.empty:
            dates = sorted(list(set(df_b_target["日付"].unique()) | set(df_p_target["日付"].unique())), reverse=True)
            game_results = []
            wins = 0; loses = 0; draws = 0

            for d in dates:
                day_b = df_b_target[df_b_target["日付"] == d]
                day_p = df_p_target[df_p_target["日付"] == d]
                
                if day_b.empty: continue

                my_score = pd.to_numeric(day_b["得点"], errors='coerce').sum()
                opp_score = pd.to_numeric(day_p["失点"], errors='coerce').sum()
                
                opp_name = day_b["対戦相手"].iloc[0] if "対戦相手" in day_b.columns and not day_b.empty else "-"
                ground = day_b["グラウンド"].iloc[0] if "グラウンド" in day_b.columns and not day_b.empty else "-"
                m_type = day_b["試合種別"].iloc[0] if "試合種別" in day_b.columns and not day_b.empty else "-"

                if my_score > opp_score: res = "WIN"; res_icon = "🔵"; wins += 1
                elif my_score < opp_score: res = "LOSE"; res_icon = "🔴"; loses += 1
                else: res = "DRAW"; res_icon = "⚪"; draws += 1
                
                game_results.append({
                    "日付": d, "種別": m_type, "対戦相手": opp_name, "会場": ground,
                    "スコア": f"{int(my_score)} - {int(opp_score)}", "勝敗": f"{res_icon} {res}",
                    "K得点": int(my_score), "相手得点": int(opp_score)
                })

            # --- チーム成績メトリクスの計算 ---
            games_count = wins + loses + draws
            win_rate = wins / (wins + loses) if (wins + loses) > 0 else 0.000

            # 1. 打撃系指標
            team_runs = pd.to_numeric(df_b_target["得点"], errors='coerce').sum()
            team_sb = pd.to_numeric(df_b_target["盗塁"], errors='coerce').sum()
            team_hr = df_b_target[df_b_target["結果"] == "本塁打"].shape[0]
            
            # 打率計算
            hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
            ab_cols = hit_cols + ["凡退", "失策", "走塁死", "盗塁死", "牽制死", "三振"]
            
            team_hits = df_b_target[df_b_target["結果"].isin(hit_cols)].shape[0]
            team_ab = df_b_target[df_b_target["結果"].isin(ab_cols)].shape[0]
            team_avg = team_hits / team_ab if team_ab > 0 else 0.0
            
            runs_per_game = team_runs / games_count if games_count > 0 else 0.0

            # 2. 投手系指標
            team_runs_allowed = pd.to_numeric(df_p_target["失点"], errors='coerce').sum()
            team_er = pd.to_numeric(df_p_target["自責点"], errors='coerce').sum()
            team_outs = pd.to_numeric(df_p_target["アウト数"], errors='coerce').sum()
            
            team_innings = team_outs / 3
            team_era = (team_er * 9) / team_innings if team_innings > 0 else 0.0
            runs_allowed_per_game = team_runs_allowed / games_count if games_count > 0 else 0.0

            # --- 表示 ---
            st.markdown("##### 📌 勝敗")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("試合数", f"{games_count}")
            m2.metric("勝利", f"{wins}")
            m3.metric("敗北", f"{loses}")
            m4.metric("引分", f"{draws}")
            m5.metric("勝率", f"{win_rate:.3f}")

            st.markdown("##### ⚔️ 攻撃")
            b1, b2, b3, b4, b5 = st.columns(5)
            b1.metric("チーム打率", f"{team_avg:.3f}")
            b2.metric("総得点", f"{int(team_runs)}")
            b3.metric("得点率", f"{runs_per_game:.2f}", help="1試合あたりの平均得点")
            b4.metric("本塁打", f"{team_hr}")
            b5.metric("盗塁", f"{int(team_sb)}")

            st.markdown("##### 🛡️ 守備")
            p1, p2, p3 = st.columns(3)
            p1.metric("チーム防御率", f"{team_era:.2f}")
            p2.metric("総失点", f"{int(team_runs_allowed)}")
            p3.metric("失点率", f"{runs_allowed_per_game:.2f}", help="1試合あたりの平均失点")
            
            st.divider()
            
            # --- 試合一覧テーブル ---
            st.subheader("📜 試合履歴 (行をクリックで詳細表示)")
            df_res = pd.DataFrame(game_results)
            
            event = st.dataframe(
                df_res.drop(columns=["K得点", "相手得点"]),
                use_container_width=True, 
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )

            # --- 詳細表示ロジック ---
            if len(event.selection.rows) > 0:
                selected_index = event.selection.rows[0]
                selected_data = df_res.iloc[selected_index]
                
                target_date = selected_data["日付"]
                target_opp = selected_data["対戦相手"]
                
                detail_b = df_batting[(df_batting["日付"] == target_date) & (df_batting["対戦相手"] == target_opp)]
                detail_p = df_pitching[(df_pitching["日付"] == target_date) & (df_pitching["対戦相手"] == target_opp)]
                
                d_date_str = target_date.strftime('%Y-%m-%d')
                d_m_type = selected_data["種別"]
                d_ground = selected_data["会場"]
                
                st.divider()
                st.markdown(f"## 🔎 試合詳細: vs {target_opp}")
                
                render_scoreboard(detail_b, detail_p, d_date_str, d_m_type, d_ground, target_opp, is_top_first=False)
                
                st.write("")
                
                tab_d_bat, tab_d_pit = st.tabs(["📝 打撃成績 (スコアブック)", "🔥 投手成績 (登板内容)"])
                
                # 詳細表示ロジック
                with tab_d_bat:
                    if not detail_b.empty:
                        detail_b["_inn_sort"] = detail_b["イニング"].apply(inning_sort_key)
                        detail_b_sorted = detail_b.sort_values(by=["_inn_sort"])

                        players_ordered = detail_b_sorted["選手名"].unique()
                        batting_rows = []
                        max_at_bats = 0 
                        display_targets = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策"]

                        for i, p_name in enumerate(players_ordered):
                            p_rows = detail_b_sorted[detail_b_sorted["選手名"] == p_name]
                            pos = p_rows.iloc[-1]["位置"] if "位置" in p_rows.columns else "-"
                            results = p_rows[p_rows["結果"].isin(display_targets)]["結果"].tolist()
                            if len(results) > max_at_bats: max_at_bats = len(results)
                            rbi = pd.to_numeric(p_rows["打点"], errors='coerce').sum()
                            run = pd.to_numeric(p_rows["得点"], errors='coerce').sum()
                            sb = pd.to_numeric(p_rows["盗塁"], errors='coerce').sum()
                            hits = p_rows[p_rows["結果"].isin(["単打", "二塁打", "三塁打", "本塁打"])].shape[0]
                            batting_rows.append({
                                "打順": i + 1, "守備": pos, "選手名": p_name,
                                "打点": rbi, "得点": run, "安打": hits, "盗塁": sb, "results": results
                            })
                        
                        df_bat_formatted = pd.DataFrame(batting_rows)
                        final_max_cols = max(5, max_at_bats)
                        for j in range(final_max_cols):
                            col_name = f"第{j+1}打席"
                            df_bat_formatted[col_name] = df_bat_formatted["results"].apply(lambda x: x[j] if j < len(x) else "")
                        
                        cols_order = ["打順", "守備", "選手名"] + [f"第{j+1}打席" for j in range(final_max_cols)] + ["安打", "打点", "得点", "盗塁"]
                        df_final_b = df_bat_formatted.drop(columns=["results"])[cols_order]
                        st.dataframe(df_final_b, use_container_width=True, hide_index=True)
                    else:
                        st.info("打撃データがありません")

                with tab_d_pit:
                    if not detail_p.empty:
                        pitchers = detail_p["投手名"].unique()
                        p_rows = []
                        for p_name in pitchers:
                            p_data = detail_p[detail_p["投手名"] == p_name]
                            # 簡易表示（閲覧用なのでシンプルに）
                            outs = p_data["アウト数"].sum()
                            st.write(f"**{p_name}**: {int(outs//3)}回 {int(outs%3)}/3  (球数: {int(p_data['球数'].sum())}, 失点: {int(p_data['失点'].sum())})")
                    else:
                        st.info("投手データがありません")

# --- 📊 個人成績 ---
elif menu == "📊 個人成績":
    st.title("📊 個人成績")
    st.write("※ ここに app.py の「📊 個人成績」ブロックのコードを貼り付けてください")
# ==========================================
    # 1. データのフィルタリング設定
    # ==========================================
    if not df_batting.empty:
        df_batting["Year"] = pd.to_datetime(df_batting["日付"]).dt.year.astype(str)
        df_pitching["Year"] = pd.to_datetime(df_pitching["日付"]).dt.year.astype(str)
        all_years_p = sorted(list(set(df_batting["Year"].unique()) | set(df_pitching["Year"].unique())), reverse=True)
    else:
        all_years_p = []

    c_p_year, c_p_type = st.columns(2)
    p_target_year = c_p_year.selectbox("年度 (Season)", ["通算"] + all_years_p, key="p_year_sel")
    
    p_avail_types = ["全種別"] + [x for x in list(df_batting["試合種別"].unique()) if str(x) != "nan" and x != ""]
    p_target_type = c_p_type.selectbox("試合種別", p_avail_types, key="p_type_sel")

    p_use_ground = st.checkbox("🏟️ グラウンドで絞り込む", key="p_ground_check")
    p_target_ground = None
    if p_use_ground:
        p_avail_grounds = [x for x in list(df_batting["グラウンド"].unique()) if str(x) != "nan" and x != ""]
        p_target_ground = st.selectbox("グラウンド選択", p_avail_grounds, key="p_ground_sel")

    # フィルタ適用
    df_b_target = df_batting.copy()
    df_p_target = df_pitching.copy()

    if p_target_year != "通算":
        df_b_target = df_b_target[df_b_target["Year"] == p_target_year]
        df_p_target = df_p_target[df_p_target["Year"] == p_target_year]

    if p_target_type != "全種別":
        df_b_target = df_b_target[df_b_target["試合種別"] == p_target_type]
        df_p_target = df_p_target[df_p_target["試合種別"] == p_target_type]
    
    if p_use_ground and p_target_ground:
        df_b_target = df_b_target[df_b_target["グラウンド"] == p_target_ground]
        df_p_target = df_p_target[df_p_target["グラウンド"] == p_target_ground]

    # ==========================================
    # 2. タブの作成
    # ==========================================
    t_bat, t_pit, t_fld = st.tabs(["打撃部門", "投手部門", "守備部門"])
    
    # ----------------------------------------------------
    # (A) 打撃部門
    # ----------------------------------------------------
    with t_bat:
        if not df_b_target.empty:
            batting_stats = []
            ab_res = ["単打", "二塁打", "三塁打", "本塁打", "三振", "凡退", "失策", "走塁死"]
            pa_res = ab_res + ["四球", "死球", "犠打"]
            
            for player in all_players:
                p_data = df_b_target[df_b_target["選手名"] == player]
                if p_data.empty: continue
                
                # 背番号取得
                player_num = PLAYER_NUMBERS.get(player, "-")

                p_bat = p_data[p_data["種別"] == "打撃"]
                
                singles = p_bat[p_bat["結果"] == "単打"].shape[0]
                doubles = p_bat[p_bat["結果"] == "二塁打"].shape[0]
                triples = p_bat[p_bat["結果"] == "三塁打"].shape[0]
                hrs = p_bat[p_bat["結果"] == "本塁打"].shape[0]
                bbs = p_bat[p_bat["結果"] == "四球"].shape[0]
                hbps = p_bat[p_bat["結果"] == "死球"].shape[0]
                
                hits = singles + doubles + triples + hrs
                pa = p_bat[p_bat["結果"].isin(pa_res)].shape[0]
                ab = p_bat[p_bat["結果"].isin(ab_res)].shape[0]
                rbi = pd.to_numeric(p_data["打点"], errors='coerce').sum()
                sb = pd.to_numeric(p_data["盗塁"], errors='coerce').sum()
                
                avg = hits / ab if ab > 0 else 0.000
                obp_demon = ab + bbs + hbps
                obp = (hits + bbs + hbps) / obp_demon if obp_demon > 0 else 0.000
                total_bases = singles + (doubles * 2) + (triples * 3) + (hrs * 4)
                slg = total_bases / ab if ab > 0 else 0.000
                ops = obp + slg

                batting_stats.append({
                    "No.": player_num,
                    "氏名": player, 
                    "打率": avg, "OPS": ops,
                    "本塁打": hrs, "打点": int(rbi), "安打": hits, 
                    "二塁打": doubles, "三塁打": triples, "出塁率": obp, 
                    "打席": pa, "打数": ab, "盗塁": int(sb), "四死球": bbs + hbps
                })
            
            if batting_stats:
                df_res = pd.DataFrame(batting_stats).sort_values("打率", ascending=False)
                for col in ["打率", "OPS", "出塁率"]:
                    df_res[col] = df_res[col].map(lambda x: f"{x:.3f}")
                
                cols = ["No.", "氏名", "打率", "OPS", "本塁打", "打点", "安打", "盗塁", "出塁率", "二塁打", "三塁打", "四死球", "打席", "打数"]
                st.dataframe(df_res[cols], use_container_width=True, hide_index=True)
        else:
            st.info("条件に一致する打撃データがありません。")

    # ----------------------------------------------------
    # (B) 投手部門（機能追加版）
    # ----------------------------------------------------
    with t_pit:
        if not df_p_target.empty:
            pitch_stats = []
            for p in all_players:
                pd_p = df_p_target[df_p_target["投手名"] == p]
                if pd_p.empty: continue
                
                # 基本スタッツ
                outs = pd_p["アウト数"].sum()
                er = pd_p["自責点"].sum()
                innings = outs / 3  # 投球回（数値）
                
                # 防御率
                era = (er * 9) / innings if innings > 0 else 0.0
                
                # 勝敗の集計（勝敗カラムがある場合のみ）
                if "勝敗" in pd_p.columns:
                    # "勝ち"や"勝利"を含む行をカウント
                    wins = pd_p[pd_p["勝敗"].astype(str).str.contains("勝|勝", na=False)].shape[0]
                    loses = pd_p[pd_p["勝敗"].astype(str).str.contains("負|敗", na=False)].shape[0]
                else:
                    wins = 0
                    loses = 0
                
                # 勝率
                win_pct = wins / (wins + loses) if (wins + loses) > 0 else 0.0
                
                # 奪三振
                ks = pd_p[pd_p["結果"] == "三振"].shape[0]
                # 四死球
                bbs = pd_p[pd_p["結果"].isin(["四球", "死球"])].shape[0]
                
                # 奪三振率 (K/9)
                k9 = (ks * 9) / innings if innings > 0 else 0.0
                
                # 四死球率 (BB/9) ※ここでは四球+死球で計算
                bb9 = (bbs * 9) / innings if innings > 0 else 0.0

                # 背番号取得
                p_num = PLAYER_NUMBERS.get(p, "-")
                
                pitch_stats.append({
                    "No.": p_num,
                    "氏名": p, 
                    "防御率": era,
                    "勝利": wins,
                    "敗戦": loses,
                    "勝率": win_pct,
                    "奪三振": ks,
                    "奪三振率": k9,
                    "四死球": bbs,
                    "四死球率": bb9,
                    "投球回": f"{outs//3}.{outs%3}", 
                    "失点": int(pd_p["失点"].sum())
                })
            
            if pitch_stats:
                df_p_res = pd.DataFrame(pitch_stats).sort_values("防御率")
                
                # 小数点フォーマット
                for col in ["防御率", "奪三振率", "四死球率", "勝率"]:
                    df_p_res[col] = df_p_res[col].map(lambda x: f"{x:.2f}" if col != "勝率" else f"{x:.3f}")

                # カラムの並び順整理
                cols_order = ["No.", "氏名", "防御率", "勝利", "敗戦", "勝率", "投球回", "奪三振", "奪三振率", "四死球", "四死球率", "失点"]
                st.dataframe(df_p_res[cols_order], use_container_width=True, hide_index=True)
        else:
            st.info("条件に一致する投手データがありません。")

    # ----------------------------------------------------
    # (C) 守備部門（ポジション別・守備率追加版）
    # ----------------------------------------------------
    with t_fld:
        st.write("※ 凡退・犠打・走塁死などの処理数（刺殺・補殺）と、失策数を集計します")
        
        if not df_p_target.empty and "処理野手" in df_p_target.columns:
            # データがあるものだけ抽出
            fld_data = df_p_target[df_p_target["処理野手"] != ""]
            
            if not fld_data.empty:
                # 1. クロス集計
                stats = pd.crosstab(fld_data["処理野手"], fld_data["結果"])
                
                # 2. 列の整理
                target_cols = ["凡退", "犠打", "失策", "走塁死", "牽制死", "盗塁死"]
                for col in target_cols:
                    if col not in stats.columns:
                        stats[col] = 0
                
                # 3. 指標計算
                out_cols = [c for c in target_cols if c != "失策"]
                stats["刺殺・補殺"] = stats[out_cols].sum(axis=1)
                stats["守備機会"] = stats["刺殺・補殺"] + stats["失策"]
                
                # 守備率
                stats["守備率"] = stats.apply(lambda row: (row["守備機会"] - row["失策"]) / row["守備機会"] if row["守備機会"] > 0 else 0.000, axis=1)
                
                stats = stats.reset_index()
                
                # -------------------------------------------------------
                # 【重要】ここが消えていた可能性があります（リスト作成＆ループ）
                # -------------------------------------------------------
                display_rows = []  # ← ここでリストを初期化
                pos_order_list = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                
                for _, row in stats.iterrows():
                    raw_name = row["処理野手"]
                    
                    # 名前分解
                    if "(" in raw_name and ")" in raw_name:
                        parts = raw_name.split(" (")
                        p_name = parts[0]
                        p_pos = parts[1].replace(")", "")
                    else:
                        p_name = raw_name
                        p_pos = "-"

                    # ソート用キー作成
                    try:
                        sort_key = pos_order_list.index(p_pos)
                    except ValueError:
                        sort_key = 99
                    
                    # 背番号
                    # PLAYER_NUMBERS が定義されていない場合のエラー回避
                    if "PLAYER_NUMBERS" in globals():
                        p_num = PLAYER_NUMBERS.get(p_name, "-")
                    else:
                        p_num = "-"

                    display_rows.append({
                        "SortKey": sort_key,
                        "位置": p_pos,
                        "No.": p_num,
                        "氏名": p_name,
                        "守備機会": row["守備機会"],
                        "刺殺・補殺": row["刺殺・補殺"],
                        "失策": row["失策"],
                        "守備率": row["守備率"]
                    })
                # -------------------------------------------------------

                # 4. 表示用データフレーム作成（エラー対策済み）
                if len(display_rows) > 0:
                    df_disp = pd.DataFrame(display_rows)
                else:
                    # 空の場合はカラム定義のみ行う
                    df_disp = pd.DataFrame(columns=["SortKey", "位置", "No.", "氏名", "守備機会", "刺殺・補殺", "失策", "守備率"])
                
                # 表示処理
                if not df_disp.empty:
                    df_disp = df_disp.sort_values(["SortKey", "守備機会"], ascending=[True, False])
                    df_disp["守備率"] = df_disp["守備率"].map(lambda x: f"{x:.3f}")
                
                final_cols = ["位置", "No.", "氏名", "守備機会", "刺殺・補殺", "失策", "守備率"]
                st.dataframe(df_disp[final_cols], use_container_width=True, hide_index=True)
                
                # グラフ
                st.caption("▼ ポジション別エラー数")
                if not df_disp.empty:
                    err_chart_df = df_disp[df_disp["失策"] > 0].sort_values("失策", ascending=False)
                    if not err_chart_df.empty:
                        err_chart_df["Label"] = err_chart_df["氏名"] + " (" + err_chart_df["位置"] + ")"
                        st.bar_chart(err_chart_df.set_index("Label")["失策"])
                    else:
                        st.write("失策の記録はありません。")
                else:
                    st.write("データがありません。")

            else:
                st.info("守備記録データがまだありません。")
        else:
            st.info("データがありません。")
            
# --- 👑 歴代記録 ---
elif menu == "👑 歴代記録":
    st.title("👑 チーム歴代記録")
    st.write("過去の全データから、シーズン記録（年度別）と通算記録のランキングを表示します。")

    # データ準備
    if df_batting.empty or df_pitching.empty:
        st.info("データがまだありません。")
    else:
        # 年度カラムを確実に作成
        df_batting["Year"] = pd.to_datetime(df_batting["日付"]).dt.year.astype(str)
        df_pitching["Year"] = pd.to_datetime(df_pitching["日付"]).dt.year.astype(str)

        # --------------------------------------------------
        # 集計ロジック関数
        # --------------------------------------------------
        def get_ranking_df(df, group_keys, agg_dict):
            # グルーピング集計
            grouped = df.groupby(group_keys).agg(agg_dict).reset_index()
            return grouped

        # --------------------------------------------------
        # A. 打撃データの整形 (年度・選手ごと)
        # --------------------------------------------------
        # ヒット系のカラム定義
        hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
        ab_cols = hit_cols + ["凡退", "失策", "走塁死", "盗塁死", "牽制死", "三振"]
        
        # まず打数などを計算するために、apply用にコピー
        df_b_calc = df_batting.copy()
        df_b_calc["is_hit"] = df_b_calc["結果"].isin(hit_cols).astype(int)
        df_b_calc["is_ab"] = df_b_calc["結果"].isin(ab_cols).astype(int)
        df_b_calc["is_hr"] = (df_b_calc["結果"] == "本塁打").astype(int)
        
        # 数値型に変換
        for col in ["打点", "盗塁", "得点"]:
            df_b_calc[col] = pd.to_numeric(df_b_calc[col], errors='coerce').fillna(0)

        # 集計ルール
        agg_rules_b = {
            "is_hit": "sum", # 安打数
            "is_ab": "sum",  # 打数
            "is_hr": "sum",  # 本塁打
            "打点": "sum",
            "盗塁": "sum",
            "得点": "sum"
        }

        # --------------------------------------------------
        # B. 投手データの整形
        # --------------------------------------------------
        df_p_calc = df_pitching.copy()
        
        # 数値変換
        for col in ["アウト数", "自責点", "失点"]:
             df_p_calc[col] = pd.to_numeric(df_p_calc[col], errors='coerce').fillna(0)

        # 奪三振カウント
        df_p_calc["is_so"] = (df_p_calc["結果"] == "三振").astype(int)
        
        # 勝敗カウント用
        df_p_calc["is_win"] = df_p_calc["勝敗"].astype(str).str.contains("勝").astype(int)

        agg_rules_p = {
            "アウト数": "sum",
            "自責点": "sum",
            "is_so": "sum", # 奪三振
            "is_win": "sum" # 勝利数
        }
        
        # ==================================================
        # 表示用関数（ランキング生成）
        # ==================================================
        def show_top5(title, df, sort_col, label_col, value_col, ascending=False, suffix="", format_float=False):
            st.markdown(f"##### {title}")
            
            # ソート
            sorted_df = df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
            # 上位5名抽出
            top5 = sorted_df.head(5)
            
            for i, row in top5.iterrows():
                rank = i + 1
                icon = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
                
                val = row[value_col]
                if format_float:
                    val_str = f"{val:.3f}"
                else:
                    val_str = f"{int(val)}"
                
                # 表示: 1. 中尾 (2025) : 10 本
                st.write(f"{icon} **{row[label_col]}** : {val_str}{suffix}")
            
            if top5.empty:
                st.write("データなし")

        # ==================================================
        # タブ切り替え
        # ==================================================
        tab_season, tab_career = st.tabs(["📅 シーズン記録 (年度別)", "🏅 通算記録 (歴代)"])

        # --- 1. シーズン記録 (年度×選手) ---
        with tab_season:
            # 規定打席・投球回のフィルタ設定
            c_fil1, c_fil2 = st.columns(2)
            min_ab = c_fil1.number_input("打率ランキングの最低打数", value=10, min_value=1)
            min_inn = c_fil2.number_input("防御率ランキングの最低投球回", value=5, min_value=1)

            # データ作成
            season_bat = get_ranking_df(df_b_calc, ["Year", "選手名"], agg_rules_b)
            season_pit = get_ranking_df(df_p_calc, ["Year", "投手名"], agg_rules_p)

            # 指標計算
            # 打率
            season_bat["AVG"] = season_bat.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
            # 防御率
            season_pit["Innings"] = season_pit["アウト数"] / 3
            season_pit["ERA"] = season_pit.apply(lambda x: (x["自責点"] * 9) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)

            # 表示用ラベル作成 "選手名 (年度)"
            season_bat["Display"] = season_bat["選手名"] + " (" + season_bat["Year"] + ")"
            season_pit["Display"] = season_pit["投手名"] + " (" + season_pit["Year"] + ")"

            # --- 表示レイアウト ---
            st.markdown("#### ⚔️ 打撃部門 (シーズン)")
            c1, c2, c3 = st.columns(3)
            with c1:
                # 打率（規定打数以上のみ）
                filtered_avg = season_bat[season_bat["is_ab"] >= min_ab]
                show_top5("打率", filtered_avg, "AVG", "Display", "AVG", suffix="", format_float=True)
            with c2:
                show_top5("本塁打", season_bat, "is_hr", "Display", "is_hr", suffix=" 本")
            with c3:
                show_top5("打点", season_bat, "打点", "Display", "打点", suffix=" 点")

            st.write("")
            c4, c5, c6 = st.columns(3)
            with c4:
                show_top5("安打数", season_bat, "is_hit", "Display", "is_hit", suffix=" 本")
            with c5:
                show_top5("盗塁", season_bat, "盗塁", "Display", "盗塁", suffix=" 個")
            with c6:
                show_top5("得点", season_bat, "得点", "Display", "得点", suffix=" 点")

            st.divider()

            st.markdown("#### 🛡️ 投手部門 (シーズン)")
            p1, p2, p3 = st.columns(3)
            with p1:
                # 防御率（規定回数以上のみ、昇順）
                filtered_era = season_pit[season_pit["Innings"] >= min_inn]
                show_top5("防御率", filtered_era, "ERA", "Display", "ERA", ascending=True, suffix="", format_float=False) # ERAは2桁フォーマット別途必要だが簡易的に
            with p2:
                show_top5("勝利数", season_pit, "is_win", "Display", "is_win", suffix=" 勝")
            with p3:
                show_top5("奪三振", season_pit, "is_so", "Display", "is_so", suffix=" 個")

        # --- 2. 通算記録 (選手ごと) ---
        with tab_career:
            st.caption("※チーム在籍中の全期間の合計成績です")
            
            # 年度を無視して集計
            career_bat = get_ranking_df(df_b_calc, ["選手名"], agg_rules_b)
            career_pit = get_ranking_df(df_p_calc, ["投手名"], agg_rules_p)

            # 指標計算
            career_bat["AVG"] = career_bat.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
            career_pit["Innings"] = career_pit["アウト数"] / 3
            career_pit["ERA"] = career_pit.apply(lambda x: (x["自責点"] * 9) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)

            # 表示用ラベル（選手名のみ）
            career_bat["Display"] = career_bat["選手名"]
            career_pit["Display"] = career_pit["投手名"]
            
            # --- 表示レイアウト ---
            st.markdown("#### ⚔️ 打撃部門 (通算)")
            tc1, tc2, tc3 = st.columns(3)
            with tc1:
                # 通算打率は基準を高めに設定（例: 30打数）
                filtered_c_avg = career_bat[career_bat["is_ab"] >= (min_ab * 2)] 
                show_top5("通算打率", filtered_c_avg, "AVG", "Display", "AVG", suffix="", format_float=True)
            with tc2:
                show_top5("通算本塁打", career_bat, "is_hr", "Display", "is_hr", suffix=" 本")
            with tc3:
                show_top5("通算打点", career_bat, "打点", "Display", "打点", suffix=" 点")

            st.write("")
            tc4, tc5, tc6 = st.columns(3)
            with tc4:
                show_top5("通算安打", career_bat, "is_hit", "Display", "is_hit", suffix=" 本")
            with tc5:
                show_top5("通算盗塁", career_bat, "盗塁", "Display", "盗塁", suffix=" 個")
            with tc6:
                # 試合出場数（概算：打席データの行数とは異なるが、ここでは打席に立った数として）
                show_top5("通算打数", career_bat, "is_ab", "Display", "is_ab", suffix=" 打数")

            st.divider()
            
            st.markdown("#### 🛡️ 投手部門 (通算)")
            tp1, tp2, tp3 = st.columns(3)
            with tp1:
                filtered_c_era = career_pit[career_pit["Innings"] >= (min_inn * 2)]
                show_top5("通算防御率", filtered_c_era, "ERA", "Display", "ERA", ascending=True, suffix="")
            with tp2:
                show_top5("通算勝利", career_pit, "is_win", "Display", "is_win", suffix=" 勝")
            with tp3:
                show_top5("通算奪三振", career_pit, "is_so", "Display", "is_so", suffix=" 個")