import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# --- ページ設定 ---
st.set_page_config(page_title="KAGURA スコア管理システム", layout="wide")

# スタイル設定
st.markdown("""
    <style>
    /* --- 1. 入力欄（セレクトボックス）の設定 --- */
    .stSelectbox div[data-baseweb="select"] {
        font-size: 18px !important;
        min-height: 40px !important;
    }
    .stButton button {
        width: 100%;
        padding: 0.2rem 0.2rem !important;
        font-size: 20px !important;
    }
    [data-testid="column"] {
        padding-left: 1px !important;
        padding-right: 1px !important;
    }
    .main { background-color: #f8f9fa; }

    /* --- 2. スコアボード（表）の設定 --- */
    [data-testid="stTable"] table {
        border-collapse: collapse !important;
        border: 2px solid #000000 !important;
    }
    [data-testid="stTable"] th, [data-testid="stTable"] td {
        border: 1px solid #444444 !important;
        font-size: 20px !important;
        padding: 10px !important;
        text-align: center !important;
        color: #000000 !important;
        font-weight: bold !important;
    }
    [data-testid="stTable"] th {
        background-color: #e0e0e0 !important;
        border-bottom: 2px solid #000000 !important;
    }
    
    /* --- 3. 指標（メトリクス）の装飾 --- */
    [data-testid="stMetricValue"] {
        font-size: 30px !important;
        font-weight: bold !important;
        color: #1e3a8a !important;
    }
    </style>
    """, unsafe_allow_html=True)

# スプレッドシート設定
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

all_players = [
    "相原一博", "荒木豊", "伊東太建", "石岡佳樹", "石原佳祐", "石田貴大", "内藤洋輔",
    "大高翼", "岡﨑英一", "開田凌空", "河野潤樹", "久保田剛志", "小野慎也", "小野拓朗",
    "佐藤蓮太", "清水智広", "杉山颯", "鈴木翔大", "塚田晴琉", "照屋航", "中尾建太",
    "永井雄太", "名執雅叶", "名執雅楽", "名執栄一", "名執冬雅", "野澤貫太", "日野拓実",
    "古屋翔", "望月駿", "山田大貴", "山中啓至", "山縣諒介", "渡辺羽", "渡邉竣太",
    "渡邉誠也", "水谷真智"
]
my_team_fixed = "KAGURA"
all_positions = ["", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
ground_list = ["小瀬スポーツ公園", "緑が丘スポーツ公園", "釜無川スポーツ公園", "飯田球場", "北麓公園", "その他"]

# --- データ読み込み（API制限対策: キャッシュ有効化） ---
def load_batting_data():
    try:
        # ttl="10m" にすることで、10分間はキャッシュを使用（アクセス回数を節約）
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl="10m")
        cols = ["打点", "盗塁", "得点", "位置", "グラウンド", "対戦相手", "試合種別"]
        for col in cols:
            if col not in data.columns: data[col] = 0 if col not in ["位置", "グラウンド", "対戦相手", "試合種別"] else ""
        
        # 日付型変換
        if "日付" in data.columns:
            data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
            
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])

def load_pitching_data():
    try:
        # ttl="10m" に設定
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl="10m")
        cols = ["アウト数", "球数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別"]
        for col in cols:
            if col not in data.columns: data[col] = 0 if col not in ["グラウンド", "対戦相手", "試合種別"] else ""
        
        # 日付型変換
        if "日付" in data.columns:
            data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
            
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別"])

df_batting = load_batting_data()
df_pitching = load_pitching_data()

# ==========================================
# サイドバー設定
# ==========================================
st.sidebar.header("⚙️ 試合設定")
match_type = st.sidebar.radio("試合種別", ["公式戦", "練習試合", "その他"], horizontal=True)
game_date = st.sidebar.date_input("試合日", datetime.date.today())
selected_date_str = game_date.strftime('%Y-%m-%d')
selected_ground_base = st.sidebar.selectbox("グラウンド", ground_list)
ground_name = st.sidebar.text_input("グラウンド名入力", value="グラウンド") if selected_ground_base == "その他" else selected_ground_base
opponents_list = ["ミッピーズ", "WISH", "NATSUME", "92ears", "球遊会", "プリティーボーイズ", "DREAM", "リベリオン", "KING STAR", "甲府市役所", "SQUAD", "その他"]
selected_opp = st.sidebar.selectbox("相手チーム", opponents_list)
opp_team = st.sidebar.text_input("相手名", value="相手チーム") if selected_opp == "その他" else selected_opp
kagura_order = st.sidebar.radio(f"攻守", ["先攻 (表)", "後攻 (裏)"], horizontal=True)

page = st.sidebar.radio("表示", ["🏠 試合速報", "📝 打撃成績入力", "🔥 投手成績入力", "🏆 チーム戦績", "📊 個人成績", "🔧 データ修正"])

# 日付フィルタ（データフレームの日付型と比較するため、dateオブジェクトのまま比較するか文字列変換する）
# ここでは日付型同士で比較
today_batting_df = df_batting[df_batting["日付"] == game_date]
today_pitching_df = df_pitching[df_pitching["日付"] == game_date]

# ==========================================
# スコアボード表示
# ==========================================
def show_scoreboard():
    st.markdown(f"### 📅 {selected_date_str} ({match_type}) &nbsp;&nbsp; 🏟️ {ground_name}")
    st.subheader(f"⚾ {my_team_fixed} vs {opp_team}")
    
    k_inning, opp_inning = [], []
    total_k, total_opp = 0, 0
    for i in range(1, 10):
        inn = f"{i}回"
        k_runs = today_batting_df[(today_batting_df["イニング"] == inn) & (today_batting_df["種別"] == "得点")].shape[0]
        opp_runs = int(today_pitching_df[today_pitching_df["イニング"] == inn]["失点"].sum())
        k_inning.append(str(k_runs) if not today_batting_df[today_batting_df["イニング"] == inn].empty else "")
        opp_inning.append(str(opp_runs) if not today_pitching_df[today_pitching_df["イニング"] == inn].empty else "")
        total_k += k_runs; total_opp += opp_runs

    hit_list = ["単打", "二塁打", "三塁打", "本塁打"]
    k_h = today_batting_df[today_batting_df["結果"].isin(hit_list)].shape[0]
    k_e = today_pitching_df[today_pitching_df["結果"] == "失策"].shape[0]
    opp_h = today_pitching_df[today_pitching_df["結果"].isin(hit_list)].shape[0]
    opp_e = today_batting_df[today_batting_df["結果"] == "失策"].shape[0]

    if kagura_order == "先攻 (表)":
        names = [my_team_fixed, opp_team]
        scores = [k_inning, opp_inning]
        R = [int(total_k), int(total_opp)]; H = [int(k_h), int(opp_h)]; E = [int(k_e), int(opp_e)]
    else:
        names = [opp_team, my_team_fixed]
        scores = [opp_inning, k_inning]
        R = [int(total_opp), int(total_k)]; H = [int(opp_h), int(k_h)]; E = [int(opp_e), int(k_e)]

    score_dict = {"チーム": names}
    for i in range(9): score_dict[str(i+1)] = [scores[0][i], scores[1][i]]
    score_dict.update({"R": R, "H": H, "E": E})
    st.table(pd.DataFrame(score_dict))

# ==========================================
# メイン表示処理
# ==========================================
if page == "🏠 試合速報":
    show_scoreboard()

elif page == "📝 打撃成績入力":
    show_scoreboard(); st.divider()
    
    # --- 登録処理用コールバック関数 ---
    def submit_batting():
        # Session State から値を取得
        # (スライサー入力値などのグローバル変数はこの関数の外側のスコープを参照します)
        current_starters = []
        for i in range(15):
            name = st.session_state.get(f"sn{i}")
            if name: current_starters.append(name)
        current_bench = st.session_state.get("bench_selection_key", [])
        
        # 重複チェック
        duplicates = set(current_starters) & set(current_bench)
        if duplicates:
            st.session_state["error_msg"] = f"⚠️ エラー: 以下の選手が『スタメン』と『ベンチ』の両方に登録されています。\n{', '.join(duplicates)}"
            return

        new_records = []
        error_logs = []
        
        # 現在の入力値（current_inning はウィジェットの値を取得できないため、session_state経由にするか、直前の値を参照）
        # ※selectboxはkeyを指定していないとコールバック内で値を取るのが難しいため、
        # ここではイニングのみ「直前の選択状態」を信頼します（再描画前なので変数は有効）
        
        for i in range(15):
            p_name = st.session_state.get(f"sn{i}")
            p_res = st.session_state.get(f"sr{i}")
            p_pos = st.session_state.get(f"sp{i}")
            p_rbi = st.session_state.get(f"si{i}")
            
            if p_name:
                if p_res == "---":
                    error_logs.append(f"・{i+1}番 {p_name}選手：結果が「---」のままです。")
                else:
                    rbi_val = int(p_rbi); run_val = 0; sb_val = 0; type_val = "打撃"
                    if p_res == "得点": run_val = 1; type_val = "得点"; rbi_val = 0
                    elif p_res == "盗塁": sb_val = 1; type_val = "盗塁"; rbi_val = 0
                    
                    new_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, 
                        "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": st.session_state.get("current_inn_key"), # keyを追加して取得
                        "選手名": p_name, "位置": p_pos,
                        "結果": p_res, "打点": rbi_val, "得点": run_val, "盗塁": sb_val, "種別": type_val
                    })

        if new_records:
            updated_df = pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True)
            conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
            st.cache_data.clear()
            st.session_state["success_msg"] = f"{len(new_records)} 件のデータを登録しました！"
            
            # ★ここでリセット（再描画前なのでエラーにならない）
            for i in range(15):
                st.session_state[f"sr{i}"] = "---"
                st.session_state[f"si{i}"] = 0
        
        elif error_logs:
            st.session_state["error_msg"] = "⚠️ 登録できませんでした。\n" + "\n".join(error_logs)
        else:
            st.session_state["warning_msg"] = "登録するデータがありません"

    # --- メッセージ表示 ---
    if "success_msg" in st.session_state:
        st.toast(st.session_state["success_msg"])
        del st.session_state["success_msg"]
    if "error_msg" in st.session_state:
        st.error(st.session_state["error_msg"])
        del st.session_state["error_msg"]
    if "warning_msg" in st.session_state:
        st.warning(st.session_state["warning_msg"])
        del st.session_state["warning_msg"]

    # --- UI描画 ---
    c_inn, c_btn, c_blank = st.columns([1.5, 1.5, 5])
    with c_inn:
        # keyを追加してコールバックから参照できるようにする
        current_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="current_inn_key")
        
        if not today_batting_df.empty:
            this_inn_data = today_batting_df[today_batting_df["イニング"] == current_inning]
            outs = this_inn_data[this_inn_data["結果"].isin(["三振", "凡退", "犠打", "走塁死", "盗塁死"])].shape[0]
        else:
            outs = 0
            
        if outs < 3:
            out_mark = "🔴 " * outs + "⚪ " * (3 - outs)
            st.markdown(f"<h3 style='margin:0; color:#333;'>{out_mark} {outs} Out</h3>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h3 style='margin:0; color:red;'>🔴 🔴 🔴 CHANGE</h3>", unsafe_allow_html=True)
    
    with c_btn:
        st.write("") 
        # on_click にコールバック関数を指定
        st.button("全データを登録", type="primary", on_click=submit_batting)

    col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]
    h_cols = st.columns(col_ratios)
    header_labels = ["打順", "守備", "氏名", "結果", "打点", "成績"]
    for col, label in zip(h_cols, header_labels):
        col.write(f"<p style='font-size:15px; font-weight:bold; margin-bottom:0;'>{label}</p>", unsafe_allow_html=True)

    batting_options = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]

    for i in range(15):
        c = st.columns(col_ratios)
        c[0].write(f"<p style='margin-top:8px;'>{i+1}</p>", unsafe_allow_html=True)
        c[1].selectbox(f"p{i}", all_positions, key=f"sp{i}", label_visibility="collapsed")
        name_v = c[2].selectbox(f"n{i}", [""] + all_players, index=0, key=f"sn{i}", label_visibility="collapsed")
        c[3].selectbox(f"r{i}", batting_options, key=f"sr{i}", label_visibility="collapsed")
        c[4].selectbox(f"i{i}", [0, 1, 2, 3, 4], key=f"si{i}", label_visibility="collapsed")
        if name_v:
            p_res = today_batting_df[today_batting_df["選手名"] == name_v]["結果"].tolist()
            c[5].info(" ".join(p_res[-4:]) if p_res else "-")
        else:
            c[5].write("")
            
    st.divider()

    with st.expander("🚌 ベンチ入りメンバーを選択", expanded=True):
        bench_selection = st.multiselect(
            "ベンチメンバーを選んでください（スタメンと重複するとエラーになります）",
            all_players,
            key="bench_selection_key"
        )

elif page == "🔥 投手成績入力":
    show_scoreboard(); st.divider()
    
    # --- 登録処理用コールバック関数 ---
    def submit_pitching():
        # Session State から値を取得
        p_name = st.session_state.get("pit_name")
        p_inning = st.session_state.get("pit_inn")
        p_res = st.session_state.get("pit_res")
        p_count = st.session_state.get("pit_count")
        pruns = st.session_state.get("pit_runs")
        per = st.session_state.get("pit_er")
        
        if p_name:
            out_inc = 1 if p_res in ["三振", "凡退", "犠打", "走塁死", "盗塁死", "牽制死"] else 0
            
            new_p = pd.DataFrame([{
                "日付": selected_date_str, "グラウンド": ground_name, 
                "対戦相手": opp_team, "試合種別": match_type, 
                "イニング": p_inning, "投手名": p_name, "結果": p_res, "球数": int(p_count), "アウト数": out_inc, "失点": int(pruns), "自責点": int(per)
            }])
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, new_p], ignore_index=True))
            st.cache_data.clear()
            st.session_state["success_msg"] = "登録しました！"
            
            # ★ここでリセット（これがやりたかった処理）
            st.session_state["pit_res"] = "凡退"
            st.session_state["pit_runs"] = 0
            st.session_state["pit_er"] = 0
            # 名前(pit_name)はリセットしないので、そのまま残ります
        else:
            st.session_state["error_msg"] = "⚠️ 投手名を選択してください"

    # --- メッセージ表示 ---
    if "success_msg" in st.session_state:
        st.toast(st.session_state["success_msg"])
        del st.session_state["success_msg"]
    if "error_msg" in st.session_state:
        st.error(st.session_state["error_msg"])
        del st.session_state["error_msg"]

    # --- UI描画 ---
    c_form, c_info = st.columns([2, 1])
    
    with c_form:
        p_name = st.selectbox("投手名", [""] + all_players, index=0, key="pit_name")
        
        ci1, ci2 = st.columns([1, 1])
        with ci1:
            p_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="pit_inn")
        with ci2:
            if not today_pitching_df.empty:
                # 注: ここは描画時点のイニングを使うため、selectboxの戻り値を参照する形でもOKですが、
                # コールバックとの整合性のため session_state があればそちらを優先してもよい
                current_inn_display = st.session_state.get("pit_inn", p_inning)
                this_inn_p = today_pitching_df[today_pitching_df["イニング"] == current_inn_display]
                outs_p = int(this_inn_p["アウト数"].sum())
            else:
                outs_p = 0
            st.write("") 
            if outs_p < 3:
                out_mark_p = "🔴 " * outs_p + "⚪ " * (3 - outs_p)
                st.markdown(f"<h4 style='margin:0; color:#333;'>{out_mark_p} {outs_p} Out</h4>", unsafe_allow_html=True)
            else:
                st.markdown(f"<h4 style='margin:0; color:red;'>🔴 🔴 🔴 CHANGE</h4>", unsafe_allow_html=True)

        p_res = st.radio("結果", ["凡退", "三振", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "失策", "犠打", "走塁死", "盗塁死", "牽制死"], horizontal=True, key="pit_res")
        cp, cr, ce = st.columns(3)
        p_count = cp.number_input("球数", 1, 15, 4, key="pit_count")
        pruns = cr.selectbox("失点", [0,1,2,3,4], key="pit_runs")
        per = ce.selectbox("自責", [0,1,2,3,4], key="pit_er")
        
        # on_click にコールバックを指定
        st.button("登録", type="primary", on_click=submit_pitching)

elif page == "🏆 チーム戦績":
    st.title("🏆 KAGURA チーム戦績")
    
    if not df_batting.empty and not df_pitching.empty:
        # 年度選択（日付型から年を抽出）
        # 日付型になっているので .dt.year で取得
        df_batting["Year"] = pd.to_datetime(df_batting["日付"]).dt.year.astype(str)
        df_pitching["Year"] = pd.to_datetime(df_pitching["日付"]).dt.year.astype(str)
        
        all_years = sorted(list(set(df_batting["Year"].unique()) | set(df_pitching["Year"].unique())), reverse=True)
        
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
                    "スコア": f"{int(my_score)} - {int(opp_score)}", "勝敗": f"{res_icon} {res}"
                })

            games_count = wins + loses + draws
            win_rate = wins / (wins + loses) if (wins + loses) > 0 else 0.000
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("試合数", f"{games_count}")
            m2.metric("勝利", f"{wins}")
            m3.metric("敗北", f"{loses}")
            m4.metric("引分", f"{draws}")
            m5.metric("勝率", f"{win_rate:.3f}")
            
            st.divider()
            st.subheader("📜 試合履歴")
            df_res = pd.DataFrame(game_results)
            st.dataframe(df_res, use_container_width=True, hide_index=True)
        else:
            st.info("条件に一致する試合がありません。")
    else:
        st.info("データがありません。")

elif page == "📊 個人成績":
    st.title("📊 個人通算成績")
    
    # フィルタ UI
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

    t_bat, t_pit = st.tabs(["打撃部門", "投手部門"])
    
    with t_bat:
        if not df_b_target.empty:
            batting_stats = []
            ab_res = ["単打", "二塁打", "三塁打", "本塁打", "三振", "凡退", "失策", "走塁死"]
            pa_res = ab_res + ["四球", "死球", "犠打"]
            
            for player in all_players:
                p_data = df_b_target[df_b_target["選手名"] == player]
                if p_data.empty: continue
                
                latest_pos = p_data[p_data["位置"] != ""]["位置"].tail(1).values
                pos_display = latest_pos[0] if len(latest_pos) > 0 else "-"
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
                    "守備": pos_display, "氏名": player, "打率": avg, "OPS": ops,
                    "本塁打": hrs, "打点": int(rbi), "安打": hits, 
                    "二塁打": doubles, "三塁打": triples, "出塁率": obp, 
                    "打席": pa, "打数": ab, "盗塁": int(sb), "四死球": bbs + hbps
                })
            
            if batting_stats:
                df_res = pd.DataFrame(batting_stats).sort_values("打率", ascending=False)
                for col in ["打率", "OPS", "出塁率"]:
                    df_res[col] = df_res[col].map(lambda x: f"{x:.3f}")
                st.dataframe(df_res, use_container_width=True, hide_index=True)
        else:
            st.info("条件に一致する打撃データがありません。")

    with t_pit:
        if not df_p_target.empty:
            pitch_stats = []
            for p in all_players:
                pd_p = df_p_target[df_p_target["投手名"] == p]
                if pd_p.empty: continue
                outs = pd_p["アウト数"].sum()
                er = pd_p["自責点"].sum()
                era = (er * 9) / (outs / 3) if outs > 0 else 0.0
                pitch_stats.append({"氏名": p, "防御率": era, "投球回": f"{outs//3}.{outs%3}", "三振": pd_p[pd_p["結果"] == "三振"].shape[0], "失点": int(pd_p["失点"].sum())})
            if pitch_stats:
                df_p_res = pd.DataFrame(pitch_stats).sort_values("防御率")
                df_p_res["防御率"] = df_p_res["防御率"].map(lambda x: f"{x:.2f}")
                st.dataframe(df_p_res, use_container_width=True, hide_index=True)
        else:
            st.info("条件に一致する投手データがありません。")

elif page == "🔧 データ修正":
    st.title("🔧 データ修正")
    st.info(
        """
        **【データの削除・修正方法】**
        - **削除**: 行の左端をクリックして選択し、`Delete` キーで削除。
        - **修正**: セルをダブルクリックして修正（すべての項目が選択式になっています）。
        - **日付**: カレンダーから選択できます。
        - **数値**: 上下キーまたは直接入力で変更できます。
        - **確定**: 編集後は必ず下の **「保存」ボタン** を押してください。
        """
    )

    t1, t2 = st.tabs(["打撃成績", "投手成績"])
    
    # 共通の選択肢定義（エラー対策済み）
    default_innings = [f"{i}回" for i in range(1, 10)]
    
    existing_opps_b = list(df_batting["対戦相手"].unique()) if "対戦相手" in df_batting.columns else []
    existing_opps_p = list(df_pitching["対戦相手"].unique()) if "対戦相手" in df_pitching.columns else []
    raw_opps_list = opponents_list + existing_opps_b + existing_opps_p
    valid_opps = {str(x) for x in raw_opps_list if str(x) != "nan" and x is not None and str(x) != ""}
    merged_opps = sorted(list(valid_opps))

    existing_grounds_b = list(df_batting["グラウンド"].unique()) if "グラウンド" in df_batting.columns else []
    existing_grounds_p = list(df_pitching["グラウンド"].unique()) if "グラウンド" in df_pitching.columns else []
    raw_grounds_list = ground_list + existing_grounds_b + existing_grounds_p
    valid_grounds = {str(x) for x in raw_grounds_list if str(x) != "nan" and x is not None and str(x) != ""}
    merged_grounds = sorted(list(valid_grounds))

    batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]
    pitching_results = ["凡退", "三振", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "失策", "犠打", "走塁死", "盗塁死", "牽制死"]
    
    match_types = ["公式戦", "練習試合", "その他"]

    with t1:
        st.write("▼ 打撃データの編集")
        ed_b = st.data_editor(
            df_batting,
            column_config={
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD", required=True),
                "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=merged_grounds, required=True),
                "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=merged_opps, required=True),
                "試合種別": st.column_config.SelectboxColumn("試合種別", options=match_types, required=True),
                "イニング": st.column_config.SelectboxColumn("イニング", options=default_innings, required=True),
                "選手名": st.column_config.SelectboxColumn("選手名", options=all_players, required=True),
                "位置": st.column_config.SelectboxColumn("位置", options=all_positions),
                "結果": st.column_config.SelectboxColumn("結果", options=batting_results, required=True),
                "打点": st.column_config.NumberColumn("打点", min_value=0, max_value=10, step=1),
                "得点": st.column_config.NumberColumn("得点", min_value=0, max_value=10, step=1),
                "盗塁": st.column_config.NumberColumn("盗塁", min_value=0, max_value=10, step=1),
                "種別": st.column_config.SelectboxColumn("種別", options=["打撃", "得点", "盗塁"]),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="editor_batting"
        )
        
        if st.button("打撃データを保存", type="primary"):
            conn.update(spreadsheet=SPREADSHEET_URL, data=ed_b)
            # ★修正：更新後にキャッシュクリア
            st.cache_data.clear()
            st.success("✅ 打撃データを更新しました！")
            st.rerun()

    with t2:
        st.write("▼ 投手データの編集")
        ed_p = st.data_editor(
            df_pitching,
            column_config={
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD", required=True),
                "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=merged_grounds, required=True),
                "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=merged_opps, required=True),
                "試合種別": st.column_config.SelectboxColumn("試合種別", options=match_types, required=True),
                "イニング": st.column_config.SelectboxColumn("イニング", options=default_innings, required=True),
                "投手名": st.column_config.SelectboxColumn("投手名", options=all_players, required=True),
                "結果": st.column_config.SelectboxColumn("結果", options=pitching_results, required=True),
                "球数": st.column_config.NumberColumn("球数", min_value=0, step=1),
                "アウト数": st.column_config.NumberColumn("アウト数", min_value=0, max_value=1, step=1, help="1=アウト取得, 0=なし"),
                "失点": st.column_config.NumberColumn("失点", min_value=0, max_value=10, step=1),
                "自責点": st.column_config.NumberColumn("自責点", min_value=0, max_value=10, step=1),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="editor_pitching"
        )
        
        if st.button("投手データを保存", type="primary"):
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=ed_p)
            # ★修正：更新後にキャッシュクリア
            st.cache_data.clear()
            st.success("✅ 投手データを更新しました！")
            st.rerun()