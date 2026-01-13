import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# ==========================================
# 1. セッション状態の初期化（ベンチメンバー保持用）
# ==========================================
if "persistent_bench" not in st.session_state:
    st.session_state["persistent_bench"] = []

def update_bench_state():
    """マルチセレクトが変更されたら、即座に記憶領域に保存する関数"""
    st.session_state["persistent_bench"] = st.session_state["bench_selection_widget"]

# ▼▼▼ 追加：イニング文字列を数値に変換する関数（ソート用） ▼▼▼
def inning_sort_key(inn_str):
    try:
        return int(str(inn_str).replace("回", ""))
    except:
        return 99
# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

# ▼▼▼ delete_match_logic（完全上書きモード） ▼▼▼

def delete_match_logic(date, opponent):
    try:
        # ===========================================================
        # ⚠️ ここにスプレッドシートのURLを貼ってください（必須）
        SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Dt74KFYNrdjTlQsMwjM0XsvepBnWHG3iBHQjOaE_t5E/edit?usp=sharing"
        
        SHEET_NAME_BATTING = "打撃成績"
        SHEET_NAME_PITCHING = "投手成績"
        # ===========================================================

        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # クリーニング関数
        def clean_text(text):
            return str(text).replace(" ", "").replace("　", "").strip()

        target_date_str = pd.to_datetime(date).strftime('%Y-%m-%d')
        target_opp_clean = clean_text(opponent)
        
        deleted_something = False

        # -----------------------------------------------------
        # 1. 打撃データの処理
        # -----------------------------------------------------
        try:
            # 最新データを取得
            df_b = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=SHEET_NAME_BATTING, ttl=0)
        except:
            df_b = pd.DataFrame()

        if df_b is not None and not df_b.empty:
            original_len = len(df_b)
            
            # 比較用データ作成
            df_b["_calc_date"] = pd.to_datetime(df_b["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            df_b["_calc_opp"] = df_b["対戦相手"].apply(clean_text)
            
            # 削除対象を探す
            mask_delete = (df_b["_calc_date"] == target_date_str) & (df_b["_calc_opp"] == target_opp_clean)
            
            if mask_delete.sum() > 0:
                # 削除対象以外を残す
                new_df_b = df_b[~mask_delete].copy()
                
                # 余計な列を消す
                save_df_b = new_df_b.drop(columns=["_calc_date", "_calc_opp"])
                
                # 【重要】updateではなく、clearしてからwriteする（確実に行を減らすため）
                conn.clear(spreadsheet=SPREADSHEET_URL, worksheet=SHEET_NAME_BATTING)
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=SHEET_NAME_BATTING, data=save_df_b)
                
                st.session_state["df_batting"] = save_df_b
                deleted_something = True
                st.write("打撃データを更新しました。")

        # -----------------------------------------------------
        # 2. 投手データの処理
        # -----------------------------------------------------
        try:
            df_p = conn.read(spreadsheet=SPREADSHEET_URL, worksheet=SHEET_NAME_PITCHING, ttl=0)
        except:
            df_p = pd.DataFrame()

        if df_p is not None and not df_p.empty:
            df_p["_calc_date"] = pd.to_datetime(df_p["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            df_p["_calc_opp"] = df_p["対戦相手"].apply(clean_text)

            mask_delete_p = (df_p["_calc_date"] == target_date_str) & (df_p["_calc_opp"] == target_opp_clean)
            
            if mask_delete_p.sum() > 0:
                new_df_p = df_p[~mask_delete_p].copy()
                save_df_p = new_df_p.drop(columns=["_calc_date", "_calc_opp"])
                
                # 【重要】clearしてからwrite
                conn.clear(spreadsheet=SPREADSHEET_URL, worksheet=SHEET_NAME_PITCHING)
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=SHEET_NAME_PITCHING, data=save_df_p)
                
                st.session_state["df_pitching"] = save_df_p
                deleted_something = True
                st.write("投手データを更新しました。")

        # -----------------------------------------------------
        # 完了処理
        # -----------------------------------------------------
        if deleted_something:
            st.cache_data.clear() # キャッシュも消す
            return True
        else:
            st.warning("削除対象が見つかりませんでした（すでに削除されている可能性があります）。")
            return False

    except Exception as e:
        st.error(f"システムエラー: {e}")
        return False

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
# ==========================================
# 定数定義
# ==========================================

# ▼▼▼ 背番号辞書 (名前: 背番号) ▼▼▼
# 頂いたリストを元に作成しました
# 背番号辞書
PLAYER_NUMBERS = {
    "佐藤蓮太": "1", "久保田剛志": "2", "開田凌空": "3", "水谷真智": "4", "河野潤樹": "5",
    "渡邉誠也": "7", "岡﨑英一": "8", "中尾建太": "10", "内藤洋輔": "11", "大高翼": "13",
    "小野拓朗": "15", "古屋翔": "17", "伊東太建": "18", "渡邉竣太": "19", "山田大貴": "21",
    "志村裕三": "23", "石田貴大": "24", "相原一博": "25", "田中伸延": "26", "坂本昂士": "27",
    "渡辺羽": "28", "石原圭佑": "29", "荒木豊": "31", "永井雄太": "33", "小野慎也": "38",
    "清水智広": "43", "名執雅叶": "51", "山縣諒介": "60", "照屋航": "63", "望月駿": "66",
    "鈴木翔大": "73"
}
my_team_fixed = "KAGURA"
all_players = list(PLAYER_NUMBERS.keys())
all_positions = ["", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
# グラウンドリスト（追加分を反映）
ground_list = [
    "小瀬スポーツ公園", "緑が丘スポーツ公園", "飯田球場", 
    "中巨摩第二公園", "スコレーセンター", "花鳥の里スポーツ広場", "春日居スポーツ広場",
    "山梨大学", "双葉スポーツ公園", "釜無川スポーツ公園", "八田野球場", "北麓公園",
    "その他"
]

# --- データ読み込み（API制限対策: キャッシュ有効化） ---
def load_batting_data():
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, ttl="10m")
        # もしデータが空なら、空のDataFrameを返す（カラム定義付き）
        if data.empty:
             return pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])

        # 必須カラムの定義（日付を含めることが重要）
        expected_cols = ["日付", "打点", "盗塁", "得点", "位置", "グラウンド", "対戦相手", "試合種別", "イニング", "選手名", "結果", "種別"]
        
        # 足りないカラムがあれば強制的に追加
        for col in expected_cols:
            if col not in data.columns:
                data[col] = 0 if col in ["打点", "盗塁", "得点"] else ""

        # 日付型の変換
        data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
            
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "盗塁", "種別", "グラウンド", "対戦相手", "試合種別"])

def load_pitching_data():
    try:
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl="10m") # 開発中はttl=0推奨
        if data.empty:
             return pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "処理野手", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "勝敗"])

        # 必須カラムの定義（ここに「勝敗」を追加）
        expected_cols = ["日付", "アウト数", "球数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "処理野手", "イニング", "投手名", "結果", "勝敗"]

        # 足りないカラムがあれば強制的に追加
        for col in expected_cols:
            if col not in data.columns: 
                if col in ["グラウンド", "対戦相手", "試合種別", "処理野手", "投手名", "結果", "イニング", "勝敗"]:
                    data[col] = ""
                else:
                    data[col] = 0
        
        # 日付型の変換
        data["日付"] = pd.to_datetime(data["日付"], errors='coerce').dt.date
            
        return data.dropna(how="all")
    except:
        return pd.DataFrame(columns=["日付", "イニング", "投手名", "結果", "処理野手", "球数", "アウト数", "失点", "自責点", "グラウンド", "対戦相手", "試合種別", "勝敗"])

df_batting = load_batting_data()
df_pitching = load_pitching_data()

# ==========================================
# サイドバー設定
# ==========================================
st.sidebar.header("⚙️ 試合設定")

# 1. まず大枠をボタン（radio）で選択
match_category = st.sidebar.radio("試合区分", ["公式戦", "練習試合", "その他"], horizontal=True)

# 2. 公式戦の場合だけ、具体的な大会名をプルダウンで選択
if match_category == "公式戦":
    # 公式戦の大会リスト
    official_tournaments = ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯"]
    match_type = st.sidebar.selectbox("大会名を選択", official_tournaments)
else:
    # 練習試合やその他の場合は、その区分名自体を登録データとする
    match_type = match_category

# 確認用（開発時のみ表示、不要なら削除可）
# st.sidebar.write(f"登録される種別: {match_type}")

#今日の試合データ（フィルタリング）
game_date = st.sidebar.date_input("試合日", datetime.date.today())
selected_date_str = game_date.strftime('%Y-%m-%d')
selected_ground_base = st.sidebar.selectbox("グラウンド", ground_list)
ground_name = st.sidebar.text_input("グラウンド名入力", value="グラウンド") if selected_ground_base == "その他" else selected_ground_base
opponents_list = ["ミッピーズ", "WISH", "NATSUME", "92ears", "球遊会", "プリティーボーイズ", "DREAM", "リベリオン", "KING STAR", "甲府市役所", "SQUAD", "CRAZY",
    "桜華", "甲府ドラゴンズ", "南アルプス市役所", "風間自工", "凪" ,"その他"]
selected_opp = st.sidebar.selectbox("相手チーム", opponents_list)
opp_team = st.sidebar.text_input("相手名", value="相手チーム") if selected_opp == "その他" else selected_opp
kagura_order = st.sidebar.radio(f"攻守", ["先攻 (表)", "後攻 (裏)"], horizontal=True)

# サイドバーの radio に "👑 歴代記録" を追加
page = st.sidebar.radio("表示", ["🏠 打撃成績入力", "🔥 投手成績入力", "🏆 チーム戦績", "📊 個人成績", "👑 歴代記録", "🔧 データ修正"])

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
        
        # ▼▼▼ 修正箇所：得点が入っている列を「合計」するロジックに変更 ▼▼▼
        # これにより、結果が本塁打でも盗塁でも、得点が1なら加算されます
        inn_bat_data = b_df[b_df["イニング"] == inn]
        k_runs = int(pd.to_numeric(inn_bat_data["得点"], errors='coerce').sum())
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        
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
    
    # 1. モード選択
    st.markdown("### 📝 入力モード")
    input_mode = st.radio(
        "モードを選択してください", 
        [
            "詳細入力 (選手ごとの成績)", 
            "選手別まとめ入力 (詳細不明・過去データ用)", 
            "スコアのみ登録 (詳細完全不明)"
        ], 
        horizontal=True
    )

    # スコアボード表示
    render_scoreboard(today_batting_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()

    # ---------------------------------------------------------
    # A. スコアのみ登録モード
    # ---------------------------------------------------------
    if input_mode == "スコアのみ登録 (詳細完全不明)":
        st.warning("【注意】このモードで登録したデータは個人成績には反映されません。")
        # （既存のスコア登録コードがあればそのまま残す、なければ以下の実装を使う）
        # ... (省略: 既存のコードをお使いください) ...

    # ---------------------------------------------------------
    # B. 選手別まとめ入力モード
    # ---------------------------------------------------------
    elif input_mode == "選手別まとめ入力 (詳細不明・過去データ用)":
        st.info("選手ごとの「試合合計数」を入力します。")
        # ... (省略: 既存のコードをお使いください) ...

    # ---------------------------------------------------------
    # C. 詳細入力モード (ベンチメンバー登録対応版)
    # ---------------------------------------------------------
    else:
        
        # --- 登録実行関数 ---
        def submit_batting():
            # 1. ベンチメンバーの取得
            current_bench = st.session_state.get("persistent_bench", [])
            
            # 2. スタメン（15番まで）の収集
            new_records = []
            current_starters = []
            
            for i in range(15):
                p_name = st.session_state.get(f"sn{i}")
                if p_name:
                    current_starters.append(p_name)
                    p_res = st.session_state.get(f"sr{i}", "---")
                    p_pos = st.session_state.get(f"sp{i}", "")
                    p_rbi = st.session_state.get(f"si{i}", 0)
                    
                    rbi_val = int(p_rbi); run_val = 0; sb_val = 0; type_val = "打撃" 
                    if p_res == "本塁打":
                        run_val = 1
                    elif p_res == "得点": 
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

            # 3. 重複チェック
            duplicates = set(current_starters) & set(current_bench)
            if duplicates:
                st.error(f"⚠️ エラー: {', '.join(duplicates)} がスタメンとベンチ両方に選ばれています。")
                return

            # 4. ベンチ入りメンバーを「控え」として追加
            for bench_player in current_bench:
                new_records.append({
                    "日付": selected_date_str, 
                    "グラウンド": ground_name, 
                    "対戦相手": opp_team, 
                    "試合種別": match_type,
                    "イニング": "ベンチ",
                    "選手名": bench_player, 
                    "位置": "控",
                    "結果": "ー",
                    "打点": 0, "得点": 0, "盗塁": 0, "種別": "ベンチ"
                })

            # 5. 保存実行
            if new_records:
                try:
                    conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True))
                    st.cache_data.clear()
                    st.success(f"✅ {len(new_records)} 件のデータを登録しました（スタメン＋ベンチ）")
                    
                    # 入力欄クリア（結果と打点のみリセット）
                    for i in range(15):
                        st.session_state[f"sr{i}"] = "---"
                        st.session_state[f"si{i}"] = 0
                except Exception as e:
                    st.error(f"保存エラー: {e}")
            else:
                st.warning("登録するデータがありません。")

        # --- UIレイアウト ---
        st.button("登録実行", type="primary", on_click=submit_batting, use_container_width=True)
        st.write("") 

        # イニング表示
        c_inn, c_outs, _ = st.columns([1.5, 2.0, 4.0])
        with c_inn:
            st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="current_inn_key")
        with c_outs:
            st.write("")
            # アウトカウント表示ロジックがあればここに記述

        # スタメン入力枠 (15名)
        col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]
        h_cols = st.columns(col_ratios)
        for col, label in zip(h_cols, ["打順", "守備", "氏名", "結果", "打点", "成績"]):
            col.write(f"**{label}**")

        batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]

        for i in range(15):
            c = st.columns(col_ratios)
            c[0].write(f"{i+1}")
            
            # 前回のラインナップ復元用
            def_pos_ix = 0; def_name_ix = 0
            if "saved_lineup" in st.session_state:
                s_pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
                if s_pos in all_positions: def_pos_ix = all_positions.index(s_pos)
                s_name = st.session_state["saved_lineup"].get(f"name_{i}", "")
                if s_name in ([""] + all_players): def_name_ix = ([""] + all_players).index(s_name)

            c[1].selectbox(f"p{i}", all_positions, index=def_pos_ix, key=f"sp{i}", label_visibility="collapsed")
            c[2].selectbox(f"n{i}", [""] + all_players, index=def_name_ix, key=f"sn{i}", label_visibility="collapsed")
            c[3].selectbox(f"r{i}", batting_results, key=f"sr{i}", label_visibility="collapsed")
            c[4].selectbox(f"i{i}", [0, 1, 2, 3, 4], key=f"si{i}", label_visibility="collapsed")
            
            # 成績表示（当日データがある場合）
            if not today_batting_df.empty:
                current_name = st.session_state.get(f"sn{i}")
                if current_name:
                    p_df = today_batting_df[today_batting_df["選手名"] == current_name]
                    if not p_df.empty:
                        # 簡易表示: 打点などの合計
                        sum_rbi = pd.to_numeric(p_df["打点"], errors='coerce').sum()
                        c[5].markdown(f"<small>打点:{int(sum_rbi)}</small>", unsafe_allow_html=True)
                    else:
                        c[5].write("")
                else:
                    c[5].write("")
            else:
                c[5].write("")

        # ---------------------------------------------------------
        # ▼ ベンチメンバー選択エリア
        # ---------------------------------------------------------
        st.divider()
        with st.expander("🚌 ベンチ入りメンバー (続き10名〜) を選択", expanded=True):
            st.multiselect(
                "ベンチメンバーを選択してください（スタメン以外）", 
                all_players, 
                default=st.session_state.get("persistent_bench", []), 
                on_change=update_bench_state,
                key="bench_selection_widget"
            )
            st.caption("※ここで選んだメンバーも「登録実行」で一緒に保存されます。")


elif page == "🔥 投手成績入力":
    is_kagura_top = (kagura_order == "先攻 (表)")
    
    # ▼▼▼ 1. モード選択ラジオボタンの追加 ▼▼▼
    st.markdown("### 📝 入力モード")
    input_mode_p = st.radio(
        "モードを選択してください", 
        ["詳細入力 (1球ごと)", "選手別まとめ入力 (詳細不明・過去データ用)"], 
        horizontal=True
    )
    
    # スコアボード表示（共通）
    render_scoreboard(today_batting_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()
    
    # ---------------------------------------------------------
    # A. 選手別まとめ入力モード（新機能）
    # ---------------------------------------------------------
    if input_mode_p == "選手別まとめ入力 (詳細不明・過去データ用)":
        st.info("投球回や奪三振数などの「合計値」を入力します。自動的に計算用のアウト数データなどが生成され、通算成績に反映されます。")
        
        # 入力用データフレームのひな形
        # ユーザーが入力しやすい項目定義
        input_cols_p = ["投手名", "勝敗", "投球回", "端数", "球数", "被安打", "奪三振", "四球", "死球", "失点", "自責点"]
        
        default_data_p = pd.DataFrame([
            {col: (0 if col not in ["投手名", "勝敗", "端数"] else None) for col in input_cols_p} 
            for _ in range(5)
        ])
        
        # 勝敗の選択肢
        decision_opts = ["-", "勝利", "敗戦", "S", "H"]
        # 端数の選択肢
        fraction_opts = ["0", "1/3", "2/3"]

        st.write("▼ 下の表に成績を入力してください")
        
        edited_df_p = st.data_editor(
            default_data_p,
            column_config={
                "投手名": st.column_config.SelectboxColumn("投手名", options=all_players, required=True),
                "勝敗": st.column_config.SelectboxColumn("勝敗", options=decision_opts, default="-"),
                "投球回": st.column_config.NumberColumn("投球回", min_value=0, step=1, help="イニングの整数部分"),
                "端数": st.column_config.SelectboxColumn("端数", options=fraction_opts, default="0", help="1アウト=1/3"),
                "球数": st.column_config.NumberColumn("球数", min_value=0, step=1),
                "被安打": st.column_config.NumberColumn("被安打", min_value=0, step=1),
                "奪三振": st.column_config.NumberColumn("奪三振", min_value=0, step=1),
                "四球": st.column_config.NumberColumn("四球", min_value=0, step=1),
                "死球": st.column_config.NumberColumn("死球", min_value=0, step=1),
                "失点": st.column_config.NumberColumn("失点", min_value=0, step=1),
                "自責点": st.column_config.NumberColumn("自責点", min_value=0, step=1),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="bulk_pitcher_input"
        )
        
        if st.button("一括登録", type="primary", key="btn_bulk_pit_insert"):
            new_records = []
            
            for index, row in edited_df_p.iterrows():
                p_name = row["投手名"]
                if not p_name: continue
                
                # --- 値の取得 ---
                # 勝敗
                dec_raw = row.get("勝敗", "-")
                dec_val = ""
                if dec_raw == "勝利": dec_val = "勝"
                elif dec_raw == "敗戦": dec_val = "負"
                elif dec_raw == "S": dec_val = "S"
                elif dec_raw == "H": dec_val = "H"
                
                # アウト数計算
                inn_int = int(row.get("投球回", 0))
                frac_str = row.get("端数", "0")
                frac_val = 0
                if frac_str == "1/3": frac_val = 1
                elif frac_str == "2/3": frac_val = 2
                
                total_outs = (inn_int * 3) + frac_val
                
                # その他カウント
                count_so = int(row.get("奪三振", 0))
                count_bb = int(row.get("四球", 0))
                count_hbp = int(row.get("死球", 0))
                count_hits = int(row.get("被安打", 0))
                
                val_balls = int(row.get("球数", 0))
                val_runs = int(row.get("失点", 0))
                val_er = int(row.get("自責点", 0))
                
                # --- レコード生成ロジック ---
                # 投手成績の集計は「行数カウント」と「数値合計」の組み合わせで行われるため、
                # 適切な数の行を作成します。
                
                records_buffer = []

                # 1. 奪三振の分だけレコード作成 (アウト数=1)
                for _ in range(count_so):
                    records_buffer.append({
                        "結果": "三振", "アウト数": 1, "処理野手": "" 
                    })
                
                # 2. 残りのアウト数分だけ「凡退」レコード作成 (アウト数=1)
                remaining_outs = total_outs - count_so
                # もし奪三振数が総アウト数を超えている場合（入力ミスの可能性が高いが）は凡退を作らない
                if remaining_outs > 0:
                    for _ in range(remaining_outs):
                        records_buffer.append({
                            "結果": "凡退", "アウト数": 1, "処理野手": "" 
                        })
                
                # 3. 四死球の分だけレコード作成 (アウト数=0)
                for _ in range(count_bb):
                    records_buffer.append({"結果": "四球", "アウト数": 0, "処理野手": ""})
                for _ in range(count_hbp):
                    records_buffer.append({"結果": "死球", "アウト数": 0, "処理野手": ""})
                    
                # 4. 被安打の分だけレコード作成 (アウト数=0, 結果=単打として登録)
                for _ in range(count_hits):
                    records_buffer.append({"結果": "単打", "アウト数": 0, "処理野手": ""})

                # --- データの付与（失点・球数・勝敗） ---
                # 作成したレコードのうち、先頭の1行にまとめて数値を載せる
                # もしレコードが1つもない（アウト0、被安打0...）場合はダミーを作る
                if not records_buffer:
                    records_buffer.append({"結果": "凡退", "アウト数": 0, "処理野手": ""})
                
                first_rec = True
                for rec in records_buffer:
                    # 先頭行にだけ重みのあるデータを載せる
                    if first_rec:
                        r_runs = val_runs
                        r_er = val_er
                        r_balls = val_balls
                        r_dec = dec_val
                        first_rec = False
                    else:
                        r_runs = 0
                        r_er = 0
                        r_balls = 0
                        r_dec = ""
                    
                    new_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, 
                        "対戦相手": opp_team, "試合種別": match_type, 
                        "イニング": "記録のみ", 
                        "投手名": p_name, 
                        "結果": rec["結果"], 
                        "処理野手": rec["処理野手"], 
                        "球数": r_balls, 
                        "アウト数": rec["アウト数"], 
                        "失点": r_runs, 
                        "自責点": r_er,
                        "勝敗": r_dec
                    })

            if new_records:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, pd.DataFrame(new_records)], ignore_index=True))
                st.cache_data.clear()
                st.success(f"{len(new_records)} 行のデータを生成して登録しました！")
                import time
                time.sleep(1)
                st.rerun()
            else:
                st.warning("登録するデータがありません。投手名と成績を入力してください。")

    # ---------------------------------------------------------
    # B. 詳細入力モード（既存機能）
    # ---------------------------------------------------------
    else:
        # --- 登録処理用コールバック関数 ---
        def submit_pitching():
            p_name = st.session_state.get("pit_name")
            p_inning = st.session_state.get("pit_inn")
            p_res = st.session_state.get("pit_res")
            p_count = 0 
            
            pruns = st.session_state.get("pit_runs")
            per = st.session_state.get("pit_er")
            
            p_dec_raw = st.session_state.get("pit_decision_key")
            p_dec_val = ""
            if p_dec_raw == "勝利投手": p_dec_val = "勝"
            elif p_dec_raw == "敗戦投手": p_dec_val = "負"
            elif p_dec_raw == "セーブ": p_dec_val = "S"
            elif p_dec_raw == "ホールド": p_dec_val = "H"

            p_fielder_raw = st.session_state.get("pit_fielder", "")
            if "記録なし" in p_fielder_raw: p_fielder_name = "" 
            else: p_fielder_name = p_fielder_raw 

            if p_name:
                out_inc = 1 if p_res in ["三振", "凡退", "犠打", "走塁死", "盗塁死", "牽制死"] else 0
                target_events = ["凡退", "失策", "犠打", "走塁死", "牽制死", "盗塁死"]
                if p_res not in target_events: p_fielder_name = ""

                new_p = pd.DataFrame([{
                    "日付": selected_date_str, "グラウンド": ground_name, 
                    "対戦相手": opp_team, "試合種別": match_type, 
                    "イニング": p_inning, "投手名": p_name, 
                    "結果": p_res, "処理野手": p_fielder_name, 
                    "球数": int(p_count), "アウト数": out_inc, 
                    "失点": int(pruns), "自責点": int(per),
                    "勝敗": p_dec_val
                }])
                
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, new_p], ignore_index=True))
                st.cache_data.clear()
                
                msg = "登録しました！"
                if p_dec_val: msg += f" （{p_name}投手に【{p_dec_raw}】を記録）"
                st.session_state["success_msg"] = msg
                
                st.session_state["pit_res"] = "凡退"
                st.session_state["pit_runs"] = 0
                st.session_state["pit_er"] = 0
                st.session_state["pit_decision_key"] = "-"
                
            else:
                st.session_state["error_msg"] = "⚠️ 投手名を選択してください"

        if "success_msg" in st.session_state:
            st.toast(st.session_state["success_msg"])
            del st.session_state["success_msg"]
        if "error_msg" in st.session_state:
            st.error(st.session_state["error_msg"])
            del st.session_state["error_msg"]

        # --- レイアウト ---
        st.button("登録", type="primary", on_click=submit_pitching, use_container_width=True)
        st.write("") 

        c_inn, c_outs, c_blank = st.columns([1.5, 2.0, 4.0])
        with c_inn:
            p_inning = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="pit_inn")
        
        with c_outs:
            if not today_pitching_df.empty:
                current_inn_display = st.session_state.get("pit_inn", p_inning)
                this_inn_p = today_pitching_df[today_pitching_df["イニング"] == current_inn_display]
                outs_p = int(this_inn_p["アウト数"].sum())
            else: outs_p = 0
            st.write(""); st.write("")
            if outs_p < 3: st.markdown(f"<h4 style='margin:0; color:#333; line-height:1.2;'>{'🔴 '*outs_p + '⚪ '*(3-outs_p)} Out</h4>", unsafe_allow_html=True)
            else: st.markdown(f"<h4 style='margin:0; color:red; line-height:1.2;'>🔴 🔴 🔴 CHANGE</h4>", unsafe_allow_html=True)

        st.divider()
        
        p_list = [""] + all_players
        default_p_index = 0
        current_val = st.session_state.get("pit_name")
        if current_val and current_val in p_list: default_p_index = p_list.index(current_val)
        elif "saved_lineup" in st.session_state:
            saved_data = st.session_state["saved_lineup"]
            for i in range(15):
                if saved_data.get(f"pos_{i}") == "投":
                    starter_name = saved_data.get(f"name_{i}")
                    if starter_name in p_list: default_p_index = p_list.index(starter_name)
                    break

        st.selectbox("投手名", p_list, index=default_p_index, key="pit_name")
        
        st.radio("結果", ["凡退", "三振", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "失策", "犠打", "走塁死", "盗塁死", "牽制死"], horizontal=True, key="pit_res")
        
        target_events = ["凡退", "失策", "犠打", "走塁死", "牽制死", "盗塁死"]
        pit_res_val = st.session_state.get("pit_res")
        if pit_res_val in target_events:
            current_fielders = []
            current_p_name = st.session_state.get("pit_name", "")
            if current_p_name: current_fielders.append(f"{current_p_name} (投)")
            
            if "saved_lineup" in st.session_state:
                saved_data = st.session_state["saved_lineup"]
                for i in range(15):
                    nm = saved_data.get(f"name_{i}"); pos = saved_data.get(f"pos_{i}")
                    if nm and pos and pos not in ["", "DH", "代打", "投"]: current_fielders.append(f"{nm} ({pos})")
            elif not today_batting_df.empty:
                df_fielders = today_batting_df[(today_batting_df["位置"].isin(["捕", "一", "二", "三", "遊", "左", "中", "右"])) & (today_batting_df["選手名"] != "")][["選手名", "位置"]].drop_duplicates()
                for _, row in df_fielders.iterrows():
                    if row["位置"] != "投": current_fielders.append(f"{row['選手名']} ({row['位置']})")
            
            seen = set(); current_fielders = [x for x in current_fielders if not (x in seen or seen.add(x))]
            if not current_fielders: current_fielders = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
            current_fielders.append("記録なし (アウトのみ)")

            if pit_res_val == "失策": st.info("👇 誰がエラーしましたか？")
            else: st.info("👇 誰が処理しましたか？")
            st.selectbox("対象選手", current_fielders, key="pit_fielder")

        st.write("▼ 数値入力・勝敗判定")
        cr, ce, cw = st.columns([1, 1, 2])
        cr.selectbox("失点", [0,1,2,3,4], key="pit_runs")
        ce.selectbox("自責", [0,1,2,3,4], key="pit_er")
        cw.selectbox("勝敗判定 (今回確定する場合)", ["-", "勝利投手", "敗戦投手", "セーブ", "ホールド"], key="pit_decision_key")

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

            # --- ▼▼▼ チーム成績メトリクスの計算 ▼▼▼ ---
            games_count = wins + loses + draws
            win_rate = wins / (wins + loses) if (wins + loses) > 0 else 0.000

            # 1. 打撃系指標
            team_runs = pd.to_numeric(df_b_target["得点"], errors='coerce').sum()
            team_sb = pd.to_numeric(df_b_target["盗塁"], errors='coerce').sum()
            team_hr = df_b_target[df_b_target["結果"] == "本塁打"].shape[0]
            
            # 打率計算 (打数 = 安打 + 凡退 + 失策 + 走塁死 + 三振)
            hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
            ab_cols = hit_cols + ["凡退", "失策", "走塁死", "盗塁死", "牽制死", "三振"]
            
            team_hits = df_b_target[df_b_target["結果"].isin(hit_cols)].shape[0]
            team_ab = df_b_target[df_b_target["結果"].isin(ab_cols)].shape[0]
            team_avg = team_hits / team_ab if team_ab > 0 else 0.0
            
            # 得点率 (1試合平均得点)
            runs_per_game = team_runs / games_count if games_count > 0 else 0.0

            # 2. 投手系指標
            team_runs_allowed = pd.to_numeric(df_p_target["失点"], errors='coerce').sum()
            team_er = pd.to_numeric(df_p_target["自責点"], errors='coerce').sum()
            team_outs = pd.to_numeric(df_p_target["アウト数"], errors='coerce').sum()
            
            # 防御率
            team_innings = team_outs / 3
            team_era = (team_er * 9) / team_innings if team_innings > 0 else 0.0
            
            # 失点率 (1試合平均失点)
            runs_allowed_per_game = team_runs_allowed / games_count if games_count > 0 else 0.0

            # --- 表示 (3段構成) ---
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
                
                # ▼▼▼ 修正箇所：「打撃成績 (スコアブック)」の表示ロジック ▼▼▼
                with tab_d_bat:
                    if not detail_b.empty:
                        # まず、この試合のデータを「イニング順」に並べ替える
                        # これにより、後から修正してもイニングが早い順に「第1打席」となります
                        detail_b["_inn_sort"] = detail_b["イニング"].apply(inning_sort_key)
                        detail_b_sorted = detail_b.sort_values(by=["_inn_sort"])  # 並べ替え実行

                        # 登場した順に選手リストを作成（重複なし）
                        players_ordered = detail_b_sorted["選手名"].unique()
                        
                        batting_rows = []
                        max_at_bats = 0 
                        display_targets = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策"]

                        for i, p_name in enumerate(players_ordered):
                            # 並べ替えたデータから、その選手の行だけを抽出
                            p_rows = detail_b_sorted[detail_b_sorted["選手名"] == p_name]
                            
                            # 最終的な守備位置を取得
                            pos = p_rows.iloc[-1]["位置"] if "位置" in p_rows.columns else "-"
                            
                            # 結果のリストを取得（イニング順になっているので、ここが正しく第1、第2...となる）
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

                # ▼▼▼ 投手成績：個人別集計 ▼▼▼
                with tab_d_pit:
                    if not detail_p.empty:
                        pitchers = detail_p["投手名"].unique()
                        p_rows = []
                        for p_name in pitchers:
                            p_data = detail_p[detail_p["投手名"] == p_name]
                            outs = p_data["アウト数"].sum()
                            balls = p_data["球数"].sum()
                            runs = p_data["失点"].sum()
                            er = p_data["自責点"].sum()
                            hits = p_data["被安打"].sum()

    # ▼▼▼ チーム戦績ページの一番最後（ここを書き換えてください） ▼▼▼
    
    st.markdown("---")
    st.subheader("⚠️ 試合データの削除")

    # 確実にデータがあるか確認してからリストを作る
    df_for_list = None
    if "df_batting" in st.session_state:
        df_for_list = st.session_state["df_batting"]
    
    if df_for_list is not None and not df_for_list.empty:
        # リスト作成：日付を確実に YYYY-MM-DD 文字列にして結合する
        # これで関数側と同じ形式になるので「不一致」がなくなります
        def make_label(row):
            d_str = pd.to_datetime(row["日付"]).strftime('%Y-%m-%d')
            opp = str(row["対戦相手"])
            return f"{d_str}___{opp}" # 区切り文字をアンダーバー3つにする（ミス防止）

        match_labels = df_for_list.apply(make_label, axis=1).unique()
        match_labels = sorted(match_labels, reverse=True)
        
        # 表示用のきれいなラベルへの変換マップを作る
        label_map = {}
        display_options = []
        for label in match_labels:
            d, o = label.split("___")
            disp = f"{d} vs {o}"
            label_map[disp] = (d, o) # 表示名 -> (日付, 相手) の辞書
            display_options.append(disp)

        # UI表示
        c_del1, c_del2 = st.columns([3, 1])
        with c_del1:
            selected_disp = st.selectbox("削除する試合を選択", display_options, key="del_select_box")
        
        with c_del2:
            st.write("")
            st.write("")
            check_del = st.checkbox("削除確認", key="del_check_box")
            
        if st.button("試合データを削除（復元不可）", type="primary", key="del_btn_exec"):
            if check_del and selected_disp:
                # 辞書から正確な「日付」と「相手」を取り出す
                target_date, target_opp = label_map[selected_disp]
                
                st.write(f"処理を開始します... {target_date} / {target_opp}")
                
                # 実行！
                if delete_match_logic(target_date, target_opp):
                    st.success(f"「{selected_disp}」を削除しました！")
                    st.cache_data.clear() # キャッシュクリア
                    import time
                    time.sleep(2) # メッセージを読めるように少し待つ
                    st.rerun()    # 画面リロード
                else:
                    st.error("削除処理を行いましたが、対象が見つかりませんでした（診断メッセージを確認してください）")
            else:
                st.warning("確認チェックを入れてください。")
    else:
        st.info("削除できるデータがありません（データ読み込み待ち、またはデータなし）")  

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

elif page == "👑 歴代記録":
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
        for col in ["アウト数", "自責点", "失点", "奪三振"]:
            # 奪三振は結果カラムから計算する必要がある場合と、数値入力の場合があるため調整
            # ここでは「結果=三振」の行をカウントする方式を基本とする
            pass

        df_p_calc["is_so"] = (df_p_calc["結果"] == "三振").astype(int)
        
        # 勝敗カウント用
        df_p_calc["is_win"] = df_p_calc["勝敗"].astype(str).str.contains("勝").astype(int)

        agg_rules_p = {
            "アウト数": "sum",
            "自責点": "sum",
            "is_so": "sum", # 奪三振
            "is_win": "sum" # 勝利数
        }
        
        # 数値カラムの変換
        for col in ["自責点", "失点"]:
             df_p_calc[col] = pd.to_numeric(df_p_calc[col], errors='coerce').fillna(0)

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
    
    # 既存データから対戦相手・グラウンドを抽出してマージ
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
    
    # ▼▼▼ 修正箇所：変数名を match_types に統一して定義 ▼▼▼
    match_types = ["高松宮賜杯", "天皇杯", "ミズノ杯", "東日本", "会長杯", "市長杯", "練習試合", "その他", "公式戦"]
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

    with t1:
        st.write("▼ 打撃データの編集")
        ed_b = st.data_editor(
            df_batting,
            column_config={
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD", required=True),
                "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=merged_grounds, required=True),
                "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=merged_opps, required=True),
                # ▼▼▼ ここで match_types を使用
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
                # ▼▼▼ ここでも match_types を使用（エラー箇所の修正）
                "試合種別": st.column_config.SelectboxColumn("試合種別", options=match_types, required=True),
                "イニング": st.column_config.SelectboxColumn("イニング", options=default_innings, required=True),
                "投手名": st.column_config.SelectboxColumn("投手名", options=all_players, required=True),
                "結果": st.column_config.SelectboxColumn("結果", options=pitching_results, required=True),
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