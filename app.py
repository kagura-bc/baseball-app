import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# ==========================================
# 1. セッション状態の初期化（ベンチメンバー保持用）
# ==========================================
if "persistent_bench" not in st.session_state:
    st.session_state["persistent_bench"] = []

# ページ冒頭の初期化部分に追加
if "opp_batter_index" not in st.session_state:
    st.session_state["opp_batter_index"] = 1  # 今何番打者か
if "opp_batter_count" not in st.session_state:
    st.session_state["opp_batter_count"] = 9  # 打順が何人までか（初期値9）

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

# ▼▼▼ 新規追加する関数 ▼▼▼
def save_lineup_item(i, item_type):
    """
    入力内容が変更された瞬間に、データを永続保存領域(saved_lineup)に記録する
    i: 打順 (0-14)
    item_type: 'pos', 'name', 'res', 'rbi'
    """
    if "saved_lineup" not in st.session_state:
        st.session_state["saved_lineup"] = {}
        
    # キーのマッピング (sp0, sn0, sr0, si0 に対応)
    prefix_map = {"pos": "sp", "name": "sn", "res": "sr", "rbi": "si"}
    widget_key = f"{prefix_map[item_type]}{i}"
    
    # 現在の入力値を保存
    if widget_key in st.session_state:
        val = st.session_state[widget_key]
        st.session_state["saved_lineup"][f"{item_type}_{i}"] = val

# 関数定義：特大サイズのアウトカウント表示
def render_out_indicator_3(count):
    color_on = "#ff2b2b"   # 点灯色（赤）
    color_off = "#e0e0e0"  # 消灯色（グレー）
    
    html = """
    <div style='font-family:sans-serif; font-weight:bold; display:flex; align-items:center;'>
        <span style='font-size:30px; margin-right:15px;'>OUT</span>
    """
    for i in range(3):
        color = color_on if i < count else color_off
        html += f"<span style='color:{color}; font-size:50px; line-height:1; margin-right:5px;'>●</span>"
    
    html += "</div>"
    return html

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
# 0. 選手データと表示用関数の定義
# ==========================================

# 変数名を PLAYER_NUMBERS (大文字) に統一します
PLAYER_NUMBERS = {
    "佐藤蓮太": "1", "久保田剛志": "2", "開田凌空": "3", "水谷真智": "4", "河野潤樹": "5",
    "渡邉誠也": "7", "岡﨑英一": "8", "中尾建太": "10", "内藤洋輔": "11", "大高翼": "13",
    "小野拓朗": "15", "古屋翔": "17", "伊東太建": "18", "渡邉竣太": "19", "山田大貴": "21",
    "志村裕三": "23", "石田貴大": "24", "相原一博": "25", "田中伸延": "26", "坂本昂士": "27",
    "渡辺羽": "28", "石原圭佑": "29", "荒木豊": "31", "永井雄太": "33", "小野慎也": "38",
    "清水智広": "43", "名執雅叶": "51", "山縣諒介": "60", "照屋航": "63", "望月駿": "66",
    "鈴木翔大": "73",
    # 新規・背番号なし
    "名執雅楽": "", "杉山颯": "", "助っ人1": "", "助っ人2": "", "助っ人3": "", 
    "助っ人4": "", "助っ人5": "", "塚田 晴琉": "", "名執 冬雅": "", "野澤 貫太": "", 
    "山中 啓至": "", "前田 琳太郎": ""
}

# 選手リストの生成（エラーが出ていた箇所のための準備）
all_players = list(PLAYER_NUMBERS.keys())

def fmt_player_name(name):
    """選手名を受け取り、'名前 (背番号)' の形式で返す関数"""
    if not name:
        return ""
    
    # PLAYER_NUMBERS (大文字) から取得
    num = PLAYER_NUMBERS.get(name, "")
    
    if num:
        return f"{name} ({num})"
    else:
        return name  # 背番号がない場合は名前のみ
    
my_team_fixed = "KAGURA"
all_players = list(PLAYER_NUMBERS.keys())
all_positions = ["", "DH", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
# グラウンドリスト（追加分を反映）
ground_list = [
    "小瀬スポーツ公園", "緑が丘スポーツ公園", "飯田球場", "ふじでん球場",
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
        data = conn.read(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", ttl=0) # 開発中はttl=0推奨
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
    st.table(pd.DataFrame(score_dict).set_index("チーム"))

# ==========================================
# 前提：コールバック関数の定義（メイン処理の前に記述が必要）
# ==========================================
def update_bench_state():
    """ベンチメンバーの選択状態をsession_stateに保存するコールバック"""
    st.session_state["persistent_bench"] = st.session_state.bench_selection_widget

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

    if not today_batting_df.empty:
        scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"]
    else:
        scoreboard_df = today_batting_df # 空の場合はそのまま

    # render_scoreboard には、除外後の 'scoreboard_df' を渡します
    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    
    st.divider()

  # ---------------------------------------------------------
    # A. スコアのみ登録モード (KAGURA得点＆相手失点 反映版)
    # ---------------------------------------------------------
    if input_mode == "スコアのみ登録 (詳細完全不明)":
        st.warning("【注意】このモードで登録したデータは個人成績には反映されません（チーム得点として記録されます）。")
        
        with st.form("score_board_form_dropdown"):
            st.write("### 🔢 イニングスコア入力")
            st.caption("※試合がなかった回は「-」を選択してください。")

            # 選択肢リスト (先頭に "-" を追加)
            score_opts = ["-"] + list(range(31))
            
            # デフォルト値「0」のインデックス
            default_idx = score_opts.index(0)

            # --- KAGURA 入力 ---
            st.markdown("🦅 **KAGURA**")
            
            # 1〜5回
            c1, c2, c3, c4, c5 = st.columns(5)
            k_innings = []
            k_innings.append(c1.selectbox("1回", options=score_opts, index=default_idx, key="k1_d"))
            k_innings.append(c2.selectbox("2回", options=score_opts, index=default_idx, key="k2_d"))
            k_innings.append(c3.selectbox("3回", options=score_opts, index=default_idx, key="k3_d"))
            k_innings.append(c4.selectbox("4回", options=score_opts, index=default_idx, key="k4_d"))
            k_innings.append(c5.selectbox("5回", options=score_opts, index=default_idx, key="k5_d"))
            
            # 6〜9回 + H/E
            c6, c7, c8, c9, c_h, c_e = st.columns(6)
            k_innings.append(c6.selectbox("6回", options=score_opts, index=default_idx, key="k6_d"))
            k_innings.append(c7.selectbox("7回", options=score_opts, index=default_idx, key="k7_d"))
            k_innings.append(c8.selectbox("8回", options=score_opts, index=default_idx, key="k8_d"))
            k_innings.append(c9.selectbox("9回", options=score_opts, index=default_idx, key="k9_d"))
            
            # HとE
            k_hits = c_h.selectbox("安打", options=score_opts, index=default_idx, key="kh_d")
            k_err  = c_e.selectbox("失策", options=score_opts, index=default_idx, key="ke_d")

            st.divider()

            # --- 対戦相手 入力 ---
            st.markdown(f"🆚 **{opp_team}**")
            
            # 1〜5回
            c1, c2, c3, c4, c5 = st.columns(5)
            o_innings = []
            o_innings.append(c1.selectbox("1回", options=score_opts, index=default_idx, key="o1_d"))
            o_innings.append(c2.selectbox("2回", options=score_opts, index=default_idx, key="o2_d"))
            o_innings.append(c3.selectbox("3回", options=score_opts, index=default_idx, key="o3_d"))
            o_innings.append(c4.selectbox("4回", options=score_opts, index=default_idx, key="o4_d"))
            o_innings.append(c5.selectbox("5回", options=score_opts, index=default_idx, key="o5_d"))
            
            # 6〜9回 + H/E
            c6, c7, c8, c9, c_h, c_e = st.columns(6)
            o_innings.append(c6.selectbox("6回", options=score_opts, index=default_idx, key="o6_d"))
            o_innings.append(c7.selectbox("7回", options=score_opts, index=default_idx, key="o7_d"))
            o_innings.append(c8.selectbox("8回", options=score_opts, index=default_idx, key="o8_d"))
            o_innings.append(c9.selectbox("9回", options=score_opts, index=default_idx, key="o9_d"))
            
            o_hits = c_h.selectbox("安打", options=score_opts, index=default_idx, key="oh_d")
            o_err  = c_e.selectbox("失策", options=score_opts, index=default_idx, key="oe_d")
            
            st.write("")
            comment = st.text_area("試合メモ (任意)", placeholder="例: 6回コールド、日没サスペンデッドなど")
            
            submit_score = st.form_submit_button("スコアを登録する", type="primary")
            
            if submit_score:
                # --- 値の変換処理 ---
                def parse_val(v): return 0 if v == "-" else int(v)
                # 合計計算
                k_total = sum([parse_val(x) for x in k_innings])
                o_total = sum([parse_val(x) for x in o_innings])
                
                # 安打・失策
                kh_val = parse_val(k_hits); ke_val = parse_val(k_err)
                oh_val = parse_val(o_hits); oe_val = parse_val(o_err)

                # =================================================
                # 1. 打撃データ側への保存 (KAGURA得点, KAGURA安打, 相手失策)
                # =================================================
                new_batting_records = []
                
                # A. 得点の記録
                for idx, val in enumerate(k_innings):
                    if val == "-": continue
                    run = int(val)
                    inn_label = f"{idx + 1}回"
                    
                    if run > 0:
                        for _ in range(run):
                            new_batting_records.append({
                                "日付": selected_date_str, "グラウンド": ground_name, 
                                "対戦相手": opp_team, "試合種別": match_type, 
                                "イニング": inn_label, "選手名": "チーム記録", 
                                "位置": "", "結果": "得点", "打点": 0, "得点": 1, "盗塁": 0, "種別": "得点"
                            })
                    else:
                        # 0点イニングの記録
                        new_batting_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, 
                            "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", 
                            "位置": "", "結果": "ー", "打点": 0, "得点": 0, "盗塁": 0, "種別": "イニング経過"
                        })

                # B. KAGURA安打の記録 (スコアボードH用)
                for _ in range(kh_val):
                    new_batting_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                        "イニング": "試合終了", "選手名": "チーム記録", "結果": "単打", "打点":0, "得点":0, "盗塁":0, "種別": "チーム安打"
                    })

                # C. 相手失策の記録 (スコアボードE用 -> 打撃DBの「失策」数をカウントするため)
                for _ in range(oe_val):
                    new_batting_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                        "イニング": "試合終了", "選手名": "チーム記録", "結果": "失策", "打点":0, "得点":0, "盗塁":0, "種別": "相手失策"
                    })

                # メモ行
                summary_text = f"スコア登録: {k_total}-{o_total}, K安打:{kh_val} K失策:{ke_val}, 相安打:{oh_val} 相失策:{oe_val}"
                if comment: summary_text += f" / メモ: {comment}"
                
                new_batting_records.append({
                    "日付": selected_date_str, "グラウンド": ground_name, 
                    "対戦相手": opp_team, "試合種別": match_type, 
                    "イニング": "試合終了", "選手名": "チーム記録", 
                    "位置": "", "結果": "ー", "打点": 0, "得点": 0, "盗塁": 0, "種別": summary_text
                })

                # =================================================
                # 2. 投手データ側への保存 (相手得点, 相手安打, KAGURA失策)
                # =================================================
                new_pitching_records = []
                
                # A. 相手得点 (失点として記録)
                for idx, val in enumerate(o_innings):
                    if val == "-": continue
                    run = int(val)
                    inn_label = f"{idx + 1}回"
                    
                    if run > 0:
                        new_pitching_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", 
                            "結果": "失点", "失点": run, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "相手得点"
                        })
                    else:
                        new_pitching_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", 
                            "結果": "ー", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "イニング経過"
                        })

                # B. 相手安打の記録 (スコアボードH用 -> 投手DBの被安打)
                for _ in range(oh_val):
                    new_pitching_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                        "イニング": "試合終了", "選手名": "チーム記録", 
                        "結果": "単打", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "被安打"
                    })

                # C. KAGURA失策の記録 (スコアボードE用 -> 投手DBの「失策」)
                for _ in range(ke_val):
                    new_pitching_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                        "イニング": "試合終了", "選手名": "チーム記録", 
                        "結果": "失策", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "チーム失策"
                    })

                # =================================================
                # 保存実行
                # =================================================
                try:
                    if new_batting_records:
                        updated_batting_df = pd.concat([df_batting, pd.DataFrame(new_batting_records)], ignore_index=True)
                        conn.update(spreadsheet=SPREADSHEET_URL, data=updated_batting_df)
                    
                    if new_pitching_records:
                        updated_pitching_df = pd.concat([df_pitching, pd.DataFrame(new_pitching_records)], ignore_index=True)
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_pitching_df)
                    
                    st.cache_data.clear()
                    st.success(f" ✅  スコアボードに反映しました (KAGURA: {k_total} - {o_total})")
                    st.balloons()
                    
                    import time
                    time.sleep(1.0)
                    st.rerun()

                except Exception as e:
                    st.error(f"保存エラー: {e}")

    # ---------------------------------------------------------
    # B. 選手別まとめ入力モード (打順・守備・ベンチ対応版)
    # ---------------------------------------------------------
    elif input_mode == "選手別まとめ入力 (詳細不明・過去データ用)":
        st.info("複数の選手を表形式で入力します。打順・守備位置・ベンチメンバーも登録可能です。")
        st.caption("※行を追加するには表の下（または右上）の「＋」を押してください。")

        # --- 1. 選択肢の定義 ---
        player_options = [fmt_player_name(p) for p in all_players]
        number_options = [i for i in range(21)]
        pos_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控", "他"]

        # --- 2. データエディタの設定 ---
        # カラム定義（先頭に「打順」を追加）
        input_cols = [
            "打順", "選手名", "守備", "打席数", 
            "単打", "二塁打", "三塁打", "本塁打", 
            "三振", "四球", "死球", "犠打", "失策出塁", 
            "打点", "得点", "盗塁"
        ]
        
        # 初期データの作成（1番〜9番までをプリセット）
        # ユーザーが入力を始めやすいよう、最初から9行用意しておきます
        initial_data = []
        for i in range(1, 10):
            # [打順, 選手名, 守備, 打席数, (その他0...)]
            initial_data.append([i, "", "他"] + [0]*13)
            
        default_data = pd.DataFrame(initial_data, columns=input_cols)

        with st.form("bulk_batting_form_full_order"):
            
            st.markdown("##### 🏟️ 出場選手成績")
            edited_df = st.data_editor(
                default_data,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    # ▼▼▼ 打順カラムの設定 ▼▼▼
                    "打順": st.column_config.NumberColumn(
                        "打順", min_value=1, step=1, required=True, width="small"
                    ),
                    "選手名": st.column_config.SelectboxColumn(
                        "選手名", options=[""] + player_options, required=True, width="medium"
                    ),
                    "守備": st.column_config.SelectboxColumn(
                        "守備", options=pos_options, required=True, width="small"
                    ),
                    "打席数": st.column_config.SelectboxColumn("打席", options=number_options, required=True, width="small"),
                    
                    "単打": st.column_config.SelectboxColumn("単", options=number_options, width="small"),
                    "二塁打": st.column_config.SelectboxColumn("二", options=number_options, width="small"),
                    "三塁打": st.column_config.SelectboxColumn("三", options=number_options, width="small"),
                    "本塁打": st.column_config.SelectboxColumn("本", options=number_options, width="small"),
                    
                    "三振": st.column_config.SelectboxColumn("振", options=number_options, width="small"),
                    "四球": st.column_config.SelectboxColumn("四", options=number_options, width="small"),
                    "死球": st.column_config.SelectboxColumn("死", options=number_options, width="small"),
                    "犠打": st.column_config.SelectboxColumn("犠", options=number_options, width="small"),
                    "失策出塁": st.column_config.SelectboxColumn("エ", options=number_options, width="small"),
                    
                    "打点": st.column_config.SelectboxColumn("点", options=number_options, width="small"),
                    "得点": st.column_config.SelectboxColumn("得", options=number_options, width="small"),
                    "盗塁": st.column_config.SelectboxColumn("盗", options=number_options, width="small"),
                },
                key="batting_editor_full_order"
            )
            st.caption("※ 残りの打席数は自動的に「凡退」として計算されます。")
            
            st.divider()
            
            # --- ベンチ入りメンバー登録 ---
            st.markdown("##### 🚌 ベンチ入りメンバー (出場なし)")
            bench_selection = st.multiselect(
                "試合に出場しなかったベンチ入り選手を選択",
                options=all_players,
                format_func=fmt_player_name,
                key="bulk_bench_select"
            )

            submitted_bulk = st.form_submit_button("全データを登録", type="primary")

            if submitted_bulk:
                new_bulk_records = []
                error_logs = []
                registered_count = 0
                
                # --- A. 出場選手の登録 ---
                for index, row in edited_df.iterrows():
                    display_name = row["選手名"]
                    if not display_name: continue 
                    
                    # 選手名の復元
                    target_player_raw = ""
                    for p in all_players:
                        if fmt_player_name(p) == display_name:
                            target_player_raw = p
                            break
                    if not target_player_raw: target_player_raw = display_name
                    
                    # 打順と守備位置の取得
                    val_order = int(row.get("打順", 0))
                    val_pos = row.get("守備", "不明")

                    # 数値取得
                    def get_val(col_name):
                        val = row.get(col_name, 0)
                        return int(val) if val is not None else 0

                    val_pa = get_val("打席数")
                    if val_pa == 0: continue

                    val_1b = get_val("単打"); val_2b = get_val("二塁打")
                    val_3b = get_val("三塁打"); val_hr = get_val("本塁打")
                    val_so = get_val("三振"); val_bb = get_val("四球")
                    val_db = get_val("死球"); val_sac = get_val("犠打")
                    val_err = get_val("失策出塁")
                    
                    val_rbi = get_val("打点"); val_run = get_val("得点"); val_sb = get_val("盗塁")

                    hits_and_others = val_1b + val_2b + val_3b + val_hr + val_so + val_bb + val_db + val_sac + val_err
                    calc_outs = val_pa - hits_and_others

                    if calc_outs < 0:
                        error_logs.append(f"{display_name}: 合計が打席数を超えています。")
                        continue

                    # データ生成
                    def create_row(res_name, type_name="打撃"):
                        return {
                            "日付": selected_date_str, "グラウンド": ground_name, 
                            "対戦相手": opp_team, "試合種別": match_type,
                            "イニング": "まとめ入力",
                            "選手名": target_player_raw, 
                            "位置": val_pos,
                            "打順": val_order, # 打順を保存
                            "結果": res_name, 
                            "打点": 0, "得点": 0, "盗塁": 0, "種別": type_name
                        }

                    recs = []
                    for _ in range(val_1b): recs.append(create_row("単打"))
                    for _ in range(val_2b): recs.append(create_row("二塁打"))
                    for _ in range(val_3b): recs.append(create_row("三塁打"))
                    for _ in range(val_hr): recs.append(create_row("本塁打"))
                    for _ in range(val_so): recs.append(create_row("三振"))
                    for _ in range(val_bb): recs.append(create_row("四球"))
                    for _ in range(val_db): recs.append(create_row("死球"))
                    for _ in range(val_sac): recs.append(create_row("犠打"))
                    for _ in range(val_err): recs.append(create_row("失策"))
                    for _ in range(calc_outs): recs.append(create_row("凡退"))
                    
                    if recs:
                        recs[0]["打点"] = val_rbi
                        recs[0]["得点"] = val_run
                        recs[0]["盗塁"] = val_sb
                        new_bulk_records.extend(recs)
                        registered_count += 1
                
                # --- B. ベンチメンバーの登録 ---
                bench_count = 0
                for bp in bench_selection:
                    already_in = False
                    for r in new_bulk_records:
                        if r["選手名"] == bp:
                            already_in = True
                            break
                    
                    if not already_in:
                        new_bulk_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, 
                            "対戦相手": opp_team, "試合種別": match_type,
                            "イニング": "ベンチ",
                            "選手名": bp, 
                            "位置": "控", "打順": 0, # ベンチは打順0
                            "結果": "ー", "打点": 0, "得点": 0, "盗塁": 0, "種別": "ベンチ"
                        })
                        bench_count += 1

                # --- 保存処理 ---
                if error_logs:
                    for err in error_logs: st.error(err)
                
                if new_bulk_records:
                    try:
                        updated_df = pd.concat([df_batting, pd.DataFrame(new_bulk_records)], ignore_index=True)
                        conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
                        st.cache_data.clear()
                        st.success(f"✅ 出場選手 {registered_count} 名、ベンチ {bench_count} 名を登録しました。")
                    except Exception as e:
                        st.error(f"保存エラー: {e}")

   # ---------------------------------------------------------
    # C. 詳細入力モード (データ自動保存 & 完全アウト連動 & ベンチ対応)
    # ---------------------------------------------------------
    else:
        # --- 登録実行関数 (イニング自動更新機能付き) ---
        def submit_batting():
            # 1. ベンチメンバーの取得
            current_bench = st.session_state.get("persistent_bench", [])
            
            # 2. スタメン（15番まで）の収集
            new_records = []
            current_starters = []
            
            # 今回の登録で増えるアウト数をカウントする変数
            new_outs_count = 0

            for i in range(15):
                p_name = st.session_state.get(f"sn{i}")
                
                if p_name:
                    current_starters.append(p_name)
                    p_res = st.session_state.get(f"sr{i}", "---")
                    p_pos = st.session_state.get(f"sp{i}", "")
                    p_rbi = st.session_state.get(f"si{i}", 0)
                    
                    # 数値変換と種別判定
                    rbi_val = int(p_rbi)
                    run_val = 0
                    sb_val = 0
                    type_val = "打撃"
                    
                    if p_res == "本塁打":
                        run_val = 1
                    elif p_res == "得点":
                        run_val = 1; type_val = "得点"; rbi_val = 0
                    elif p_res == "盗塁":
                        sb_val = 1; type_val = "盗塁"; rbi_val = 0
                    
                    # アウト数のカウント（自動更新用）
                    if p_res in ["三振", "犠打", "凡退", "走塁死", "盗塁死"]:
                        new_outs_count += 1
                    elif p_res == "併殺打":
                        new_outs_count += 2
                    
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
                    "日付": selected_date_str, "グラウンド": ground_name,
                    "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": "ベンチ", "選手名": bench_player, "位置": "控",
                    "結果": "ー", "打点": 0, "得点": 0, "盗塁": 0, "種別": "ベンチ"
                })

            # 5. 保存実行
            if new_records:
                try:
                    updated_df = pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True)
                    conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
                    st.cache_data.clear() # キャッシュクリア
                    
                    # 入力欄クリア（結果と打点のみリセット）
                    if "saved_lineup" not in st.session_state: st.session_state["saved_lineup"] = {}
                    for i in range(15):
                        st.session_state[f"sr{i}"] = "---"
                        st.session_state["saved_lineup"][f"res_{i}"] = "---"
                        st.session_state[f"si{i}"] = 0
                        st.session_state["saved_lineup"][f"rbi_{i}"] = 0
                    
                    # イニング自動更新ロジック
                    current_inn_str = st.session_state.get("current_inn_key", "1回")
                    pre_outs = 0
                    if not today_batting_df.empty:
                        inn_df = today_batting_df[
                            (today_batting_df["イニング"] == current_inn_str) & 
                            (today_batting_df["イニング"] != "まとめ入力")
                        ]
                        o1 = len(inn_df[inn_df["結果"].isin(["三振", "犠打", "凡退", "走塁死", "盗塁死"])])
                        o2 = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                        pre_outs = (o1 + o2) % 3 
                    
                    # 合計が3以上なら更新
                    msg = f" ✅ {len(new_records)} 件のデータを登録しました"
                    if pre_outs + new_outs_count >= 3:
                        msg += " ➝ 3アウト・チェンジ"
                        next_inn = current_inn_str
                        if "回" in current_inn_str:
                            try:
                                curr_num = int(current_inn_str.replace("回", ""))
                                if curr_num < 9:
                                    next_inn = f"{curr_num + 1}回"
                                else:
                                    next_inn = "延長"
                            except:
                                pass
                        st.session_state["current_inn_key"] = next_inn
                        msg += f" (次は{next_inn}です)"
                    
                    st.success(msg)

                    # データ反映のためリラン
                    import time
                    time.sleep(0.5)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"保存エラー: {e}")
            else:
                st.warning("登録するデータがありません。")

        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        # 【修正ポイント】UIレイアウトは関数の「外（左側）」に出す
        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        
        # --- UIレイアウト ---
        st.button("登録実行", type="primary", on_click=submit_batting, use_container_width=True)
        
        st.write("")
        # --- イニングとアウトカウントの表示エリア ---
        c_inn, c_outs, _ = st.columns([1.5, 2.5, 3.5])
        
        with c_inn:
            # 現在のイニングを選択
            selected_inn = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)], key="current_inn_key")
            
        with c_outs:
            current_outs_db = 0
            if not today_batting_df.empty:
                inn_df = today_batting_df[
                    (today_batting_df["イニング"] == selected_inn) & 
                    (today_batting_df["イニング"] != "まとめ入力")
                ]
                outs_1 = len(inn_df[inn_df["結果"].isin(["三振", "犠打", "凡退", "走塁死", "盗塁死"])])
                outs_2 = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                current_outs_db = (outs_1 + outs_2) % 3
            
            # 赤丸表示
            st.markdown(render_out_indicator_3(current_outs_db), unsafe_allow_html=True)

        # スタメン入力枠
        col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]
        h_cols = st.columns(col_ratios)
        for col, label in zip(h_cols, ["打", "守備", "氏名", "結果", "打点", "成績"]):
            col.write(f"**{label}**")
            
        batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]
        player_list_with_empty = [""] + all_players
        
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}

        # スタメン入力ループ（ここを丸ごと入れ替えてください）
        for i in range(15):
            c = st.columns(col_ratios)
            c[0].write(f"{i+1}")
            
            # 初期値（index）の決定
            s_pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
            try: def_pos_ix = all_positions.index(s_pos)
            except ValueError: def_pos_ix = 0
            
            s_name = st.session_state["saved_lineup"].get(f"name_{i}", "")
            try: def_name_ix = player_list_with_empty.index(s_name)
            except ValueError: def_name_ix = 0
            
            s_res = st.session_state["saved_lineup"].get(f"res_{i}", "---")
            try: def_res_ix = batting_results.index(s_res)
            except ValueError: def_res_ix = 0
            
            s_rbi = st.session_state["saved_lineup"].get(f"rbi_{i}", 0)

            # ウィジェットの配置
            c[1].selectbox(f"p{i}", all_positions, index=def_pos_ix, key=f"sp{i}", 
                           label_visibility="collapsed", on_change=save_lineup_item, args=(i, "pos"))
            
            c[2].selectbox(f"n{i}", player_list_with_empty, index=def_name_ix, key=f"sn{i}", 
                           label_visibility="collapsed", format_func=fmt_player_name, on_change=save_lineup_item, args=(i, "name"))
            
            c[3].selectbox(f"r{i}", batting_results, index=def_res_ix, key=f"sr{i}", 
                           label_visibility="collapsed", on_change=save_lineup_item, args=(i, "res"))
            
            c[4].selectbox(f"i{i}", [0, 1, 2, 3, 4], index=int(s_rbi), key=f"si{i}", 
                           label_visibility="collapsed", on_change=save_lineup_item, args=(i, "rbi"))
            
            # ▼▼▼▼▼▼ 成績表示エリア（ここが修正ポイント） ▼▼▼▼▼▼
            if not today_batting_df.empty:
                current_name_val = st.session_state.get(f"sn{i}")
                
                if current_name_val:
                    # その選手の今日の全打席を取得（まとめ入力等は除外）
                    p_df = today_batting_df[
                        (today_batting_df["選手名"] == current_name_val) & 
                        (~today_batting_df["イニング"].isin(["まとめ入力", "ベンチ", "試合終了"]))
                    ]
                    
                    if not p_df.empty:
                        # 履歴テキスト作成 (例: 第1打席(安打) 第2打席(本塁打)...)
                        history_items = []
                        for idx, row in p_df.reset_index().iterrows():
                            # idxは0始まりなので+1して打席数にする
                            res_text = row['結果']
                            # 少し短縮表記にする（スペース節約のため）
                            if res_text == "本塁打": res_text = "本"
                            elif res_text == "三塁打": res_text = "3塁"
                            elif res_text == "二塁打": res_text = "2塁"
                            elif res_text == "単打": res_text = "安"
                            elif res_text == "三振": res_text = "振"
                            elif res_text == "四球": res_text = "四"
                            elif res_text == "死球": res_text = "死"
                            
                            history_items.append(f"{idx+1}打席({res_text})")
                        
                        # 横並びで表示
                        full_text = " ".join(history_items)
                        c[5].markdown(f"<div style='font-size:11px; line-height:1.2; word-wrap:break-word; color:#333;'>{full_text}</div>", unsafe_allow_html=True)
                    else:
                        c[5].write("")
                else:
                    c[5].write("")
            else:
                c[5].write("")

        st.divider()
        with st.expander(" 🚌  ベンチ入りメンバー (続き10名〜) を選択", expanded=True):
            st.multiselect(
                "ベンチメンバーを選択してください（スタメン以外）",
                all_players,
                default=st.session_state.get("persistent_bench", []),
                on_change=update_bench_state,
                key="bench_selection_widget",
                format_func=fmt_player_name
            )
        st.caption("※ここで選んだメンバーも「登録実行」で一緒に保存されます。")

# ==========================================
# ページ分岐: 投手成績入力 (完全統合版)
# ==========================================
elif page == "🔥 投手成績入力":
    is_kagura_top = (kagura_order == "先攻 (表)")
    
    # ---------------------------------------------------------
    # 0. 打撃入力から「現在の投手」を探すロジック
    # ---------------------------------------------------------
    current_lineup_pitcher = ""
    if "saved_lineup" in st.session_state:
        for i in range(15):
            pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
            name = st.session_state["saved_lineup"].get(f"name_{i}", "")
            if pos in ["投", "P"] and name in all_players:
                current_lineup_pitcher = name
                break
    
    # ---------------------------------------------------------
    # 1. モード選択
    # ---------------------------------------------------------
    st.markdown("### 📝 入力モード")
    input_mode_p = st.radio(
        "モードを選択してください", 
        ["詳細入力 (1球ごと)", "選手別まとめ入力 (詳細不明・過去データ用)"], 
        horizontal=True,
        key="pitching_mode_radio"
    )
    
    # スコアボード表示 (まとめ入力除外)
    if not today_batting_df.empty:
        scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"]
    else:
        scoreboard_df = today_batting_df

    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    
    st.divider()

# ---------------------------------------------------------
    # A. 詳細入力モード (レイアウト刷新・勝敗分離版)
    # ---------------------------------------------------------
    if input_mode_p == "詳細入力 (1球ごと)":
        st.info("1打席ごとの結果を入力します。勝敗（勝利・敗戦等）は画面下部で別途登録してください。")
        
        # --- 0. 相手打順管理用のセッション状態の初期化 ---
        if "opp_batter_index" not in st.session_state:
            st.session_state["opp_batter_index"] = 1
        if "opp_batter_count" not in st.session_state:
            st.session_state["opp_batter_count"] = 9

        # --- 1. 投手初期値の計算 ---
        player_list_for_select = [""] + [fmt_player_name(p) for p in all_players]
        def_p_index = 0
        if current_lineup_pitcher:
            target_str = fmt_player_name(current_lineup_pitcher)
            if target_str in player_list_for_select:
                def_p_index = player_list_for_select.index(target_str)

        # =========================================================
        #  【レイアウト変更エリア】
        # =========================================================
        
        # --- [上段] イニング ／ アウトカウント ---
        c_top1, c_top2 = st.columns([1, 1])
        
        with c_top1:
            # イニング選択
            current_inn = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)] + ["延長"], key="p_det_inn")
            
        with c_top2:
            # アウトカウント計算 & 表示
            current_outs_db = 0
            if not today_pitching_df.empty:
                p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                outs_1 = len(p_inn_df[p_inn_df["結果"].isin(["三振", "凡退", "犠打", "犠飛", "凡打"])])
                outs_2 = len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2
                current_outs_db = (outs_1 + outs_2) % 3
            # 特大アウト表示
            st.markdown(render_out_indicator_3(current_outs_db), unsafe_allow_html=True)

        st.write("") # 余白

        # --- [下段] 相手人数 ／ 相手打順 ／ 登板投手 ---
        c_mid1, c_mid2, c_mid3 = st.columns([1.2, 1.2, 2.5])
        
        with c_mid1:
            st.session_state["opp_batter_count"] = st.number_input(
                "相手打順人数", min_value=1, max_value=20, 
                value=st.session_state["opp_batter_count"]
            )
        with c_mid2:
            st.session_state["opp_batter_index"] = st.number_input(
                "現在の打順", min_value=1, max_value=st.session_state["opp_batter_count"], 
                value=st.session_state["opp_batter_index"]
            )
        with c_mid3:
            target_pitcher_disp = st.selectbox(
                "登板投手", player_list_for_select, index=def_p_index, key="p_det_name"
            )

        st.divider()

        # =========================================================
        #  結果入力フォーム (勝敗選択は削除)
        # =========================================================
        with st.form("pitching_detail_form_outs"):
            c_res, c_run = st.columns([1, 1])
            with c_res:
                st.markdown("##### ⚾ 結果")
                p_res = st.selectbox(
                    "打席結果", 
                    ["凡退", "三振", "安打", "本塁打", "四球", "死球", "犠打", "失策", "併殺打"], 
                    key="p_det_res"
                )
            with c_run:
                st.markdown("##### 👟 失点 (発生時のみ)")
                c_r, c_er = st.columns(2)
                p_runs = c_r.number_input("失点", min_value=0, step=1, key="p_det_r")
                p_er   = c_er.number_input("自責", min_value=0, step=1, key="p_det_er")

            # ※ここに勝敗ラジオボタンがありましたが削除しました

            st.write("")
            submit_detail = st.form_submit_button("登録実行", type="primary", use_container_width=True)
            
            if submit_detail:
                # バリデーション
                if not target_pitcher_disp:
                    st.error("⚠️ 投手を選択してください")
                elif p_res == "本塁打" and p_runs == 0:
                    st.error("⚠️ 本塁打の場合は、必ず失点を入力してください（1点以上）。")
                else:
                    try:
                        target_player = ""
                        for p in all_players:
                            if fmt_player_name(p) == target_pitcher_disp:
                                target_player = p
                                break
                        if not target_player: target_player = target_pitcher_disp

                        # 勝敗はここでは「ー」で固定
                        dec_val = "ー"
                        
                        current_idx = st.session_state["opp_batter_index"]
                        max_count = st.session_state["opp_batter_count"]
                        out_labels = ["無死", "一死", "二死"]
                        current_situation_label = out_labels[current_outs_db]

                        new_record = {
                            "日付": selected_date_str, 
                            "グラウンド": ground_name, 
                            "対戦相手": opp_team, 
                            "試合種別": match_type, 
                            "イニング": current_inn, 
                            "選手名": target_player,
                            "結果": p_res, 
                            "失点": p_runs, 
                            "自責点": p_er, 
                            "勝敗": dec_val, 
                            "球数": 0, 
                            "種別": f"詳細:{current_situation_label} / {current_idx}番打者"
                        }
                        
                        updated_df = pd.concat([df_pitching, pd.DataFrame([new_record])], ignore_index=True)
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_df)
                        
                        if "df_pitching" in st.session_state:
                            del st.session_state["df_pitching"]
                        st.cache_data.clear()
                        
                        st.session_state["opp_batter_index"] = (current_idx % max_count) + 1

                        # 3アウト判定 & イニング更新
                        add_outs = 0
                        if p_res in ["三振", "凡退", "犠打", "犠飛", "凡打"]: add_outs = 1
                        elif p_res == "併殺打": add_outs = 2
                        
                        msg = f"✅ {current_inn} {current_situation_label}：対 {current_idx}番打者 -> {p_res}"
                        if p_runs > 0: msg += f" (失点{p_runs})"

                        if (current_outs_db + add_outs) >= 3:
                            msg += " ➝ 3アウト・チェンジ"
                            next_inn = current_inn
                            if "回" in current_inn:
                                try:
                                    curr_num = int(current_inn.replace("回", ""))
                                    if curr_num < 9:
                                        next_inn = f"{curr_num + 1}回"
                                    else:
                                        next_inn = "延長"
                                except:
                                    pass
                            st.session_state["p_det_inn"] = next_inn
                            msg += f" (次は{next_inn}です)"
                        
                        st.success(msg)
                        import time
                        time.sleep(0.5)
                        st.rerun()

                    except Exception as e:
                        st.error(f"保存エラー: {e}")

        st.divider()

        # --- 対戦成績マトリックス ---
        st.markdown("##### 📊 投手 vs 相手打線 (対戦成績)")
        if not today_pitching_df.empty:
            matrix_data = []
            max_at_bats = 0 

            for i in range(1, st.session_state["opp_batter_count"] + 1):
                target_str = f"{i}番打者"
                batter_df = today_pitching_df[today_pitching_df["種別"].astype(str).str.contains(target_str, na=False)]
                
                results = []
                for _, row in batter_df.iterrows():
                    p_name = row.get("選手名", row.get("投手名", ""))
                    res_str = f"{row['イニング']}{row['結果']}({p_name})"
                    if row['失点'] > 0: res_str += f"★{int(row['失点'])}"
                    results.append(res_str)
                
                if len(results) > max_at_bats:
                    max_at_bats = len(results)
                
                matrix_data.append([f"{i}番"] + results)

            if matrix_data and max_at_bats > 0:
                cols = ["打順"] + [f"第{k}打席" for k in range(1, max_at_bats + 1)]
                formatted_data = []
                for row in matrix_data:
                    pad_len = (max_at_bats + 1) - len(row)
                    formatted_data.append(row + [""] * pad_len)
                
                df_matrix = pd.DataFrame(formatted_data, columns=cols)
                st.dataframe(df_matrix, hide_index=True, use_container_width=True)
            else:
                st.caption("※ まだ詳細データがありません")
        else:
            st.caption("※ データなし")

        st.divider()

        # =========================================================
        #  【新規】試合後の責任投手登録エリア
        # =========================================================
        with st.expander("🏆 試合後の責任投手登録 (勝利・敗戦・セーブ)", expanded=False):
            st.info("試合終了後に、責任投手を1人ずつ登録してください。")
            with st.form("pitcher_decision_form"):
                c_dec_p, c_dec_type = st.columns(2)
                with c_dec_p:
                    dec_pitcher = st.selectbox("対象投手", player_list_for_select, key="dec_pitcher_sel")
                with c_dec_type:
                    dec_type = st.selectbox("責任内容", ["勝利", "敗戦", "セーブ", "ホールド"], key="dec_type_sel")
                
                submit_dec = st.form_submit_button("決定を登録")
                
                if submit_dec:
                    if not dec_pitcher:
                        st.error("投手を選択してください")
                    else:
                        # 選手名復元
                        target_player = ""
                        for p in all_players:
                            if fmt_player_name(p) == dec_pitcher:
                                target_player = p
                                break
                        if not target_player: target_player = dec_pitcher
                        
                        # ラベル変換
                        d_val = "ー"
                        if dec_type == "勝利": d_val = "勝"
                        elif dec_type == "敗戦": d_val = "負"
                        elif dec_type == "セーブ": d_val = "S"
                        elif dec_type == "ホールド": d_val = "H"

                        # 勝敗のみのレコードを作成
                        dec_record = {
                            "日付": selected_date_str, 
                            "グラウンド": ground_name, 
                            "対戦相手": opp_team, 
                            "試合種別": match_type, 
                            "イニング": "試合終了", 
                            "選手名": target_player,
                            "結果": "ー", "失点": 0, "自責点": 0, 
                            "勝敗": d_val, "球数": 0, 
                            "種別": f"責任投手:{dec_type}"
                        }
                        
                        try:
                            updated_df = pd.concat([df_pitching, pd.DataFrame([dec_record])], ignore_index=True)
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_df)
                            
                            if "df_pitching" in st.session_state:
                                del st.session_state["df_pitching"]
                            st.cache_data.clear()
                            
                            st.success(f"✅ {target_player} に「{dec_type}」を記録しました。")
                            import time
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存エラー: {e}")
# ---------------------------------------------------------
    # B. 選手別まとめ入力モード (詳細不明・過去データ用)
    # ---------------------------------------------------------
    elif input_mode_p == "選手別まとめ入力 (詳細不明・過去データ用)":
        st.info("複数の投手の成績を表形式でまとめて入力します。（プルダウンで選択）")
        
        # 初期データの作成（よく使う5行分くらい用意）
        input_cols_p = [
            "投手名", "勝敗", "投球回(整数)", "投球回(端数)", "球数",
            "被安打", "被本塁打", "奪三振", "与四死球", "失点", "自責点"
        ]
        
        # テンプレートデータ作成
        initial_data_p = []
        for _ in range(5):
            initial_data_p.append(["", "ー", 0, 0, 0, 0, 0, 0, 0, 0, 0])
            
        default_df_p = pd.DataFrame(initial_data_p, columns=input_cols_p)
        
        # --- プルダウン用の選択肢リストを作成 ---
        # 球数用 (0〜200)
        options_balls = list(range(0, 201))
        # 一般成績用 (0〜50) ※必要に応じて範囲を変更してください
        options_stats = list(range(0, 51))
        
        with st.form("bulk_pitching_form"):
            st.markdown("##### 🏟️ 投手成績")
            
            # data_editorの設定
            edited_p = st.data_editor(
                default_df_p,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "投手名": st.column_config.SelectboxColumn("投手名", options=[""] + all_players, required=True),
                    "勝敗": st.column_config.SelectboxColumn("勝敗", options=["ー", "勝", "負", "S", "H"], required=True),
                    
                    # 投球回は整数のため NumberColumn のままでも良いですが、
                    # ここでは数値入力欄として残すか、必要ならSelectboxColumnに変更可。
                    # 今回は使い勝手を考慮し、回数だけは数値入力(Number)のままとしていますが、
                    # 強い要望であればここも options=list(range(0,20)) 等に変更可能です。
                    "投球回(整数)": st.column_config.NumberColumn("回", min_value=0, step=1, help="イニングの整数部分"),
                    "投球回(端数)": st.column_config.SelectboxColumn("端数", options=[0, 1, 2], help="0, 1/3, 2/3"),
                    
                    # --- 以下、全てプルダウン(Selectbox)に変更 ---
                    "球数": st.column_config.SelectboxColumn("球数", options=options_balls, width="small"),
                    "被安打": st.column_config.SelectboxColumn("被安", options=options_stats, width="small"),
                    "被本塁打": st.column_config.SelectboxColumn("被本", options=options_stats, width="small"),
                    "奪三振": st.column_config.SelectboxColumn("奪三", options=options_stats, width="small"),
                    "与四死球": st.column_config.SelectboxColumn("四死", options=options_stats, width="small"),
                    "失点": st.column_config.SelectboxColumn("失点", options=options_stats, width="small"),
                    "自責点": st.column_config.SelectboxColumn("自責", options=options_stats, width="small"),
                },
                key="pitching_bulk_editor"
            )
            
            submit_bulk_p = st.form_submit_button("全データを登録", type="primary")
            
            if submit_bulk_p:
                new_bulk_recs_p = []
                reg_count = 0
                
                for idx, row in edited_p.iterrows():
                    p_name = row["投手名"]
                    if not p_name: continue
                    
                    # 選手名復元
                    target_player = p_name 
                    
                    # 数値取得（Selectboxになっても intキャストで安全に取得可能）
                    inn_int = int(row.get("投球回(整数)", 0))
                    inn_frac = int(row.get("投球回(端数)", 0))
                    total_outs = (inn_int * 3) + inn_frac
                    
                    res_win = row.get("勝敗", "ー")
                    val_balls = int(row.get("球数", 0))
                    val_hits = int(row.get("被安打", 0))
                    val_hr = int(row.get("被本塁打", 0))
                    val_so = int(row.get("奪三振", 0))
                    val_bb = int(row.get("与四死球", 0))
                    val_runs = int(row.get("失点", 0))
                    val_er = int(row.get("自責点", 0))
                    
                    # 1行のレコードとして作成
                    rec = {
                        "日付": selected_date_str, 
                        "グラウンド": ground_name, 
                        "対戦相手": opp_team, 
                        "試合種別": match_type, 
                        "イニング": "まとめ入力", 
                        "投手名": target_player,
                        "結果": "まとめ", 
                        "勝敗": res_win,
                        "アウト数": total_outs,
                        "球数": val_balls,
                        "失点": val_runs,
                        "自責点": val_er,
                        "処理野手": "", 
                        "種別": f"被安{val_hits}/振{val_so}/四{val_bb}" # メモ用文字列
                    }
                    
                    # ベースレコード登録
                    new_bulk_recs_p.append(rec)
                    
                    # カウント用ダミーレコード（集計ロジックを騙すため奪三振数だけ行を複製）
                    for _ in range(val_so):
                        new_bulk_recs_p.append({
                            "日付": selected_date_str, "グラウンド":ground_name, "対戦相手":opp_team, "試合種別":match_type,
                            "イニング": "まとめ入力", "投手名": target_player, "結果": "三振", 
                            "失点":0, "自責点":0, "アウト数":0, "勝敗":"ー", "球数":0, "種別":"ダミー(三振)"
                        })
                    
                    reg_count += 1

                if new_bulk_recs_p:
                    try:
                        updated_df = pd.concat([df_pitching, pd.DataFrame(new_bulk_recs_p)], ignore_index=True)
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=updated_df)
                        st.cache_data.clear()
                        st.success(f"✅ 投手 {reg_count} 名のデータを登録しました。")
                        import time
                        time.sleep(1.0)
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存エラー: {e}")

# ==========================================
# ページ分岐: チーム戦績 (修正・統合版)
# ==========================================
elif page == "🏆 チーム戦績":
    st.title("🏆 チーム戦績ダッシュボード")

    # --------------------------------------------------
# 1. データ準備 & スマート集計ロジック（修正版）
# --------------------------------------------------
    if df_batting.empty and df_pitching.empty:
        st.info("データがまだありません。")
    else:
        games_map = {}

   # --- A. 打撃データから集計 ---
        df_b_work = df_batting.copy()
        df_b_work["DateStr"] = pd.to_datetime(df_b_work["日付"]).dt.strftime('%Y-%m-%d')
        
        for (d_str, opp, m_type), group in df_b_work.groupby(["DateStr", "対戦相手", "試合種別"]):
            # 1. 得点の計算（チーム記録があればそれを優先）
            team_rec_rows = group[group["選手名"] == "チーム記録"]
            if not team_rec_rows.empty:
                runs = pd.to_numeric(team_rec_rows["得点"], errors='coerce').fillna(0).sum()
                is_team_record = True
            else:
                runs = pd.to_numeric(group["得点"], errors='coerce').fillna(0).sum()
                is_team_record = False

            # 2. スタッツの計算（個人成績の積み上げ）
            individuals = group[group["選手名"] != "チーム記録"]
            
            # 初期値
            total_hits = 0
            total_ab = 0
            total_hr = 0
            total_sb = 0

            if not individuals.empty:
                # (a) 安打数・本塁打の計算
                # 「結果」列に含まれる文字列の個数（行数）をカウントします
                # ※まとめ入力機能でも、入力された数だけ行が複製されているため、この単純カウントで合致します
                s1 = len(individuals[individuals["結果"] == "単打"])
                s2 = len(individuals[individuals["結果"] == "二塁打"])
                s3 = len(individuals[individuals["結果"] == "三塁打"])
                hr = len(individuals[individuals["結果"] == "本塁打"])
                
                total_hits = s1 + s2 + s3 + hr
                total_hr = hr
                
                # (b) 盗塁の計算
                # 「盗塁」カラムの数値を合計（詳細入力・まとめ入力ともに数値が入る仕様のため）
                total_sb = pd.to_numeric(individuals["盗塁"], errors='coerce').fillna(0).sum()

                # (c) 打数(AB)の計算
                # 打数としてカウントすべき結果リスト（四死球・犠打・打撃妨害などを除く）
                ab_results = ["単打", "二塁打", "三塁打", "本塁打", "三振", "凡退", "失策", "併殺打", "野選", "振り逃げ"]
                
                # 該当する行数をカウントして打数とする
                total_ab = len(individuals[individuals["結果"].isin(ab_results)])

            # グラウンド情報
            gr = group["グラウンド"].iloc[0] if not group.empty else ""
            key = (d_str, opp, m_type)

            if key not in games_map:
                games_map[key] = {
                    "日付": d_str, "対戦相手": opp, "試合種別": m_type, "グラウンド": gr,
                    "得点": 0, "失点": 0, "打数": 0, "安打": 0, "本塁打": 0, "盗塁": 0,
                    "自責点": 0, "投球回": 0.0,
                    "has_team_record": False
                }
            
            # 計算結果を格納
            games_map[key]["得点"] = runs
            games_map[key]["打数"] = total_ab
            games_map[key]["安打"] = total_hits
            games_map[key]["本塁打"] = total_hr
            games_map[key]["盗塁"] = total_sb
            
            if is_team_record:
                games_map[key]["has_team_record"] = True

        # --- B. 投手データから集計 ---
        df_p_work = df_pitching.copy()
        df_p_work["DateStr"] = pd.to_datetime(df_p_work["日付"]).dt.strftime('%Y-%m-%d')

        for (d_str, opp, m_type), group in df_p_work.groupby(["DateStr", "対戦相手", "試合種別"]):
            # 1. 失点の計算（チーム記録優先）
            team_rec_rows = group[group["選手名"] == "チーム記録"]
            if not team_rec_rows.empty:
                runs_allowed = pd.to_numeric(team_rec_rows["失点"], errors='coerce').fillna(0).sum()
            else:
                runs_allowed = pd.to_numeric(group["失点"], errors='coerce').fillna(0).sum()

            # 2. 自責点・投球回の計算（個人成績の積み上げ）
            # 投手名または選手名でフィルタリング（チーム記録行を除外）
            if "投手名" in group.columns:
                individuals_p = group[group["投手名"] != "チーム記録"]
            else:
                individuals_p = group[group["選手名"] != "チーム記録"]

            er = 0
            outs = 0.0

            if not individuals_p.empty:
                # 自責点
                if "自責点" in individuals_p.columns:
                    er = pd.to_numeric(individuals_p["自責点"], errors='coerce').fillna(0).sum()
                
                # 投球回（アウト数 ÷ 3）
                if "アウト数" in individuals_p.columns:
                    total_outs = pd.to_numeric(individuals_p["アウト数"], errors='coerce').fillna(0).sum()
                    outs = total_outs / 3
                elif "投球回" in individuals_p.columns:
                    outs = pd.to_numeric(individuals_p["投球回"], errors='coerce').fillna(0).sum()

            key = (d_str, opp, m_type)
            if key not in games_map:
                gr = group["グラウンド"].iloc[0] if not group.empty else ""
                games_map[key] = {
                    "日付": d_str, "対戦相手": opp, "試合種別": m_type, "グラウンド": gr,
                    "得点": 0, "失点": 0, "打数": 0, "安打": 0, "本塁打": 0, "盗塁": 0,
                    "自責点": 0, "投球回": 0.0,
                    "has_team_record": False
                }
            
            # 計算結果を保存
            # 失点はチーム全体の値をセット
            games_map[key]["失点"] = runs_allowed
            # 自責点と投球回は、個人の積み上げを加算
            games_map[key]["自責点"] += er
            games_map[key]["投球回"] += outs

        # DataFrame化
        match_results = list(games_map.values())
        df_team_stats = pd.DataFrame(match_results)

        if not df_team_stats.empty:
            df_team_stats["日付"] = pd.to_datetime(df_team_stats["日付"])
            df_team_stats = df_team_stats.sort_values("日付", ascending=False)

        # --------------------------------------------------
        # 2. フィルタリング (年度・試合種別)
        # --------------------------------------------------
        if not df_team_stats.empty:
            df_team_stats["Year"] = df_team_stats["日付"].dt.year.astype(str)
            all_years = sorted(list(df_team_stats["Year"].unique()), reverse=True)
            
            c_filter1, c_filter2 = st.columns(2)
            with c_filter1:
                target_year = st.selectbox("年度", ["通算"] + all_years, key="team_stats_year")
            with c_filter2:
                # nanを除外
                types_list = [x for x in df_team_stats["試合種別"].unique() if str(x) != 'nan']
                all_types = ["全種別"] + list(types_list)
                target_type = st.selectbox("試合種別", all_types, key="team_stats_type")

            # フィルタ適用
            df_display = df_team_stats.copy()
            if target_year != "通算":
                df_display = df_display[df_display["Year"] == target_year]
            if target_type != "全種別":
                df_display = df_display[df_display["試合種別"] == target_type]
        else:
            df_display = pd.DataFrame()

        st.divider()

# --------------------------------------------------
        # 3. 集計 & メトリクス表示
        # --------------------------------------------------
        wins = 0
        losses = 0
        draws = 0
        
        # 合計用変数
        total_score = 0
        total_lost = 0
        total_ab_sum = 0  # 打数合計
        total_hits = 0    # 安打
        total_hr = 0      # 本塁打
        total_sb = 0      # 盗塁
        total_er = 0      # 自責点
        total_ip = 0.0    # 投球回

        viewer_options = []

        if not df_display.empty:
            for index, row in df_display.iterrows():
                # 勝敗・得点・失点
                s = row["得点"]
                l = row["失点"]
                total_score += s
                total_lost += l
                
                # 新しい指標の加算
                # 【修正箇所】ここで "打席" ではなく "打数" を取得します
                total_ab_sum += row.get("打数", 0) 
                
                total_hits += row.get("安打", 0)
                total_hr += row.get("本塁打", 0)
                total_sb += row.get("盗塁", 0)
                total_er += row.get("自責点", 0)
                total_ip += row.get("投球回", 0)

                res_txt = "-"
                if s > l:
                    wins += 1; res_txt = " ⚪ 勝"
                elif s < l:
                    losses += 1; res_txt = " ⚫ 敗"
                else:
                    draws += 1; res_txt = "△分"
                
                df_display.at[index, "勝敗"] = res_txt
                
                d_str = row["日付"].strftime('%Y-%m-%d')
                label = f"{d_str} vs {row['対戦相手']} ({res_txt}) - {row['試合種別']}"
                viewer_options.append(label)

        total_games = wins + losses + draws
        
        # --- 率系の計算 ---
        # 勝率
        win_pct = wins / (wins + losses) if (wins + losses) > 0 else 0.0
        
        # チーム打率 (安打 / 打数)
        team_avg = total_hits / total_ab_sum if total_ab_sum > 0 else 0.0
        
        # チーム防御率 (自責点 * 7 / 投球回)
        # ※投球回が0の場合は0.0とする
        team_era = (total_er * 7) / total_ip if total_ip > 0 else 0.0
        
        # 得点率・失点率 (1試合平均)
        runs_per_game = total_score / total_games if total_games > 0 else 0.0
        runs_allowed_per_game = total_lost / total_games if total_games > 0 else 0.0

        # --- 表示 ---
        
        # 1段目：勝敗情報
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("試合数", f"{total_games}")
        m2.metric("勝利", f"{wins}", delta="WIN")
        m3.metric("敗戦", f"{losses}", delta="-LOSE", delta_color="inverse")
        m4.metric("引分", f"{draws}")
        m5.metric("勝率", f"{win_pct:.3f}")

        st.markdown("---")
        
        # 2段目：攻撃指標
        st.markdown("#####  ⚔️  攻撃スタッツ")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("チーム打率", f"{team_avg:.3f}", help=f"{int(total_hits)}安打 / {int(total_ab_sum)}打数")
        a2.metric("平均得点", f"{runs_per_game:.2f}", delta=f"総: {int(total_score)}")
        a3.metric("本塁打数", f"{int(total_hr)} 本")
        a4.metric("盗塁数", f"{int(total_sb)} 個")

        # 3段目：守備指標
        st.markdown("#####   🛡️   守備スタッツ")
        d1, d2, d3 = st.columns(3)
        d1.metric("チーム防御率", f"{team_era:.2f}", help="自責点×7 ÷ 投球回")
        # 得点・失点も念のため int() で整数化して表示
        d2.metric("平均失点", f"{runs_allowed_per_game:.2f}", delta=f"総: {int(total_lost)}", delta_color="inverse")
        d3.metric("得失点差", f"{int(total_score - total_lost):+d}")

        # --------------------------------------------------
        # 4. 試合履歴リスト
        # --------------------------------------------------
        st.subheader(" 📋  試合履歴")
        if not df_display.empty:
            # 表示カラム整理
            cols = ["日付", "対戦相手", "得点", "失点", "勝敗", "試合種別", "グラウンド"]
            st.dataframe(
                df_display[cols],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.write("履歴データがありません")

        # --------------------------------------------------
        # 5. 試合詳細ビューワー (インデックス番号削除版)
        # --------------------------------------------------
        st.markdown("###  📝 試合詳細ビューワー")
        
        if viewer_options:
            selected_label = st.selectbox(
                "詳細を確認したい試合を選択してください", 
                viewer_options,
                key="detail_selector"
            )
            
            if selected_label:
                # ラベルから日付・相手を特定
                try:
                    parts = selected_label.split(" vs ")
                    target_date_str = parts[0]
                    rest = parts[1]
                    target_opp = rest.split(" (")[0]
                except:
                    st.error("データの特定に失敗しました。")
                    target_date_str = ""
                    target_opp = ""

                if target_date_str:
                    # メタデータ取得
                    target_row = df_display[
                        (df_display["日付"] == pd.to_datetime(target_date_str)) &
                        (df_display["対戦相手"] == target_opp)
                    ].iloc[0]
                    
                    has_team_rec = target_row["has_team_record"]
                    
                    # データ抽出
                    match_bat = df_batting[
                        (pd.to_datetime(df_batting["日付"]).dt.strftime('%Y-%m-%d') == target_date_str) & 
                        (df_batting["対戦相手"] == target_opp)
                    ].copy()
                    
                    match_pit = df_pitching[
                        (pd.to_datetime(df_pitching["日付"]).dt.strftime('%Y-%m-%d') == target_date_str) & 
                        (df_pitching["対戦相手"] == target_opp)
                    ].copy()

                    # --- A. スコアボード表示 ---
                    if has_team_rec:
                        sb_bat = match_bat[match_bat["選手名"] == "チーム記録"].copy()
                        sb_pit = match_pit[match_pit["選手名"] == "チーム記録"].copy()
                    else:
                        sb_bat = match_bat
                        sb_pit = match_pit

                    render_scoreboard(
                        sb_bat, sb_pit, 
                        target_date_str, 
                        target_row["試合種別"], 
                        target_row["グラウンド"], 
                        target_opp, 
                        is_top_first=True
                    )

                    st.divider()

                    # --- B. 打撃成績 (個人サマリー) ---
                    st.markdown("#### 🏏  打撃成績")
                    
                    # 個人成績抽出（チーム記録行を除外）
                    personal_bat = match_bat[match_bat["選手名"] != "チーム記録"].copy()
                    
                    if not personal_bat.empty:
                        # ベンチメンバー分離
                        active_mask = personal_bat["イニング"] != "ベンチ"
                        active_players = personal_bat.loc[active_mask, "選手名"].unique()
                        
                        df_active = personal_bat[
                            (personal_bat["選手名"].isin(active_players)) & 
                            (personal_bat["イニング"] != "ベンチ")
                        ].copy()
                        
                        df_bench = personal_bat[~personal_bat["選手名"].isin(active_players)].copy()

                        # 出場選手の集計
                        if not df_active.empty:
                            def summarize_batting_text(df_group):
                                df_group["打点"] = pd.to_numeric(df_group["打点"], errors='coerce').fillna(0)
                                df_group["盗塁"] = pd.to_numeric(df_group["盗塁"], errors='coerce').fillna(0)
                                
                                tpa = len(df_group)
                                hits = df_group[df_group["結果"].isin(["単打", "二塁打", "三塁打", "本塁打"])].shape[0]
                                hr = df_group[df_group["結果"] == "本塁打"].shape[0]
                                rbi = int(df_group["打点"].sum())
                                so = df_group[df_group["結果"].isin(["三振", "振り逃げ"])].shape[0]
                                bb = df_group[df_group["結果"].isin(["四球", "死球"])].shape[0]
                                sb = int(df_group["盗塁"].sum())
                                run = int(pd.to_numeric(df_group["得点"], errors='coerce').fillna(0).sum())
                                
                                order_val = 999
                                if "打順" in df_group.columns:
                                    vals = pd.to_numeric(df_group["打順"], errors='coerce').dropna()
                                    if not vals.empty: order_val = vals.min()

                                # テキスト生成
                                res_parts = []
                                if hits > 0: res_parts.append(f"安打{hits}")
                                if hr > 0: res_parts.append(f"本塁打{hr}")
                                if rbi > 0: res_parts.append(f"打点{rbi}")
                                if sb > 0: res_parts.append(f"盗塁{sb}")
                                if run > 0: res_parts.append(f"得点{run}")
                                if so > 0: res_parts.append(f"三振{so}")
                                if bb > 0: res_parts.append(f"四死球{bb}")
                                
                                summary_str = " ".join(res_parts) if res_parts else "記録なし"
                                
                                return pd.Series({
                                    "打順": order_val, 
                                    "選手名": df_group["選手名"].iloc[0],
                                    "打席": tpa,
                                    "成績詳細": summary_str
                                })

                            df_summary = df_active.groupby("選手名", sort=False).apply(summarize_batting_text).reset_index(drop=True)
                            df_summary = df_summary.sort_values("打順")
                            
                            # 打順整形
                            df_summary["打順"] = df_summary["打順"].apply(lambda x: str(int(x)) if x != 999 else "-")
                            
                            # ▼▼▼ 修正点:「打順」をインデックスに設定して表示 ▼▼▼
                            st.table(df_summary[["打順", "選手名", "打席", "成績詳細"]].set_index("打順"))
                        
                        else:
                            if not has_team_rec: st.info("出場選手の記録がありません")

                        # ベンチ入りメンバー
                        if not df_bench.empty:
                            st.write("")
                            st.markdown("##### 🚌  ベンチ入りメンバー (出場なし)")
                            bench_names = df_bench["選手名"].unique().tolist()
                            st.success(", ".join(bench_names))
                        
                    else:
                        if has_team_rec: st.caption("※ 個人打撃成績なし（スコアのみ登録）")
                        else: st.info("打撃データがありません")

                    st.write("") 

                    # --- C. 投手成績 (統合表示) ---
                    st.markdown("#### ⚾  投手成績")
                    
                    personal_pit = match_pit[match_pit["選手名"] != "チーム記録"].copy()
                    
                    if not personal_pit.empty:
                        def summarize_pitching(df_group):
                            def get_sum(col_name):
                                if col_name in df_group.columns:
                                    return pd.to_numeric(df_group[col_name], errors='coerce').fillna(0).sum()
                                return 0
                            
                            balls = get_sum("球数")
                            runs = get_sum("失点")
                            er = get_sum("自責点")
                            
                            total_hits = 0; total_so = 0; total_bb = 0
                            
                            for _, row in df_group.iterrows():
                                val_h = int(row.get("被安打", 0)) if "被安打" in row else 0
                                val_so = int(row.get("奪三振", 0)) if "奪三振" in row else 0
                                val_bb = int(row.get("与四死球", 0)) if "与四死球" in row else 0
                                res = str(row.get("結果", ""))
                                r_type = str(row.get("種別", ""))
                                
                                if res == "まとめ" or "まとめ" in str(row.get("イニング", "")):
                                    total_hits += val_h; total_so += val_so; total_bb += val_bb
                                elif "ダミー" in r_type: continue
                                else:
                                    if res in ["単打", "二塁打", "三塁打", "本塁打"]: total_hits += 1
                                    elif res in ["三振", "振り逃げ"]: total_so += 1
                                    elif res in ["四球", "死球"]: total_bb += 1
                            
                            total_outs = 0
                            if "投球回(整数)" in df_group.columns:
                                i_int = pd.to_numeric(df_group["投球回(整数)"], errors='coerce').fillna(0).sum()
                                i_frac = pd.to_numeric(df_group["投球回(端数)"], errors='coerce').fillna(0).sum()
                                total_outs += (i_int * 3) + i_frac
                            if "アウト数" in df_group.columns:
                                total_outs += pd.to_numeric(df_group["アウト数"], errors='coerce').fillna(0).sum()

                            final_inn = int(total_outs // 3)
                            final_frac = int(total_outs % 3)
                            frac_str = " 1/3" if final_frac == 1 else " 2/3" if final_frac == 2 else ""
                            display_inn = f"{final_inn}{frac_str}"
                            
                            final_res = "-"
                            if "勝敗" in df_group.columns:
                                r_str = str(df_group["勝敗"].astype(str).unique())
                                if "勝" in r_str: final_res = "勝"
                                elif "負" in r_str: final_res = "負"
                                elif "S" in r_str: final_res = "S"
                                elif "H" in r_str: final_res = "H"
                            
                            p_name = df_group["投手名"].iloc[0] if "投手名" in df_group.columns else df_group["選手名"].iloc[0]

                            return pd.Series({
                                "投手名": p_name, "結果": final_res, "回": display_inn,
                                "球数": int(balls), "被安": int(total_hits), "奪三": int(total_so),
                                "四死": int(total_bb), "失点": int(runs), "自責": int(er)
                            })

                        if "投手名" not in personal_pit.columns and "選手名" in personal_pit.columns:
                            personal_pit["投手名"] = personal_pit["選手名"]
                            
                        df_p_summary = personal_pit.groupby("投手名", sort=False).apply(summarize_pitching).reset_index(drop=True)
                        
                        # ▼▼▼ 修正点:「投手名」をインデックスに設定して表示 ▼▼▼
                        st.table(df_p_summary[["投手名", "結果", "回", "球数", "被安", "奪三", "四死", "失点", "自責"]].set_index("投手名"))

                    else:
                        if has_team_rec: st.caption("※ 個人投手成績なし（スコアのみ登録）")
                        else: st.info("投手データがありません")
        else:
            st.info("表示できる試合データがありません")

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

# ==========================================
# ページ分岐: 歴代記録 (チーム記録除外版)
# ==========================================
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
        # A. 打撃データの整形 (チーム記録除外)
        # --------------------------------------------------
        hit_cols = ["単打", "二塁打", "三塁打", "本塁打"]
        ab_cols = hit_cols + ["凡退", "失策", "走塁死", "盗塁死", "牽制死", "三振"]
        
        df_b_calc = df_batting.copy()
        
        # ▼▼▼ 修正: ランキングから「チーム記録」を除外 ▼▼▼
        df_b_calc = df_b_calc[df_b_calc["選手名"] != "チーム記録"]
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        
        df_b_calc["is_hit"] = df_b_calc["結果"].isin(hit_cols).astype(int)
        df_b_calc["is_ab"] = df_b_calc["結果"].isin(ab_cols).astype(int)
        df_b_calc["is_hr"] = (df_b_calc["結果"] == "本塁打").astype(int)
        
        for col in ["打点", "盗塁", "得点"]:
            df_b_calc[col] = pd.to_numeric(df_b_calc[col], errors='coerce').fillna(0)
            
        agg_rules_b = {
            "is_hit": "sum", "is_ab": "sum", "is_hr": "sum",
            "打点": "sum", "盗塁": "sum", "得点": "sum"
        }

        # --------------------------------------------------
        # B. 投手データの整形 (チーム記録除外)
        # --------------------------------------------------
        df_p_calc = df_pitching.copy()
        
        # ▼▼▼ 修正: ランキングから「チーム記録」を除外 ▼▼▼
        # 投手名カラムがあればそちらで判定
        if "投手名" in df_p_calc.columns:
            df_p_calc = df_p_calc[df_p_calc["投手名"] != "チーム記録"]
        # 念のため選手名カラムもチェック
        if "選手名" in df_p_calc.columns:
            df_p_calc = df_p_calc[df_p_calc["選手名"] != "チーム記録"]
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

        df_p_calc["is_so"] = (df_p_calc["結果"] == "三振").astype(int)
        df_p_calc["is_win"] = df_p_calc["勝敗"].astype(str).str.contains("勝").astype(int)
        
        agg_rules_p = {
            "アウト数": "sum", "自責点": "sum",
            "is_so": "sum", "is_win": "sum"
        }
        
        for col in ["自責点", "失点"]:
            df_p_calc[col] = pd.to_numeric(df_p_calc[col], errors='coerce').fillna(0)

        # ==================================================
        # 表示用関数（ランキング生成）
        # ==================================================
        def show_top5(title, df, sort_col, label_col, value_col, ascending=False, suffix="", format_float=False):
            st.markdown(f"##### {title}")
            sorted_df = df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
            top5 = sorted_df.head(5)
            for i, row in top5.iterrows():
                rank = i + 1
                icon = " 🥇 " if rank == 1 else " 🥈 " if rank == 2 else " 🥉 " if rank == 3 else f"{rank}."
                val = row[value_col]
                val_str = f"{val:.3f}" if format_float else f"{int(val)}"
                st.write(f"{icon} **{row[label_col]}** : {val_str}{suffix}")
            if top5.empty:
                st.write("データなし")

        # ==================================================
        # タブ切り替え
        # ==================================================
        tab_season, tab_career = st.tabs([" 📅  シーズン記録 (年度別)", " 🏅  通算記録 (歴代)"])

        # --- 1. シーズン記録 (年度×選手) ---
        with tab_season:
            c_fil1, c_fil2 = st.columns(2)
            min_ab = c_fil1.number_input("打率ランキングの最低打数", value=10, min_value=1)
            min_inn = c_fil2.number_input("防御率ランキングの最低投球回", value=5, min_value=1)
            
            season_bat = get_ranking_df(df_b_calc, ["Year", "選手名"], agg_rules_b)
            season_pit = get_ranking_df(df_p_calc, ["Year", "投手名"], agg_rules_p)
            
            # 指標計算
            season_bat["AVG"] = season_bat.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
            season_pit["Innings"] = season_pit["アウト数"] / 3
            season_pit["ERA"] = season_pit.apply(lambda x: (x["自責点"] * 9) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)
            
            season_bat["Display"] = season_bat["選手名"].astype(str) + " (" + season_bat["Year"].astype(str) + ")"
            season_pit["Display"] = season_pit["投手名"].astype(str) + " (" + season_pit["Year"].astype(str) + ")"
            
            st.markdown("####  ⚔️  打撃部門 (シーズン)")
            c1, c2, c3 = st.columns(3)
            with c1:
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
            st.markdown("####  🛡️  投手部門 (シーズン)")
            p1, p2, p3 = st.columns(3)
            with p1:
                filtered_era = season_pit[season_pit["Innings"] >= min_inn]
                show_top5("防御率", filtered_era, "ERA", "Display", "ERA", ascending=True, suffix="", format_float=False)
            with p2:
                show_top5("勝利数", season_pit, "is_win", "Display", "is_win", suffix=" 勝")
            with p3:
                show_top5("奪三振", season_pit, "is_so", "Display", "is_so", suffix=" 個")

        # --- 2. 通算記録 (選手ごと) ---
        with tab_career:
            st.caption("※チーム在籍中の全期間の合計成績です")
            
            career_bat = get_ranking_df(df_b_calc, ["選手名"], agg_rules_b)
            career_pit = get_ranking_df(df_p_calc, ["投手名"], agg_rules_p)
            
            career_bat["AVG"] = career_bat.apply(lambda x: x["is_hit"] / x["is_ab"] if x["is_ab"] > 0 else 0, axis=1)
            career_pit["Innings"] = career_pit["アウト数"] / 3
            career_pit["ERA"] = career_pit.apply(lambda x: (x["自責点"] * 9) / x["Innings"] if x["Innings"] > 0 else 99.99, axis=1)
            
            career_bat["Display"] = career_bat["選手名"].astype(str)
            career_pit["Display"] = career_pit["投手名"].astype(str)
            
            st.markdown("####  ⚔️  打撃部門 (通算)")
            tc1, tc2, tc3 = st.columns(3)
            with tc1:
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
                show_top5("通算打数", career_bat, "is_ab", "Display", "is_ab", suffix=" 打数")
            
            st.divider()
            st.markdown("####  🛡️  投手部門 (通算)")
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