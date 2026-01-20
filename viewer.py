import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# ==========================================
# 1. ページ・CSS設定
# ==========================================
st.set_page_config(page_title="KAGURA Official Stats (閲覧用)", layout="wide", page_icon="⚾")
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    h1, h2, h3 { color: #1e3a8a; }
    [data-testid="stMetricValue"] { font-size: 24px !important; color: #d90429 !important; }
    [data-testid="stTable"] th { background-color: #e0e0e0 !important; border-bottom: 2px solid #000 !important; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 定数・辞書定義 (メインアプリと同期)
# ==========================================
PLAYER_NUMBERS = {
    "佐藤蓮太": "1", "久保田剛志": "2", "開田凌空": "3", "水谷真智": "4", "河野潤樹": "5",
    "渡邉誠也": "7", "岡﨑英一": "8", "中尾建太": "10", "内藤洋輔": "11", "大高翼": "13",
    "小野拓朗": "15", "古屋翔": "17", "伊東太建": "18", "渡邉竣太": "19", "山田大貴": "21",
    "志村裕三": "23", "石田貴大": "24", "相原一博": "25", "田中伸延": "26", "坂本昂士": "27",
    "渡辺羽": "28", "石原圭佑": "29", "名執栄一": "30", "荒木豊": "31", "永井雄太": "33",
    "小野慎也": "38", "清水智広": "43", "名執雅叶": "51", "山縣諒介": "60", "照屋航": "63",
    "望月駿": "66", "鈴木翔大": "73",
    "名執雅楽": "", "名執冬雅": "", "杉山颯": "", "助っ人1": "", "助っ人2": "", "助っ人3": "",
    "助っ人4": "", "助っ人5": "", "塚田晴琉": "", "野澤貫太": "", "山中啓至": "", "前田琳太郎": ""
}
all_players = list(PLAYER_NUMBERS.keys())
my_team_fixed = "KAGURA"

# 公式戦として扱う大会名のリスト
OFFICIAL_GAME_TYPES = ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯", "公式戦"]

# ==========================================
# 3. データ読み込み & 共通関数
# ==========================================
# ⚠️ ここにスプレッドシートのURLを設定してください
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    try:
        df_b = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="打撃成績")
        df_p = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績")
        
        # カラム補正
        if df_b.empty:
            df_b = pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])
        if df_p.empty:
            df_p = pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "処理野手", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "勝敗"])
            
        # 日付変換
        df_b["日付"] = pd.to_datetime(df_b["日付"], errors='coerce')
        df_p["日付"] = pd.to_datetime(df_p["日付"], errors='coerce')
        
        # 文字列型の日付カラムも作っておく（集計用）
        df_b["DateStr"] = df_b["日付"].dt.strftime('%Y-%m-%d')
        df_p["DateStr"] = df_p["日付"].dt.strftime('%Y-%m-%d')
        
        return df_b, df_p
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_batting, df_pitching = load_data()

# --- 共通計算関数 ---
def get_ranking_df(df, group_keys, agg_dict):
    if df.empty: return pd.DataFrame()
    grouped = df.groupby(group_keys).agg(agg_dict).reset_index()
    return grouped

def calc_advanced_stats(df):
    # 打率
    df["AVG"] = df.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
    # 出塁率 (OBP)
    df["OBP"] = df.apply(lambda x: (x["is_hit"] + x["is_bb"]) / (x["is_ab"] + x["is_bb"]) if (x["is_ab"] + x["is_bb"]) > 0 else 0, axis=1)
    # 長打率 (SLG)
    if "is_1b" in df.columns:
        df["TotalBases"] = df["is_1b"] + (df["is_2b"] * 2) + (df["is_3b"] * 3) + (df["is_hr"] * 4)
        df["SLG"] = df.apply(lambda x: x["TotalBases"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
        # OPS
        df["OPS"] = df["OBP"] + df["SLG"]
    else:
        df["OPS"] = 0
    return df

def show_top5(title, df, sort_col, label_col, value_col, ascending=False, suffix="", format_float=False):
    st.markdown(f"##### {title}")
    if ascending:
        target_df = df.copy() 
    else:
        target_df = df[df[value_col] > 0].copy()

    sorted_df = target_df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
    top5 = sorted_df.head(5)
    if top5.empty:
        st.caption("データなし")
    else:
        for i, row in top5.iterrows():
            rank = i + 1
            icon = " 🥇 " if rank == 1 else " 🥈 " if rank == 2 else " 🥉 " if rank == 3 else f"{rank}."
            val = row[value_col]
            val_str = f"{val:.3f}" if format_float else (f"{val:.2f}" if ascending else f"{int(val)}")
            st.write(f"{icon} **{row[label_col]}** : {val_str}{suffix}")

def render_scoreboard(b_df, p_df, date_txt, m_type, g_name, opp_name, is_top_first=True):
    st.markdown(f"###   📅   {date_txt} ({m_type}) &nbsp;&nbsp;   🏟️   {g_name}")
    st.subheader(f"⚾ {my_team_fixed} vs {opp_name}")

    # ▼▼▼ 追加: チーム記録優先ロジック (重複防止) ▼▼▼
    # 「チーム記録」の行がある場合はそれだけを使う（個人成績との二重計上を防ぐ）
    if "選手名" in b_df.columns and (b_df["選手名"] == "チーム記録").any():
        b_df_calc = b_df[b_df["選手名"] == "チーム記録"]
    else:
        b_df_calc = b_df

    if "選手名" in p_df.columns and (p_df["選手名"] == "チーム記録").any():
        p_df_calc = p_df[p_df["選手名"] == "チーム記録"]
    elif "投手名" in p_df.columns and (p_df["投手名"] == "チーム記録").any():
        p_df_calc = p_df[p_df["投手名"] == "チーム記録"]
    else:
        p_df_calc = p_df
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    k_inning, opp_inning = [], []
    total_k, total_opp = 0, 0

    for i in range(1, 10):
        inn = f"{i}回"
        # ▼ 修正: フィルタ済みの b_df_calc, p_df_calc を使用する
        inn_bat_data = b_df_calc[b_df_calc["イニング"] == inn]
        k_runs = int(pd.to_numeric(inn_bat_data["得点"], errors='coerce').sum())

        opp_data_inn = p_df_calc[p_df_calc["イニング"] == inn]
        opp_runs = int(pd.to_numeric(opp_data_inn["失点"], errors='coerce').sum())
        
        # k_exists, opp_exists の判定も計算用DFで行う
        k_exists = not inn_bat_data.empty
        opp_exists = not opp_data_inn.empty
        k_inning.append(str(k_runs) if k_exists else "")
        opp_inning.append(str(opp_runs) if opp_exists else "")

        total_k += k_runs
        total_opp += opp_runs

    hit_list = ["単打", "二塁打", "三塁打", "本塁打", "安打"]
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
    st.table(pd.DataFrame(score_dict).set_index("チーム"))

# ----------------------------------------------------------------------
# ▼▼▼ 挿入箇所: render_scoreboard関数の定義が終わった直後に入れてください ▼▼▼
# ----------------------------------------------------------------------

# --- 試合詳細データを表示する関数 (共通化) ---
def render_match_details(day_b, day_p):
    t_d_bat, t_d_pit = st.tabs(["打撃詳細", "投手詳細"])
    
    with t_d_bat:
        # ベンチ以外、かつ「チーム記録」を除外
        active_b = day_b[~day_b["イニング"].astype(str).str.contains("ベンチ")].copy()
        
        # チーム記録の除外処理
        active_b = active_b[active_b["選手名"] != "チーム記録"]

        if not active_b.empty:
            def inn_key(x):
                try: return int(str(x).replace("回", ""))
                except: return 99
            active_b["_sort"] = active_b["イニング"].apply(inn_key)
            active_b = active_b.sort_values(["_sort"])
            
            players = active_b["選手名"].unique()
            rows = []
            max_cols = 0
            
            for i, p in enumerate(players):
                p_df = active_b[active_b["選手名"] == p]
                res_list = p_df[p_df["種別"] == "打撃"]["結果"].tolist()
                if len(res_list) > max_cols: max_cols = len(res_list)
                
                rbi = pd.to_numeric(p_df["打点"], errors='coerce').sum()
                run = pd.to_numeric(p_df["得点"], errors='coerce').sum()
                sb = pd.to_numeric(p_df["盗塁"], errors='coerce').sum()
                hits = p_df[p_df["結果"].isin(["単打", "二塁打", "三塁打", "本塁打", "安打"])].shape[0]
                pos = p_df["位置"].iloc[-1] if "位置" in p_df.columns else ""
                
                rows.append({
                    "打順": i+1, "選手名": p, "守備": pos,
                    "安打": hits, "打点": int(rbi), "得点": int(run), "盗塁": int(sb),
                    "results": res_list
                })
            
            if rows:
                df_show = pd.DataFrame(rows)
                for k in range(max_cols):
                    df_show[f"第{k+1}打席"] = df_show["results"].apply(lambda x: x[k] if k < len(x) else "")
                
                cols = ["打順", "守備", "選手名"] + [f"第{k+1}打席" for k in range(max_cols)] + ["安打", "打点", "得点", "盗塁"]
                st.dataframe(df_show[cols], hide_index=True, use_container_width=True)
        else:
            st.info("詳細データなし")

    with t_d_pit:
        if not day_p.empty and "投手名" in day_p.columns:
            p_real = day_p[day_p["投手名"] != "チーム記録"]
            if not p_real.empty:
                p_stats = []
                for p_name, g in p_real.groupby("投手名"):
                    outs = pd.to_numeric(g["アウト数"], errors='coerce').sum()
                    inn_str = f"{int(outs//3)}回{int(outs%3)}/3"
                    er = pd.to_numeric(g["自責点"], errors='coerce').sum()
                    r = pd.to_numeric(g["失点"], errors='coerce').sum()
                    balls = pd.to_numeric(g["球数"], errors='coerce').sum()
                    p_stats.append({
                        "投手名": p_name, "投球回": inn_str, "球数": int(balls),
                        "失点": int(r), "自責点": int(er)
                    })
                st.dataframe(pd.DataFrame(p_stats), hide_index=True, use_container_width=True)
            else:
                st.info("投手詳細なし")
        else:
            st.info("データなし")
# ----------------------------------------------------------------------

# ==========================================
# 4. サイドバーメニュー
# ==========================================
st.sidebar.title("⚾ KAGURA Stats")
st.sidebar.caption("閲覧専用モード")
menu = st.sidebar.radio("MENU", [" 🏠  最新試合結果", " 🏆  チーム成績", " 📊  個人成績"])

# ==========================================
# 5. 各ページの実装
# ==========================================

# -------------------------------------------------------------------
# PAGE: 最新試合結果
# -------------------------------------------------------------------
if menu == " 🏠  最新試合結果":
    st.title(" 📢  最新試合結果")
    
    if not df_batting.empty:
        # 最新の日付を取得
        latest_date = df_batting["日付"].max()
        latest_date_str = latest_date.strftime('%Y-%m-%d')
        
        # その日のデータを抽出
        day_b = df_batting[df_batting["DateStr"] == latest_date_str]
        day_p = df_pitching[df_pitching["DateStr"] == latest_date_str]
        
        if not day_b.empty:
            opp = day_b["対戦相手"].iloc[0] if "対戦相手" in day_b.columns else "-"
            ground = day_b["グラウンド"].iloc[0] if "グラウンド" in day_b.columns else "-"
            m_type = day_b["試合種別"].iloc[0] if "試合種別" in day_b.columns else "-"
            
            # スコアボード
            render_scoreboard(day_b, day_p, latest_date_str, m_type, ground, opp, is_top_first=True)
            
            st.divider()
            st.subheader(" 📝  試合詳細データ")
            # ▼▼▼ 修正: 関数定義を削除し、呼び出し(実行)コードだけにする ▼▼▼
            render_match_details(day_b, day_p)
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# -------------------------------------------------------------------
# PAGE: チーム成績
# -------------------------------------------------------------------
elif menu == " 🏆  チーム成績":
    st.title(" 🏆  チーム成績ダッシュボード")
    
    if not df_batting.empty:
        # データ前処理 (チーム成績集計用)
        # ※本来はメインアプリと同様の複雑な集計ロジックが必要ですが、
        #   ここでは簡略化のため、既存のデータフレームから計算します。
        
        # 1. 試合ごとの集計データを作成
        df_b_src = df_batting.copy()
        df_b_src["Year"] = df_b_src["日付"].dt.year.astype(str)
        
        # フィルタリング
        all_years = sorted(df_b_src["Year"].unique().tolist(), reverse=True)
        
        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1:
            default_idx = 1 if all_years else 0
            sel_year = st.selectbox("年度", ["通算"] + all_years, index=default_idx)
        
        with c_f2:
            types = [x for x in df_b_src["試合種別"].unique() if x]
            others = [t for t in types if t != "練習試合"]
            type_opts = ["全種別", "練習試合", "公式戦 (トータル)"] + sorted(others)
            sel_type = st.selectbox("試合種別", type_opts)
            
        with c_f3:
            opps = sorted([x for x in df_b_src["対戦相手"].unique() if x])
            sel_opp = st.selectbox("対戦相手", ["全対戦相手"] + opps)

        # フィルタ適用
        df_view = df_b_src.copy()
        df_p_view = df_pitching.copy()
        df_p_view["Year"] = df_p_view["日付"].dt.year.astype(str)

        if sel_year != "通算":
            df_view = df_view[df_view["Year"] == sel_year]
            df_p_view = df_p_view[df_p_view["Year"] == sel_year]
            
        if sel_type != "全種別":
            if sel_type == "公式戦 (トータル)":
                df_view = df_view[df_view["試合種別"].isin(OFFICIAL_GAME_TYPES)]
                df_p_view = df_p_view[df_p_view["試合種別"].isin(OFFICIAL_GAME_TYPES)]
            else:
                df_view = df_view[df_view["試合種別"] == sel_type]
                df_p_view = df_p_view[df_p_view["試合種別"] == sel_type]
                
        if sel_opp != "全対戦相手":
            df_view = df_view[df_view["対戦相手"] == sel_opp]
            df_p_view = df_p_view[df_p_view["対戦相手"] == sel_opp]

        if not df_view.empty:
            # 集計
            dates = sorted(df_view["DateStr"].unique(), reverse=True)
            wins, losses, draws = 0, 0, 0
            total_runs, total_lost = 0, 0
            match_history = []

            for d in dates:
                d_b = df_view[df_view["DateStr"] == d]
                d_p = df_p_view[df_p_view["DateStr"] == d]
                
                # ▼▼▼ 修正: 重複防止ロジック（チーム記録がある場合はそちらを優先） ▼▼▼
                # 得点計算
                if "選手名" in d_b.columns and (d_b["選手名"] == "チーム記録").any():
                    score = pd.to_numeric(d_b[d_b["選手名"] == "チーム記録"]["得点"], errors='coerce').sum()
                else:
                    score = pd.to_numeric(d_b["得点"], errors='coerce').sum()

                # 失点計算
                if "選手名" in d_p.columns and (d_p["選手名"] == "チーム記録").any():
                    lost = pd.to_numeric(d_p[d_p["選手名"] == "チーム記録"]["失点"], errors='coerce').sum()
                elif "投手名" in d_p.columns and (d_p["投手名"] == "チーム記録").any():
                    lost = pd.to_numeric(d_p[d_p["投手名"] == "チーム記録"]["失点"], errors='coerce').sum()
                else:
                    lost = pd.to_numeric(d_p["失点"], errors='coerce').sum()
                # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

                total_runs += score
                total_lost += lost

                res = "引分"
                if score > lost: 
                    wins += 1; res = "〇 勝利"
                elif score < lost: 
                    losses += 1; res = "● 敗戦"
                else: 
                    draws += 1
                
                opp_name = d_b["対戦相手"].iloc[0] if "対戦相手" in d_b.columns else "-"
                g_name = d_b["グラウンド"].iloc[0] if "グラウンド" in d_b.columns else "-"
                
                match_history.append({
                    "日付": d, "対戦相手": opp_name, "結果": res,
                    "スコア": f"{int(score)} - {int(lost)}", "グラウンド": g_name
                })

            games = wins + losses + draws
            win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0

            # ... (以下、打率などの計算部分は `df_view` のまま利用しますが、
            #      打率計算などは個人成績ベースで行うのが基本のため、チーム記録行を除外したほうが正確です) ...
            
            # 打撃スタッツ用（チーム記録行を除外）
            df_stats_src = df_view[df_view["選手名"] != "チーム記録"]
            hits = len(df_stats_src[df_stats_src["結果"].isin(["単打", "二塁打", "三塁打", "本塁打", "安打"])])
            ab_list = ["単打", "二塁打", "三塁打", "本塁打", "安打", "三振", "凡退", "失策", "併殺打", "野選"]
            ab = len(df_stats_src[df_stats_src["結果"].isin(ab_list)])
            avg = hits / ab if ab > 0 else 0.0
            
            # 投手スタッツ
            er = pd.to_numeric(df_p_view["自責点"], errors='coerce').sum()
            outs = pd.to_numeric(df_p_view["アウト数"], errors='coerce').sum()
            era = (er * 7) / (outs / 3) if outs > 0 else 0.0

            # 表示
            st.markdown("##### 📊 チーム成績サマリー")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("試合数", games)
            m2.metric("勝利", wins)
            m3.metric("敗戦", losses)
            m4.metric("引分", draws)
            m5.metric("勝率", f"{win_rate:.3f}")
            
            st.divider()
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("チーム打率", f"{avg:.3f}")
            c2.metric("総得点", int(total_runs))
            c3.metric("総失点", int(total_lost))
            c4.metric("防御率", f"{era:.2f}")

            # ▼▼▼ 追加: 試合履歴 & 詳細ビューワー ▼▼▼
            st.divider()
            st.subheader(" 📜  試合履歴 & 詳細ビューワー")
            
            if match_history:
                # 2. 履歴テーブル表示
                df_hist = pd.DataFrame(match_history)
                st.dataframe(df_hist, hide_index=True, use_container_width=True)
                
                # 3. 詳細表示用セレクタ
                st.write("")
                st.markdown("##### 🔍 試合の詳細を確認")
                # セレクトボックス用に文字列を作成
                match_opts = df_hist.apply(lambda x: f"{x['日付']} vs {x['対戦相手']} ({x['結果']})", axis=1).tolist()
                sel_match_str = st.selectbox("試合を選択してください", match_opts, key="team_history_sel")
                
                if sel_match_str:
                    sel_date = sel_match_str.split(" ")[0] # 日付部分を抽出
                    
                    target_b = df_batting[df_batting["DateStr"] == sel_date]
                    target_p = df_pitching[df_pitching["DateStr"] == sel_date]
                    
                    if not target_b.empty:
                        m_opp = target_b["対戦相手"].iloc[0]
                        m_g = target_b["グラウンド"].iloc[0]
                        m_type = target_b["試合種別"].iloc[0]
                        
                        st.markdown("---")
                        # スコアボード表示
                        render_scoreboard(target_b, target_p, sel_date, m_type, m_g, m_opp)
                        # 詳細データ表示 (修正した関数を使用)
                        render_match_details(target_b, target_p)
            else:
                st.info("表示できる試合履歴がありません")
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        else:
            st.info("データがありません")
    else:
        st.info("データがありません")

# -------------------------------------------------------------------
# PAGE: 成績・記録
# -------------------------------------------------------------------
elif menu == " 📊  個人成績":
    st.title(" 📊  個人成績")
    
    # データ整形
    if not df_batting.empty:
        df_batting["Year"] = df_batting["日付"].dt.year.astype(str)
        df_pitching["Year"] = df_pitching["日付"].dt.year.astype(str)
        
        # 打撃計算用
        df_b_calc = df_batting.copy()
        df_b_calc = df_b_calc[df_b_calc["選手名"] != "チーム記録"]
        hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
        ab_cols = hit_cols + ["凡退", "失策", "走塁死", "盗塁死", "牽制死", "三振", "併殺打", "野選", "振り逃げ", "打撃妨害"]
        
        df_b_calc["is_hit"] = df_b_calc["結果"].isin(hit_cols).astype(int)
        df_b_calc["is_ab"] = df_b_calc["結果"].isin(ab_cols).astype(int)
        df_b_calc["is_hr"] = (df_b_calc["結果"] == "本塁打").astype(int)
        df_b_calc["is_1b"] = (df_b_calc["結果"] == "単打").astype(int)
        df_b_calc["is_2b"] = (df_b_calc["結果"] == "二塁打").astype(int)
        df_b_calc["is_3b"] = (df_b_calc["結果"] == "三塁打").astype(int)
        df_b_calc["is_bb"] = (df_b_calc["結果"].isin(["四球", "死球"])).astype(int)
        for c in ["打点", "盗塁", "得点"]:
            df_b_calc[c] = pd.to_numeric(df_b_calc[c], errors='coerce').fillna(0)
            
        agg_rules_b = {
            "is_hit": "sum", "is_ab": "sum", "is_hr": "sum",
            "is_1b": "sum", "is_2b": "sum", "is_3b": "sum", "is_bb": "sum",
            "打点": "sum", "盗塁": "sum", "得点": "sum"
        }
        
        # 投手計算用
        df_p_calc = df_pitching.copy()
        if "投手名" in df_p_calc.columns:
            df_p_calc = df_p_calc[df_p_calc["投手名"] != "チーム記録"]
            # 名前補完
            if "選手名" in df_p_calc.columns:
                 df_p_calc["投手名"] = df_p_calc["投手名"].replace("", pd.NA).fillna(df_p_calc["選手名"])
        
        df_p_calc["is_so"] = (df_p_calc["結果"] == "三振").astype(int)
        if "勝敗" in df_p_calc.columns:
            df_p_calc["is_win"] = df_p_calc["勝敗"].astype(str).str.contains("勝").astype(int)
            df_p_calc["is_lose"] = df_p_calc["勝敗"].astype(str).str.contains("負|敗").astype(int)
        else:
            df_p_calc["is_win"] = 0; df_p_calc["is_lose"] = 0
            
        for c in ["自責点", "失点", "アウト数", "被安打", "与四球"]:
            if c not in df_p_calc.columns: df_p_calc[c] = 0
            df_p_calc[c] = pd.to_numeric(df_p_calc[c], errors='coerce').fillna(0)
        
        df_p_calc["is_bb_detail"] = df_p_calc["結果"].isin(["四球", "死球"]).astype(int)
        df_p_calc["total_bb"] = df_p_calc["与四球"] + df_p_calc["is_bb_detail"]
        
        agg_rules_p = {
            "アウト数": "sum", "自責点": "sum", "失点": "sum",
            "is_so": "sum", "is_win": "sum", "is_lose": "sum",
            "被安打": "sum", "total_bb": "sum"
        }

        # タブ構成
        t1, t2, t3, t4 = st.tabs([" 👤  個人通算成績", " 📈  個人年度別", " 🏆  期間別ランキング", " 👑  歴代記録"])
        
        # --- Tab 1: 個人通算成績 ---
        with t1:
            st.markdown("####  📊  個人成績一覧 (通算・年度別フィルター)")
            years = sorted(list(set(df_b_calc["Year"].unique()) | set(df_p_calc["Year"].unique())), reverse=True)
            
            c1, c2 = st.columns(2)
            default_idx = 1 if years else 0
            sel_year = c1.selectbox("年度", ["通算"] + years, index=default_idx, key="p_stat_year")
            
            # 種別選択
            types = [x for x in df_b_calc["試合種別"].unique() if x]
            others = [t for t in types if t != "練習試合"]
            type_opts = ["全種別", "練習試合", "公式戦 (トータル)"] + sorted(others)
            sel_type = c2.selectbox("試合種別", type_opts, key="p_stat_type")
            
            # フィルタ
            target_b = df_b_calc.copy()
            target_p = df_p_calc.copy()
            
            if sel_year != "通算":
                target_b = target_b[target_b["Year"] == sel_year]
                target_p = target_p[target_p["Year"] == sel_year]
            
            if sel_type != "全種別":
                if sel_type == "公式戦 (トータル)":
                    target_b = target_b[target_b["試合種別"].isin(OFFICIAL_GAME_TYPES)]
                    target_p = target_p[target_p["試合種別"].isin(OFFICIAL_GAME_TYPES)]
                else:
                    target_b = target_b[target_b["試合種別"] == sel_type]
                    target_p = target_p[target_p["試合種別"] == sel_type]
            
            st_b, st_p, st_fld = st.tabs(["打撃部門", "投手部門", "守備部門"])
            
            with st_b:
                if not target_b.empty:
                    res_df = get_ranking_df(target_b, ["選手名"], agg_rules_b)
                    res_df = calc_advanced_stats(res_df)
                    
                    # No. 追加
                    res_df["No."] = res_df["選手名"].apply(lambda x: PLAYER_NUMBERS.get(x, "-"))
                    
                    # 表示カラム
                    cols = ["No.", "選手名", "AVG", "OPS", "is_hr", "打点", "is_hit", "盗塁", "is_ab"]
                    disp_cols = ["No.", "氏名", "打率", "OPS", "本塁打", "打点", "安打", "盗塁", "打数"]
                    
                    res_df = res_df.rename(columns={"選手名": "氏名", "is_hr": "本塁打", "is_hit": "安打", "is_ab": "打数"})
                    res_df = res_df.rename(columns={"AVG": "打率"})
                    
                    # フォーマット
                    res_df["打率"] = res_df["打率"].map(lambda x: f"{x:.3f}")
                    res_df["OPS"] = res_df["OPS"].map(lambda x: f"{x:.3f}")
                    
                    st.dataframe(res_df[disp_cols].sort_values("打率", ascending=False), hide_index=True, use_container_width=True)
                else:
                    st.info("データなし")
            
            with st_p:
                if not target_p.empty:
                    res_df_p = get_ranking_df(target_p, ["投手名"], agg_rules_p)
                    res_df_p["Innings"] = res_df_p["アウト数"] / 3
                    res_df_p["ERA"] = res_df_p.apply(lambda x: (x["自責点"] * 7) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)
                    res_df_p["WHIP"] = res_df_p.apply(lambda x: (x["total_bb"] + x["被安打"]) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)
                    
                    res_df_p["No."] = res_df_p["投手名"].apply(lambda x: PLAYER_NUMBERS.get(x, "-"))
                    
                    # 表示
                    res_df_p["投球回"] = res_df_p["Innings"].map(lambda x: f"{int(x)}.{int((x*3)%3)}")
                    
                    cols = ["No.", "投手名", "ERA", "WHIP", "is_win", "is_lose", "is_so", "投球回"]
                    disp_cols = ["No.", "氏名", "防御率", "WHIP", "勝利", "敗戦", "奪三振", "投球回"]
                    
                    res_df_p = res_df_p.rename(columns={"投手名": "氏名", "is_win": "勝利", "is_lose": "敗戦", "is_so": "奪三振", "ERA": "防御率"})
                    
                    res_df_p["防御率"] = res_df_p["防御率"].map(lambda x: f"{x:.2f}")
                    res_df_p["WHIP"] = res_df_p["WHIP"].map(lambda x: f"{x:.2f}")
                    
                    st.dataframe(res_df_p[disp_cols].sort_values("防御率"), hide_index=True, use_container_width=True)
                else:
                    st.info("データなし")

            # (C) ▼▼▼ 追加: 守備部門 ▼▼▼
            with st_fld:
                # 処理野手が記録されているデータを抽出
                if not target_p.empty and "処理野手" in target_p.columns:
                    df_f = target_p[target_p["処理野手"].notna() & (target_p["処理野手"] != "")].copy()
                    
                    if not df_f.empty:
                        # 名前とポジションが混在している場合 ("佐藤 (投)") などを考慮して集計
                        # ここではシンプルに「処理野手」の文字列そのままでグルーピングします
                        
                        fld_stats = []
                        for p_name, group in df_f.groupby("処理野手"):
                            # 守備機会 = その選手が関与した全プレイ数
                            chances = len(group)
                            # 失策数
                            errors = len(group[group["結果"] == "失策"])
                            # 守備率 = (機会 - 失策) / 機会
                            fpct = (chances - errors) / chances if chances > 0 else 0.000
                            
                            # 表示用背番号取得 (名前部分だけ抽出してマッチング)
                            pure_name = p_name.split(" (")[0] if "(" in p_name else p_name
                            p_num = PLAYER_NUMBERS.get(pure_name, "-")
                            
                            fld_stats.append({
                                "No.": p_num,
                                "氏名": p_name,
                                "守備機会": chances,
                                "失策": errors,
                                "守備率": fpct
                            })
                        
                        if fld_stats:
                            df_show_f = pd.DataFrame(fld_stats).sort_values(["守備率", "守備機会"], ascending=[False, False])
                            df_show_f["守備率"] = df_show_f["守備率"].map(lambda x: f"{x:.3f}")
                            
                            st.dataframe(
                                df_show_f[["No.", "氏名", "守備機会", "失策", "守備率"]],
                                hide_index=True,
                                use_container_width=True
                            )
                        else:
                            st.info("守備記録なし")
                    else:
                        st.info("守備データなし")
                else:
                    st.info("データなし")

        # --- Tab 2: 個人年度別 ---
        with t2:
            st.markdown("####  📈  個人年度別成績推移")
            target_player = st.selectbox("選手を選択", all_players)
            
            if target_player:
                p_hist = df_b_calc[df_b_calc["選手名"] == target_player]
                
                if not p_hist.empty:
                    # 年度別集計
                    hist_df = get_ranking_df(p_hist, ["Year"], agg_rules_b)
                    hist_df = calc_advanced_stats(hist_df)
                    hist_df = hist_df.sort_values("Year", ascending=False)
                    
                    # ▼▼▼ 追加: 通算行の計算 ▼▼▼
                    total_row = hist_df.sum(numeric_only=True) # 数値カラムを合計
                    total_row["Year"] = "通算" # 表示名
                    
                    # 率系の指標を再計算 (合計値から算出しないと平均の平均になってしまうため)
                    t_ab = total_row["is_ab"]
                    t_hit = total_row["is_hit"]
                    total_row["AVG"] = t_hit / t_ab if t_ab > 0 else 0.000
                    # (必要ならOPSなどもここで再計算できますが、今回は打率のみ再計算例とします)
                    
                    # DataFrame化して結合
                    df_total = pd.DataFrame([total_row])
                    hist_df = pd.concat([hist_df, df_total], ignore_index=True)
                    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
                    
                    # 表示フォーマット
                    hist_df["打率"] = hist_df["AVG"].map(lambda x: f"{x:.3f}")
                    
                    # 表示
                    st.dataframe(
                        hist_df[["Year", "打率", "is_ab", "is_hit", "is_hr", "打点", "盗塁"]]
                        .rename(columns={"Year":"年度", "is_ab":"打数", "is_hit":"安打", "is_hr":"本塁打"}),
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("打撃データなし")

        # --- Tab 3: 期間別ランキング ---
        with t3:
            st.markdown("####  🏆  期間別ランキング")
            mode = st.radio("集計期間", ["年度別", "月間", "直近3試合"], horizontal=True)
            
            df_tgt_b = df_b_calc.copy()
            df_tgt_p = df_p_calc.copy()
            
            if mode == "年度別":
                yr = st.selectbox("年度", years, key="rank_yr")
                df_tgt_b = df_tgt_b[df_tgt_b["Year"] == yr]
                df_tgt_p = df_tgt_p[df_tgt_p["Year"] == yr]
                def_ab = 10
            elif mode == "月間":
                df_tgt_b["Month"] = df_tgt_b["日付"].dt.strftime('%Y-%m')
                months = sorted(df_tgt_b["Month"].unique(), reverse=True)
                sel_m = st.selectbox("月", months)
                df_tgt_b = df_tgt_b[df_tgt_b["Month"] == sel_m]
                # 投手も同様に
                df_tgt_p["Month"] = df_tgt_p["日付"].dt.strftime('%Y-%m')
                df_tgt_p = df_tgt_p[df_tgt_p["Month"] == sel_m]
                def_ab = 3
            else:
                dates = sorted(df_tgt_b["日付"].unique(), reverse=True)[:3]
                df_tgt_b = df_tgt_b[df_tgt_b["日付"].isin(dates)]
                df_tgt_p = df_tgt_p[df_tgt_p["日付"].isin(dates)]
                st.caption(f"対象: {[d.strftime('%m/%d') for d in dates]}")
                def_ab = 1

            if not df_tgt_b.empty:
                ranked = get_ranking_df(df_tgt_b, ["選手名"], agg_rules_b)
                ranked = calc_advanced_stats(ranked)
                ranked["Display"] = ranked["選手名"]
                
                st.write("---")
                c_1, c_2, c_3 = st.columns(3)
                with c_1: show_top5("打率", ranked[ranked["is_ab"] >= def_ab], "AVG", "Display", "AVG", format_float=True)
                with c_2: show_top5("打点", ranked, "打点", "Display", "打点", suffix=" 点")
                with c_3: show_top5("OPS", ranked[ranked["is_ab"] >= def_ab], "OPS", "Display", "OPS", format_float=True)

        # --- Tab 4: 歴代記録 ---
        with t4:
            st.markdown("####  👑  歴代記録 (シーズン最高 & 通算)")
            rtype = st.radio("集計対象", ["シーズン最高", "通算"], horizontal=True)
            
            if rtype == "シーズン最高":
                r_df = get_ranking_df(df_b_calc, ["Year", "選手名"], agg_rules_b)
                r_df = calc_advanced_stats(r_df)
                r_df["Display"] = r_df["選手名"] + " (" + r_df["Year"] + ")"
                min_ab_r = 10
            else:
                r_df = get_ranking_df(df_b_calc, ["選手名"], agg_rules_b)
                r_df = calc_advanced_stats(r_df)
                r_df["Display"] = r_df["選手名"]
                min_ab_r = 30
            
            c_r1, c_r2, c_r3 = st.columns(3)
            with c_r1: show_top5("打率", r_df[r_df["is_ab"] >= min_ab_r], "AVG", "Display", "AVG", format_float=True)
            with c_r2: show_top5("本塁打", r_df, "is_hr", "Display", "is_hr", suffix=" 本")
            with c_r3: show_top5("打点", r_df, "打点", "Display", "打点", suffix=" 点")
            
    else:
        st.info("データがありません")