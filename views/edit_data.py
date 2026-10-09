import time
import re
import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL
from utils.players import get_active_players

# データベースの正式な23列（打撃成績・投手成績共通）
DB_TARGET_COLUMNS = [
    'ID', '日付', 'イニング', '打順', '打者名', '守備位置', '結果', '打球方向', 
    '処理野手', 'エラー野手', 'ランナー状況', '打点', '投手名', '自責点', 
    '球数', 'ストライク', 'ファールボール', 'ボール', 'グラウンド', '対戦相手', 
    '試合種別', '勝敗', 'スコアラー'
]

# 🌟 自動除外対象となる不要な一時・集計列
UNNECESSARY_COLUMNS = ["Year", "year", "_date_str", "date_str", "日付_dt", "_date_dt", "_inn_num"]

# 🌟 キャッシュを利用したリスト取得関数（URL可変対応）
@st.cache_data(ttl=60)
def get_cached_grounds(spreadsheet_url: str):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_ground = conn.read(spreadsheet=spreadsheet_url, worksheet="グラウンド登録", ttl=0)
        return df_ground["グラウンド名"].dropna().tolist() if "グラウンド名" in df_ground.columns else ["その他"]
    except Exception:
        return ["その他"]

@st.cache_data(ttl=60)
def get_cached_opponents(spreadsheet_url: str):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_opp = conn.read(spreadsheet=spreadsheet_url, worksheet="相手チーム登録", ttl=0)
        return df_opp["チーム名"].dropna().tolist() if "チーム名" in df_opp.columns else ["その他"]
    except Exception:
        return ["その他"]

# --- 各種プルダウン用の選択肢を定義 ---
RESULT_OPTIONS = [
    "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打", 
    "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "三重殺", "振り逃げ三振", 
    "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "ボーク", "暴投", "捕逸", 
    "牽制死", "盗塁死", "盗塁", "走塁死", "スタメン", "交代", "守備変更", "ー"
]
INNING_OPTIONS = ["試合前"] + [f"{i}回表" for i in range(1, 19)] + [f"{i}回裏" for i in range(1, 19)] + ["延長表", "延長裏", "試合終了", "まとめ入力"]
MATCH_TYPES = ["公式戦", "練習試合", "その他"]
POSITIONS = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "DH", "代打", "代走", "－", ""]
WIN_LOSE_OPTIONS = ["ー", "勝利", "敗戦", "セーブ", "ホールド"]
RUNNER_OPTIONS = ["ランナーなし", "ランナー1塁", "得点圏", "満塁", "ー", ""]

def extract_inning_num(val):
    val_str = str(val)
    if "試合前" in val_str:
        return 0
    if "試合終了" in val_str or "まとめ" in val_str:
        return 999
    m = re.search(r'(\d+)', val_str)
    base_num = int(m.group(1)) * 2 if m else 50
    if "裏" in val_str:
        base_num += 1
    return base_num


def clean_dataframe_for_save(df: pd.DataFrame) -> pd.DataFrame:
    """保存用に不要列を除外・欠損列を補完し、DB_TARGET_COLUMNSに整頓する"""
    df_clean = df.copy()
    drop_cols = UNNECESSARY_COLUMNS + ["削除選択"]
    df_clean = df_clean.drop(columns=[c for c in drop_cols if c in df_clean.columns], errors="ignore")
    
    # 日付列を文字列（YYYY-MM-DD）に統一
    if "日付" in df_clean.columns:
        df_clean["日付"] = pd.to_datetime(df_clean["日付"], errors="coerce").dt.strftime('%Y-%m-%d').fillna(df_clean["日付"].astype(str))

    # DB_TARGET_COLUMNSに定義されている列を揃える
    for col in DB_TARGET_COLUMNS:
        if col not in df_clean.columns:
            df_clean[col] = 0 if col in ["ID", "打順", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""
            
    # DB_TARGET_COLUMNSの定義順にのみ並び替え（不要列を完全に除去）
    existing_target_cols = [col for col in DB_TARGET_COLUMNS if col in df_clean.columns]
    return df_clean[existing_target_cols]


def show_edit_page(df_batting: pd.DataFrame, df_pitching: pd.DataFrame, is_test_mode: bool = False):
    st.title("🔧 データ修正")

    target_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
    ground_list = get_cached_grounds(target_url)
    opponents_list = get_cached_opponents(target_url)

    # 🌟 読み込み時点でYearや_date_strなどの不要列を除外
    df_batting = df_batting.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_batting.columns], errors="ignore")
    df_pitching = df_pitching.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_pitching.columns], errors="ignore")

    # スプレッドシートから最新の選手一覧を取得
    ALL_PLAYERS, _ = get_active_players()
    player_options = list(dict.fromkeys(ALL_PLAYERS + [""]))

    # テストモード判定で書き込むシートを切り替え
    ws_batting = "打撃成績_テスト" if is_test_mode else "打撃成績"
    ws_pitching = "投手成績_テスト" if is_test_mode else "投手成績"

    # --- ソート & データ型整頓処理 ---
    def prepare_sorted_df(df):
        if df.empty:
            return df.copy()
        df_work = df.copy()
        
        # 🌟 文字列項目のデータ型を強制的にstr（文字列）に揃え、float誤認エラーを防止
        str_columns = [
            'イニング', '打者名', '守備位置', '結果', '打球方向', 
            '処理野手', 'エラー野手', 'ランナー状況', '投手名', 
            'グラウンド', '対戦相手', '試合種別', '勝敗', 'スコアラー'
        ]
        for col in str_columns:
            if col in df_work.columns:
                df_work[col] = df_work[col].fillna("").astype(str)

        if "日付" in df_work.columns:
            df_work["_date_dt"] = pd.to_datetime(df_work["日付"], errors="coerce")
            df_work["_inn_num"] = df_work["イニング"].apply(extract_inning_num) if "イニング" in df_work.columns else 0
            sort_cols = ["_date_dt", "_inn_num"]
            ascending_flags = [False, False]
            if "ID" in df_work.columns:
                sort_cols.append("ID")
                ascending_flags.append(False)
                
            df_sorted = df_work.sort_values(by=sort_cols, ascending=ascending_flags)
            
            # DateColumn用に日付をdateオブジェクト型に揃える
            df_sorted["日付"] = df_sorted["_date_dt"].dt.date
            
            # 一時ソート作業列を除外
            df_res = df_sorted.drop(columns=["_date_dt", "_inn_num"], errors="ignore").reset_index(drop=True)
        else:
            df_res = df_work.reset_index(drop=True)

        # 表示前に不要列を削除
        return df_res.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_res.columns], errors="ignore")

    df_batting_sorted = prepare_sorted_df(df_batting)
    df_pitching_sorted = prepare_sorted_df(df_pitching)

    # --- ボタンのスタイル設定 ---
    st.markdown("""
        <style>
        div.stButton > button[data-testid="stBaseButton-primary"] {
            background-color: #ff4b4b !important;
            color: white !important;
            border: none !important;
            font-weight: bold !important;
        }
        div.stButton > button[data-testid="stBaseButton-primary"]:hover {
            background-color: #ff3333 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 🌟 データベース全23列に対応した共通 column_config
    common_column_config = {
        "削除選択": st.column_config.CheckboxColumn("削除", default=False),
        "ID": st.column_config.NumberColumn("ID", disabled=True),
        "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD"),
        "イニング": st.column_config.SelectboxColumn("イニング", options=INNING_OPTIONS),
        "打順": st.column_config.NumberColumn("打順", min_value=1, max_value=30, step=1),
        "打者名": st.column_config.SelectboxColumn("打者名", options=player_options),
        "守備位置": st.column_config.SelectboxColumn("守備位置", options=POSITIONS),
        "結果": st.column_config.SelectboxColumn("結果", options=RESULT_OPTIONS),
        "打球方向": st.column_config.SelectboxColumn("打球方向", options=POSITIONS),
        "処理野手": st.column_config.TextColumn("処理野手"),
        "エラー野手": st.column_config.SelectboxColumn("エラー野手", options=POSITIONS),
        "ランナー状況": st.column_config.SelectboxColumn("ランナー状況", options=RUNNER_OPTIONS),
        "打点": st.column_config.NumberColumn("打点", min_value=0, max_value=10, step=1),
        "投手名": st.column_config.SelectboxColumn("投手名", options=player_options),
        "自責点": st.column_config.NumberColumn("自責点", min_value=0, max_value=20, step=1),
        "球数": st.column_config.NumberColumn("球数", min_value=0, step=1),
        "ストライク": st.column_config.NumberColumn("ストライク", min_value=0, step=1),
        "ファールボール": st.column_config.NumberColumn("ファールボール", min_value=0, step=1),
        "ボール": st.column_config.NumberColumn("ボール", min_value=0, step=1),
        "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=ground_list),
        "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=opponents_list),
        "試合種別": st.column_config.SelectboxColumn("試合種別", options=MATCH_TYPES),
        "勝敗": st.column_config.SelectboxColumn("勝敗", options=WIN_LOSE_OPTIONS),
        "スコアラー": st.column_config.SelectboxColumn("スコアラー", options=player_options),
    }

    t1, t2 = st.tabs(["🏏 打撃データの修正", "⚾️ 投手データの修正"])

    # ========================================================
    # 打撃データ修正タブ
    # ========================================================
    with t1:
        st.subheader("打撃データの編集・削除")

        # 🔍 データ絞り込み用フィルター
        with st.expander("🔍 データを絞り込む (日付・対戦相手・打者名)", expanded=False):
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                dates = ["すべて"] + sorted([str(d) for d in df_batting_sorted["日付"].dropna().unique()], reverse=True) if "日付" in df_batting_sorted.columns else ["すべて"]
                sel_date_b = st.selectbox("日付で絞り込み", dates, key="filter_date_b")
            with f_col2:
                opps = ["すべて"] + sorted(df_batting_sorted["対戦相手"].dropna().astype(str).unique().tolist()) if "対戦相手" in df_batting_sorted.columns else ["すべて"]
                sel_opp_b = st.selectbox("対戦相手で絞り込み", opps, key="filter_opp_b")
            with f_col3:
                p_names_b = ["すべて"] + sorted(df_batting_sorted["打者名"].dropna().astype(str).unique().tolist()) if "打者名" in df_batting_sorted.columns else ["すべて"]
                sel_player_b = st.selectbox("打者名で絞り込み", p_names_b, key="filter_player_b")

        # フィルタリング適用
        df_b_filtered = df_batting_sorted.copy()
        if sel_date_b != "すべて" and "日付" in df_b_filtered.columns:
            df_b_filtered = df_b_filtered[df_b_filtered["日付"].astype(str) == sel_date_b]
        if sel_opp_b != "すべて" and "対戦相手" in df_b_filtered.columns:
            df_b_filtered = df_b_filtered[df_b_filtered["対戦相手"].astype(str) == sel_opp_b]
        if sel_player_b != "すべて" and "打者名" in df_b_filtered.columns:
            df_b_filtered = df_b_filtered[df_b_filtered["打者名"].astype(str) == sel_player_b]

        # 不要列を除外して編集用データフレームを作成
        df_b_work = df_b_filtered.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_b_filtered.columns], errors="ignore")
        df_b_work.insert(0, "削除選択", False)

        edited_b = st.data_editor(
            df_b_work,
            column_config=common_column_config,
            use_container_width=True,
            key="bat_editor_final",
            hide_index=True
        )

        if st.button("チェックした行を削除 ＆ 修正内容を保存", type="primary", use_container_width=True, key="del_bat_btn"):
            with st.spinner("スプレッドシートを更新中..."):
                conn = st.connection("gsheets", type=GSheetsConnection)
                
                # 削除チェックが入っていない変更後データ
                edited_valid = edited_b[edited_b["削除選択"] == False].drop(columns=["削除選択"])
                
                # IDに基づいて元データフレームにマージ（絞り込み表示対応）
                if "ID" in df_batting_sorted.columns and "ID" in edited_b.columns:
                    target_ids = edited_b["ID"].tolist()
                    df_untouched = df_batting_sorted[~df_batting_sorted["ID"].isin(target_ids)]
                    final_df = pd.concat([df_untouched, edited_valid], ignore_index=True)
                else:
                    final_df = edited_valid

                save_df = clean_dataframe_for_save(final_df)
                
                conn.update(spreadsheet=target_url, worksheet=ws_batting, data=save_df)
                st.cache_data.clear()
                st.success("打撃データを更新しました！")
                time.sleep(0.5)
                st.rerun()

    # ========================================================
    # 投手データ修正タブ
    # ========================================================
    with t2:
        st.subheader("投手データの編集・削除")

        # 🔍 データ絞り込み用フィルター
        with st.expander("🔍 データを絞り込む (日付・対戦相手・投手名)", expanded=False):
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                dates_p = ["すべて"] + sorted([str(d) for d in df_pitching_sorted["日付"].dropna().unique()], reverse=True) if "日付" in df_pitching_sorted.columns else ["すべて"]
                sel_date_p = st.selectbox("日付で絞り込み", dates_p, key="filter_date_p")
            with f_col2:
                opps_p = ["すべて"] + sorted(df_pitching_sorted["対戦相手"].dropna().astype(str).unique().tolist()) if "対戦相手" in df_pitching_sorted.columns else ["すべて"]
                sel_opp_p = st.selectbox("対戦相手で絞り込み", opps_p, key="filter_opp_p")
            with f_col3:
                p_names_p = ["すべて"] + sorted(df_pitching_sorted["投手名"].dropna().astype(str).unique().tolist()) if "投手名" in df_pitching_sorted.columns else ["すべて"]
                sel_player_p = st.selectbox("投手名で絞り込み", p_names_p, key="filter_player_p")

        # フィルタリング適用
        df_p_filtered = df_pitching_sorted.copy()
        if sel_date_p != "すべて" and "日付" in df_p_filtered.columns:
            df_p_filtered = df_p_filtered[df_p_filtered["日付"].astype(str) == sel_date_p]
        if sel_opp_p != "すべて" and "対戦相手" in df_p_filtered.columns:
            df_p_filtered = df_p_filtered[df_p_filtered["対戦相手"].astype(str) == sel_opp_p]
        if sel_player_p != "すべて" and "投手名" in df_p_filtered.columns:
            df_p_filtered = df_p_filtered[df_p_filtered["投手名"].astype(str) == sel_player_p]

        # 不要列を除外して編集用データフレームを作成
        df_p_work = df_p_filtered.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_p_filtered.columns], errors="ignore")
        df_p_work.insert(0, "削除選択", False)

        edited_p = st.data_editor(
            df_p_work,
            column_config=common_column_config,
            use_container_width=True,
            key="pitch_editor_final",
            hide_index=True
        )

        if st.button("チェックした行を削除 ＆ 修正内容を保存", type="primary", use_container_width=True, key="del_pitch_btn"):
            with st.spinner("スプレッドシートを更新中..."):
                conn = st.connection("gsheets", type=GSheetsConnection)
                
                edited_valid = edited_p[edited_p["削除選択"] == False].drop(columns=["削除選択"])
                
                if "ID" in df_pitching_sorted.columns and "ID" in edited_p.columns:
                    target_ids = edited_p["ID"].tolist()
                    df_untouched = df_pitching_sorted[~df_pitching_sorted["ID"].isin(target_ids)]
                    final_df = pd.concat([df_untouched, edited_valid], ignore_index=True)
                else:
                    final_df = edited_valid

                save_df = clean_dataframe_for_save(final_df)

                conn.update(spreadsheet=target_url, worksheet=ws_pitching, data=save_df)
                st.cache_data.clear()
                st.success("投手データを更新しました！")
                time.sleep(0.5)
                st.rerun()