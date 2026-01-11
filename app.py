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
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl="10m")
        cols = ["打点", "盗塁", "得点", "位置", "グラウンド", "対戦相手", "試合種別"]
        for col in cols:
            if col not in data.columns: data[col] = 0 if col not in ["位置", "グラウンド", "対戦相手", "試合種別"] else ""
        
        if "日付" in data.columns:
            data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
            
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])

def load_pitching_data():
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl="10m")
        # "処理野手" を追加
        cols = ["アウト数", "球数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "処理野手"]
        for col in cols:
            if col not in data.columns: 
                # 文字列項目は空文字、数値は0で初期化
                if col in ["グラウンド", "対戦相手", "試合種別", "処理野手"]:
                    data[col] = ""
                else:
                    data[col] = 0
        
        if "日付" in data.columns:
            data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
            
        return data.dropna(how="all")
    except:
        # 初期化カラムにも "処理野手" を追加
        return pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "処理野手", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別"])

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

page = st.sidebar.radio("表示", ["🏠 打撃成績入力", "🔥 投手成績入力", "🏆 チーム戦績", "📊 個人成績", "🔧 データ修正"])

# 今日の試合データ（入力用）
today_batting_df = df_batting[df_batting["日付"] == game_date]
today_pitching_df = df_pitching[df_pitching["日付"] == game_date]

# ==========================================
# スコアボード表示ロジック（共通関数化）
# ==========================================
def render_scoreboard(b_df, p_df, date_txt, m_type, g_name, opp_name, is_top_first=True):
    """
    任意のデータフレームを受け取ってスコアボードを描画する関数
    is_top_first: TrueならKAGURAが先攻(表)、Falseなら後攻(裏)
    """
    st.markdown(f"### 📅 {date_txt} ({m_type}) &nbsp;&nbsp; 🏟️ {g_name}")
    st.subheader(f"⚾ {my_team_fixed} vs {opp_name}")
    
    k_inning, opp_inning = [], []
    total_k, total_opp = 0, 0
    
    # 9回まで計算
    for i in range(1, 10):
        inn = f"{i}回"
        k_runs = b_df[(b_df["イニング"] == inn) & (b_df["種別"] == "得点")].shape[0]
        opp_runs = int(p_df[p_df["イニング"] == inn]["失点"].sum())
        
        # データが存在するイニングだけ数字を表示、なければ空文字
        k_exists = not b_df[b_df["イニング"] == inn].empty
        opp_exists = not p_df[p_df["イニング"] == inn].empty
        
        k_inning.append(str(k_runs) if k_exists else "")
        opp_inning.append(str(opp_runs) if opp_exists else "")
        
        total_k += k_runs
        total_opp += opp_runs

    hit_list = ["単打", "二塁打", "三塁打", "本塁打"]
    k_h = b_df[b_df["結果"].isin(hit_list)].shape[0]
    k_e = p_df[p_df["結果"] == "失策"].shape[0]
    opp_h = p_df[p_df["結果"].isin(hit_list)].shape[0]
    opp_e = b_df[b_df["結果"] == "失策"].shape[0]

    # KAGURAが先攻か後攻かで表示順を入れ替え
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
# メイン表示処理
# ==========================================
if page == "🏠 打撃成績入力":
    is_kagura_top = (kagura_order == "先攻 (表)")
    
    # スコアボード表示
    render_scoreboard(today_batting_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()
    
    # --- 登録処理用コールバック関数（ここから関数の中身） ---
    def submit_batting():
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
        
        for i in range(15):
            p_name = st.session_state.get(f"sn{i}")
            p_res = st.session_state.get(f"sr{i}")
            p_pos = st.session_state.get(f"sp{i}")
            p_rbi = st.session_state.get(f"si{i}")
            
            # 選手名があれば登録対象にする
            if p_name:
                rbi_val = int(p_rbi)
                run_val = 0
                sb_val = 0
                type_val = "打撃" 
                
                if p_res == "得点": 
                    run_val = 1; type_val = "得点"; rbi_val = 0
                elif p_res == "盗塁": 
                    sb_val = 1; type_val = "盗塁"; rbi_val = 0
                
                new_records.append({
                    "日付": selected_date_str, "グラウンド": ground_name, 
                    "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": st.session_state.get("current_inn_key"),
                    "選手名": p_name, "位置": p_pos,
                    "結果": p_res, "打点": rbi_val, "得点": run_val, "盗塁": sb_val, "種別": type_val
                })

        if new_records:
            updated_df = pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True)
            conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
            st.cache_data.clear()
            st.session_state["success_msg"] = f"{len(new_records)} 件のデータを登録しました（メンバー確定）"
            
            # 現在のオーダーをバックアップ保存
            saved_lineup = {}
            for i in range(15):
                saved_lineup[f"name_{i}"] = st.session_state.get(f"sn{i}")
                saved_lineup[f"pos_{i}"] = st.session_state.get(f"sp{i}")
            st.session_state["saved_lineup"] = saved_lineup
            
            # 結果入力だけリセット
            for i in range(15):
                st.session_state[f"sr{i}"] = "---"
                st.session_state[f"si{i}"] = 0
        
        else:
            st.session_state["warning_msg"] = "登録するデータ（選手名）がありません"

    # --- メッセージ表示（ここから関数から抜けてメインのインデントに戻る） ---
    if "success_msg" in st.session_state:
        st.toast(st.session_state["success_msg"])
        del st.session_state["success_msg"]
    if "error_msg" in st.session_state:
        st.error(st.session_state["error_msg"])
        del st.session_state["error_msg"]
    if "warning_msg" in st.session_state:
        st.warning(st.session_state["warning_msg"])
        del st.session_state["warning_msg"]

    # ==========================================
    # ▼ レイアウト作成（必ず関数の外に書く）
    # ==========================================
    
    # 1. 登録ボタン
    st.button("登録", type="primary", on_click=submit_batting, use_container_width=True)

    st.write("") 

    # 2. イニング選択とアウトカウント
    c_inn, c_outs, c_blank = st.columns([1.5, 2.0, 4.0])
    
    with c_inn:
        current_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="current_inn_key")
        
    with c_outs:
        if not today_batting_df.empty:
            this_inn_data = today_batting_df[today_batting_df["イニング"] == current_inning]
            outs = this_inn_data[this_inn_data["結果"].isin(["三振", "凡退", "犠打", "走塁死", "盗塁死", "牽制死"])].shape[0]
        else:
            outs = 0
            
        st.write("") 
        st.write("") 
        
        if outs < 3:
            out_mark = "🔴 " * outs + "⚪ " * (3 - outs)
            st.markdown(f"<h4 style='margin:0; color:#333; line-height:1.2;'>{out_mark} Out</h4>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h4 style='margin:0; color:red; line-height:1.2;'>🔴 🔴 🔴 CHANGE</h4>", unsafe_allow_html=True)
    
    # 3. 入力フォームヘッダー
    col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]
    h_cols = st.columns(col_ratios)
    header_labels = ["打順", "守備", "氏名", "結果", "打点", "成績"]
    for col, label in zip(h_cols, header_labels):
        col.write(f"<p style='font-size:15px; font-weight:bold; margin-bottom:0;'>{label}</p>", unsafe_allow_html=True)

    # 選択肢リスト定義
    batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]

    # 4. 入力フォームループ
    for i in range(15):
        c = st.columns(col_ratios)
        c[0].write(f"<p style='margin-top:8px;'>{i+1}</p>", unsafe_allow_html=True)
        
        # 保存されたオーダーの初期値設定
        default_pos_ix = 0
        default_name_ix = 0
        
        if "saved_lineup" in st.session_state:
            saved_data = st.session_state["saved_lineup"]
            
            s_pos = saved_data.get(f"pos_{i}")
            if s_pos in all_positions:
                default_pos_ix = all_positions.index(s_pos)
                
            s_name = saved_data.get(f"name_{i}")
            player_list = [""] + all_players
            if s_name in player_list:
                default_name_ix = player_list.index(s_name)

        c[1].selectbox(f"p{i}", all_positions, index=default_pos_ix, key=f"sp{i}", label_visibility="collapsed")
        name_v = c[2].selectbox(f"n{i}", [""] + all_players, index=default_name_ix, key=f"sn{i}", label_visibility="collapsed")
        c[3].selectbox(f"r{i}", batting_results, key=f"sr{i}", label_visibility="collapsed")
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
    is_kagura_top = (kagura_order == "先攻 (表)")
    render_scoreboard(today_batting_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()
    
    # --- 登録処理用コールバック関数 ---
    def submit_pitching():
        # Session State から値を取得
        p_name = st.session_state.get("pit_name")
        p_inning = st.session_state.get("pit_inn")
        p_res = st.session_state.get("pit_res")
        p_count = st.session_state.get("pit_count")
        pruns = st.session_state.get("pit_runs")
        per = st.session_state.get("pit_er")
        
        # 画面で選ばれた「鈴木 (遊)」のような文字列を取得
        p_fielder_raw = st.session_state.get("pit_fielder", "")
        p_fielder_name = ""

        if p_name:
            # アウトカウントが増えるイベント
            out_inc = 1 if p_res in ["三振", "凡退", "犠打", "走塁死", "盗塁死", "牽制死"] else 0
            
            # 野手名を記録する対象イベント
            target_events = ["凡退", "失策", "犠打", "走塁死", "牽制死", "盗塁死"]
            
            # 対象イベント かつ 選択値が空でない場合、名前を抽出
            if p_res in target_events and p_fielder_raw:
                if "(" in p_fielder_raw:
                    p_fielder_name = p_fielder_raw.split(" (")[0]
                else:
                    p_fielder_name = p_fielder_raw 
            
            # それ以外なら空文字
            if p_res not in target_events:
                p_fielder_name = ""

            new_p = pd.DataFrame([{
                "日付": selected_date_str, "グラウンド": ground_name, 
                "対戦相手": opp_team, "試合種別": match_type, 
                "イニング": p_inning, "投手名": p_name, 
                "結果": p_res, "処理野手": p_fielder_name, 
                "球数": int(p_count), "アウト数": out_inc, "失点": int(pruns), "自責点": int(per)
            }])
            
            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, new_p], ignore_index=True))
            st.cache_data.clear()
            st.session_state["success_msg"] = "登録しました！"
            
            # リセット処理（結果等は初期値に戻す）
            st.session_state["pit_res"] = "凡退"
            st.session_state["pit_runs"] = 0
            st.session_state["pit_er"] = 0
            
        else:
            st.session_state["error_msg"] = "⚠️ 投手名を選択してください"

    # --- メッセージ表示 ---
    if "success_msg" in st.session_state:
        st.toast(st.session_state["success_msg"])
        del st.session_state["success_msg"]
    if "error_msg" in st.session_state:
        st.error(st.session_state["error_msg"])
        del st.session_state["error_msg"]

    # ==========================================
    # ▼ レイアウト（ここから画面を作ります）
    # ==========================================

    # 1. 登録ボタン
    st.button("登録", type="primary", on_click=submit_pitching, use_container_width=True)
    st.write("") 

    # 2. イニングとアウトカウント
    c_inn, c_outs, c_blank = st.columns([1.5, 2.0, 4.0])
    with c_inn:
        p_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="pit_inn")
    
    with c_outs:
        if not today_pitching_df.empty:
            current_inn_display = st.session_state.get("pit_inn", p_inning)
            this_inn_p = today_pitching_df[today_pitching_df["イニング"] == current_inn_display]
            outs_p = int(this_inn_p["アウト数"].sum())
        else:
            outs_p = 0
            
        st.write("") 
        st.write("") 
        if outs_p < 3:
            out_mark_p = "🔴 " * outs_p + "⚪ " * (3 - outs_p)
            st.markdown(f"<h4 style='margin:0; color:#333; line-height:1.2;'>{out_mark_p} Out</h4>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h4 style='margin:0; color:red; line-height:1.2;'>🔴 🔴 🔴 CHANGE</h4>", unsafe_allow_html=True)

    st.divider()
    
    # 3. 投手名（スタメンの「投」を自動反映するロジック）
    
    # 選択肢リスト
    p_list = [""] + all_players
    default_p_index = 0
    
    # (A) すでにこのページで投手が選択されている場合（リリーフへの交代後など）はそれを維持
    current_val = st.session_state.get("pit_name")
    if current_val and current_val in p_list:
        default_p_index = p_list.index(current_val)
        
    # (B) まだ選択されていない(空欄)場合、打撃入力で保存された「投」の選手を探す
    elif "saved_lineup" in st.session_state:
        saved_data = st.session_state["saved_lineup"]
        for i in range(15):
            # 守備位置が「投」のデータを探す
            if saved_data.get(f"pos_{i}") == "投":
                starter_name = saved_data.get(f"name_{i}")
                if starter_name in p_list:
                    default_p_index = p_list.index(starter_name)
                break

    # 計算した index を初期値として設定
    p_name = st.selectbox("投手名", p_list, index=default_p_index, key="pit_name")
    
    # 4. 結果（★重要：これを先に書かないとエラーになります）
    p_res = st.radio("結果", ["凡退", "三振", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "失策", "犠打", "走塁死", "盗塁死", "牽制死"], horizontal=True, key="pit_res")
    
    # 5. 守備者選択（ここを修正：saved_lineup を優先参照する）
    target_events = ["凡退", "失策", "犠打", "走塁死", "牽制死", "盗塁死"]
    
    if p_res in target_events:
        current_fielders = []
        
        # (A) 現在選択中の投手を入れる
        current_p_name = st.session_state.get("pit_name", "")
        if current_p_name:
            current_fielders.append(f"{current_p_name} (投)")
        
        # (B) 直近の「登録」内容（saved_lineup）がある場合、それを最優先で使う
        # これにより、スタメン変更後に古い選手が出なくなります
        if "saved_lineup" in st.session_state:
            saved_data = st.session_state["saved_lineup"]
            for i in range(15):
                nm = saved_data.get(f"name_{i}")
                pos = saved_data.get(f"pos_{i}")
                
                # 名前があり、かつ有効な守備位置（投以外）の場合
                if nm and pos and pos not in ["", "DH", "代打", "投"]:
                    current_fielders.append(f"{nm} ({pos})")
                    
        # (C) もし saved_lineup がない（ブラウザ更新後など）場合は、既存データの最新を参照（バックアップ）
        elif not today_batting_df.empty:
            valid_pos = ["捕", "一", "二", "三", "遊", "左", "中", "右"]
            # 今日のデータから選手リストを作成
            df_fielders = today_batting_df[
                (today_batting_df["位置"].isin(valid_pos)) & 
                (today_batting_df["選手名"] != "")
            ][["選手名", "位置"]].drop_duplicates()
            
            for _, row in df_fielders.iterrows():
                if row["位置"] != "投":
                    current_fielders.append(f"{row['選手名']} ({row['位置']})")
        
        # 重複削除（リスト順序を保持）
        seen = set()
        current_fielders = [x for x in current_fielders if not (x in seen or seen.add(x))]
        
        # データなしの場合の表示
        if not current_fielders:
             current_fielders = ["(打撃画面でスタメン登録してください)"] + ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

        if p_res == "失策":
            st.info("👇 誰がエラーしましたか？")
        else:
            st.info("👇 誰が処理しましたか？")
            
        st.selectbox("対象選手", current_fielders, key="pit_fielder")

    # 6. その他の入力（球数など）
    cp, cr, ce = st.columns(3)
    p_count = cp.number_input("球数", 1, 15, 4, key="pit_count")
    pruns = cr.selectbox("失点", [0,1,2,3,4], key="pit_runs")
    per = ce.selectbox("自責", [0,1,2,3,4], key="pit_er")

elif page == "🏆 チーム戦績":
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

        # --- 試合一覧の生成 ---
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
                    "K得点": int(my_score), "相手得点": int(opp_score) # 内部用に保持
                })

            # チーム成績メトリクス
            games_count = wins + loses + draws
            win_rate = wins / (wins + loses) if (wins + loses) > 0 else 0.000
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("試合数", f"{games_count}")
            m2.metric("勝利", f"{wins}")
            m3.metric("敗北", f"{loses}")
            m4.metric("引分", f"{draws}")
            m5.metric("勝率", f"{win_rate:.3f}")
            
            st.divider()
            
            # --- 試合選択用データフレーム（ここからが修正の核） ---
            st.subheader("📜 試合履歴 (行をクリックで詳細表示)")
            df_res = pd.DataFrame(game_results)
            
            # 選択イベント付きデータフレームを表示
            event = st.dataframe(
                df_res.drop(columns=["K得点", "相手得点"]), # 表示用には不要な列を隠す
                use_container_width=True, 
                hide_index=True,
                on_select="rerun", # 選択したら再実行
                selection_mode="single-row" # 1行だけ選択
            )

            # --- 詳細表示ロジック（ここから書き換え） ---
            if len(event.selection.rows) > 0:
                selected_index = event.selection.rows[0]
                selected_data = df_res.iloc[selected_index]
                
                target_date = selected_data["日付"]
                target_opp = selected_data["対戦相手"]
                
                # 該当試合のデータを抽出
                detail_b = df_batting[(df_batting["日付"] == target_date) & (df_batting["対戦相手"] == target_opp)]
                detail_p = df_pitching[(df_pitching["日付"] == target_date) & (df_pitching["対戦相手"] == target_opp)]
                
                d_date_str = target_date.strftime('%Y-%m-%d')
                d_m_type = selected_data["種別"]
                d_ground = selected_data["会場"]
                
                st.divider()
                st.markdown(f"## 🔎 試合詳細: vs {target_opp}")
                
                # 1. スコアボード（既存のまま）
                # 過去データの先攻後攻は情報がないため仮で is_top_first=False としています
                render_scoreboard(detail_b, detail_p, d_date_str, d_m_type, d_ground, target_opp, is_top_first=False)
                
                st.write("")
                
                # --- タブで表示分け ---
                tab_d_bat, tab_d_pit = st.tabs(["📝 打撃成績 (スコアブック)", "🔥 投手成績 (登板内容)"])
                
               # ▼▼▼ 2. 打撃成績：オーダー表形式（最低5打席分を表示） ▼▼▼
                with tab_d_bat:
                    if not detail_b.empty:
                        # 選手ごとにデータをまとめる
                        players_ordered = detail_b["選手名"].unique()
                        
                        batting_rows = []
                        max_at_bats = 0 
                        
                        # 表示したい打撃結果（盗塁などは除外して、純粋な打席結果のみ）
                        display_targets = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策"]

                        for i, p_name in enumerate(players_ordered):
                            p_rows = detail_b[detail_b["選手名"] == p_name]
                            
                            # 最新の守備位置
                            pos = p_rows.iloc[-1]["位置"] if "位置" in p_rows.columns else "-"
                            
                            # 結果リストを作成（打撃結果のみに絞り込む）
                            results = p_rows[p_rows["結果"].isin(display_targets)]["結果"].tolist()
                            
                            if len(results) > max_at_bats:
                                max_at_bats = len(results)
                                
                            # 集計値
                            rbi = pd.to_numeric(p_rows["打点"], errors='coerce').sum()
                            run = pd.to_numeric(p_rows["得点"], errors='coerce').sum()
                            sb = pd.to_numeric(p_rows["盗塁"], errors='coerce').sum()
                            
                            # 安打数
                            hits = p_rows[p_rows["結果"].isin(["単打", "二塁打", "三塁打", "本塁打"])].shape[0]
                            
                            row_data = {
                                "打順": i + 1,
                                "守備": pos,
                                "選手名": p_name,
                                "打点": rbi,
                                "得点": run,
                                "安打": hits,
                                "盗塁": sb,
                                "results": results
                            }
                            batting_rows.append(row_data)
                        
                        # データフレーム化
                        df_bat_formatted = pd.DataFrame(batting_rows)
                        
                        # 【修正点】最低でも「第5打席」までは列を作る（それ以上ある場合は拡張）
                        final_max_cols = max(5, max_at_bats)
                        
                        for j in range(final_max_cols):
                            col_name = f"第{j+1}打席"
                            # データがあれば入れ、なければ空文字
                            df_bat_formatted[col_name] = df_bat_formatted["results"].apply(lambda x: x[j] if j < len(x) else "")
                        
                        # 表示カラム整理
                        cols_order = ["打順", "守備", "選手名"] + [f"第{j+1}打席" for j in range(final_max_cols)] + ["安打", "打点", "得点", "盗塁"]
                        df_final_b = df_bat_formatted.drop(columns=["results"])[cols_order]
                        
                        st.dataframe(df_final_b, use_container_width=True, hide_index=True)
                    else:
                        st.info("打撃データがありません")

                # ▼▼▼ 3. 投手成績：個人別集計 ▼▼▼
                with tab_d_pit:
                    if not detail_p.empty:
                        pitchers = detail_p["投手名"].unique()
                        p_rows = []
                        
                        for p_name in pitchers:
                            p_data = detail_p[detail_p["投手名"] == p_name]
                            
                            # 集計
                            outs = p_data["アウト数"].sum()
                            balls = p_data["球数"].sum()
                            runs = p_data["失点"].sum()
                            er = p_data["自責点"].sum()
                            
                            # 被安打や三振、四死球の数
                            hits = p_data[p_data["結果"].isin(["単打", "二塁打", "三塁打", "本塁打"])].shape[0]
                            ks = p_data[p_data["結果"] == "三振"].shape[0]
                            bbs = p_data[p_data["結果"].isin(["四球", "死球"])].shape[0]
                            
                            # 投球回表記 (例: 4回1/3 → 4.1)
                            ip_display = f"{int(outs // 3)}"
                            if outs % 3 != 0:
                                ip_display += f".{int(outs % 3)}"
                            
                            p_rows.append({
                                "投手名": p_name,
                                "投球回": ip_display,
                                "球数": int(balls),
                                "被安打": hits,
                                "奪三振": ks,
                                "四死球": bbs,
                                "失点": int(runs),
                                "自責点": int(er)
                            })
                            
                        df_final_p = pd.DataFrame(p_rows)
                        st.dataframe(df_final_p, use_container_width=True, hide_index=True)
                    else:
                        st.info("投手データがありません")
            
            else:
                st.info("上の表から試合を選択（クリック）すると、ここに詳細が表示されます。")

elif page == "📊 個人成績":
    st.title("📊 個人通算成績")
    
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
    # 2. タブの作成（ここで t_fld を定義します）
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

    # ----------------------------------------------------
    # (B) 投手部門
    # ----------------------------------------------------
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

    # ----------------------------------------------------
    # (C) 守備部門（ここが集計ロジックです）
    # ----------------------------------------------------
    with t_fld:
        st.write("※ 凡退・犠打・走塁死などの処理数と、失策数を集計します")
        
        # 必要な列が存在し、データがあるか確認
        if not df_p_target.empty and "処理野手" in df_p_target.columns:
            # 処理野手が記録されているデータだけ抽出
            fld_data = df_p_target[df_p_target["処理野手"] != ""]
            
            if not fld_data.empty:
                # 1. クロス集計を作成（行：野手、列：結果）
                stats = pd.crosstab(fld_data["処理野手"], fld_data["結果"])
                
                # 2. 列の整理（存在しない列がある場合に備えて0埋め）
                target_cols = ["凡退", "犠打", "失策", "走塁死", "牽制死", "盗塁死"]
                for col in target_cols:
                    if col not in stats.columns:
                        stats[col] = 0
                
                # 3. 合算指標を作成
                #    失策以外のすべてを「刺殺・補殺（アウト処理）」として合算
                out_cols = [c for c in target_cols if c != "失策"]
                
                stats["刺殺・補殺"] = stats[out_cols].sum(axis=1)
                stats["守備機会"] = stats["刺殺・補殺"] + stats["失策"]
                
                # 4. 表示用に整理
                display_cols = ["守備機会", "刺殺・補殺", "失策"]
                final_df = stats[display_cols].reset_index()
                
                # 並び替え（ポジション順）
                pos_order = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                
                def get_pos_order(name_str):
                    for i, p in enumerate(pos_order):
                        if f"({p})" in name_str: 
                            return i
                    return 99 # ポジション名がない場合は後ろへ

                final_df["Order"] = final_df["処理野手"].apply(get_pos_order)
                # ポジション順 → 守備機会が多い順
                final_df = final_df.sort_values(["Order", "守備機会"], ascending=[True, False]).drop(columns=["Order"])
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.dataframe(final_df, use_container_width=True, hide_index=True)
                with col2:
                    st.bar_chart(final_df.set_index("処理野手")[["刺殺・補殺", "失策"]])
                
            else:
                st.info("守備記録（凡退処理・失策など）データがまだありません。")
        else:
            st.info("データがありません。")

elif page == "🔧 データ修正":
    st.title("🔧 データ修正")
    st.info(
        """
        **【データの削除・修正方法】**
        - **削除**: 行の左端をクリックして選択し、`Delete` キーで削除。
        - **修正**: セルをダブルクリックして修正（すべての項目が選択式になっています）。
        - **確定**: 編集後は必ず下の **「保存」ボタン** を押してください。
        """
    )

    t1, t2 = st.tabs(["打撃成績", "投手成績"])
    
    # 共通の選択肢定義
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
                # 処理野手の編集を追加
                "処理野手": st.column_config.SelectboxColumn("処理野手", options=["", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]),
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
            st.cache_data.clear()
            st.success("✅ 投手データを更新しました！")
            st.rerun()