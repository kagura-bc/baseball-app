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

# 自動除外対象となる不要な一時・集計列
UNNECESSARY_COLUMNS = ["Year", "year", "_date_str", "date_str", "日付_dt", "_date_dt", "_inn_num"]

@st.cache_data(ttl=60)
def get_cached_grounds(spreadsheet_url: str):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_ground = conn.read(spreadsheet=spreadsheet_url, worksheet="グラウンド登録", ttl=0)
        return df_ground["グラウンド名"].dropna().astype(str).str.strip().tolist() if "グラウンド名" in df_ground.columns else ["その他"]
    except Exception:
        return ["その他"]

@st.cache_data(ttl=60)
def get_cached_opponents(spreadsheet_url: str):
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_opp = conn.read(spreadsheet=spreadsheet_url, worksheet="相手チーム登録", ttl=0)
        return df_opp["チーム名"].dropna().astype(str).str.strip().tolist() if "チーム名" in df_opp.columns else ["その他"]
    except Exception:
        return ["その他"]

# プルダウン選択肢の基本定義
RESULT_OPTIONS = [
    "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打", 
    "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "三重殺", "振り逃げ三振", 
    "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "ボーク", "暴投", "捕逸", 
    "牽制死", "盗塁死", "盗塁", "走塁死", "スタメン", "交代", "守備変更", "ー", ""
]
INNING_OPTIONS = ["試合前"] + [f"{i}回表" for i in range(1, 19)] + [f"{i}回裏" for i in range(1, 19)] + ["延長表", "延長裏", "試合終了", "まとめ入力"]
BASE_MATCH_TYPES = ["公式戦", "練習試合", "高松宮賜杯", "天皇杯", "ミズノ杯", "会長杯", "市長杯", "東日本", "甲府市杯", "その他", ""]
POSITIONS = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "DH", "代打", "代走", "－", ""]
WIN_LOSE_OPTIONS = ["ー", "勝利", "敗戦", "セーブ", "ホールド", ""]
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
    
    if "日付" in df_clean.columns:
        df_clean["日付"] = pd.to_datetime(df_clean["日付"], errors="coerce").dt.strftime('%Y-%m-%d').fillna(df_clean["日付"].astype(str))

    for col in DB_TARGET_COLUMNS:
        if col not in df_clean.columns:
            df_clean[col] = 0 if col in ["ID", "打順", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""
            
    existing_target_cols = [col for col in DB_TARGET_COLUMNS if col in df_clean.columns]
    return df_clean[existing_target_cols]


def show_edit_page(df_batting: pd.DataFrame, df_pitching: pd.DataFrame, is_test_mode: bool = False):
    st.title("🔧 データ修正")

    target_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
    ground_list = get_cached_grounds(target_url)
    opponents_list = get_cached_opponents(target_url)

    df_batting = df_batting.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_batting.columns], errors="ignore")
    df_pitching = df_pitching.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_pitching.columns], errors="ignore")

    ALL_PLAYERS, _ = get_active_players()
    base_player_options = list(dict.fromkeys([p.strip() for p in ALL_PLAYERS if p] + [""]))

    ws_batting = "打撃成績_テスト" if is_test_mode else "打撃成績"
    ws_pitching = "投手成績_テスト" if is_test_mode else "投手成績"

    # --- ソート & 余白クレンジング処理 ---
    def prepare_sorted_df(df):
        if df.empty:
            return df.copy()
        df_work = df.copy()
        
        str_columns = [
            'イニング', '打者名', '守備位置', '結果', '打球方向', 
            '処理野手', 'エラー野手', 'ランナー状況', '投手名', 
            'グラウンド', '対戦相手', '試合種別', '勝敗', 'スコアラー'
        ]
        for col in str_columns:
            if col in df_work.columns:
                df_work[col] = df_work[col].fillna("").astype(str).str.strip()

        if "日付" in df_work.columns:
            df_work["_date_dt"] = pd.to_datetime(df_work["日付"], errors="coerce")
            df_work["_inn_num"] = df_work["イニング"].apply(extract_inning_num) if "イニング" in df_work.columns else 0
            sort_cols = ["_date_dt", "_inn_num"]
            ascending_flags = [False, False]
            if "ID" in df_work.columns:
                sort_cols.append("ID")
                ascending_flags.append(False)
                
            df_sorted = df_work.sort_values(by=sort_cols, ascending=ascending_flags)
            df_sorted["日付"] = df_sorted["_date_dt"].dt.date
            df_res = df_sorted.drop(columns=["_date_dt", "_inn_num"], errors="ignore").reset_index(drop=True)
        else:
            df_res = df_work.reset_index(drop=True)

        return df_res.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_res.columns], errors="ignore")

    df_batting_sorted = prepare_sorted_df(df_batting)
    df_pitching_sorted = prepare_sorted_df(df_pitching)

    # 🌟 DB内の実データを自動追加して選択肢外エラー（表示消え）を防ぐ関数
    def build_options(base_list, df, col_name):
        opts = list(base_list)
        if col_name in df.columns:
            existing_vals = [str(v).strip() for v in df[col_name].dropna().unique() if str(v).strip() != ""]
            for v in existing_vals:
                if v not in opts:
                    opts.append(v)
        return opts

    t1, t2 = st.tabs(["🏏 打撃データの修正", "⚾️ 投手データの修正"])

    # ========================================================
    # 🏏 打撃データ修正タブ
    # ========================================================
    with t1:
        st.subheader("打撃データの編集・削除")
        
        edit_mode_b = st.radio(
            "編集モードの選択", 
            ["📱 1件ずつ選択してフォーム修正（タブレット推奨）", "📊 テーブルで一括編集（PC推奨）"],
            key="edit_mode_b_radio",
            horizontal=True
        )

        # 🔍 フィルター
        with st.expander("🔍 データを絞り込む (日付・対戦相手・打者名)", expanded=True):
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

        df_b_filtered = df_batting_sorted.copy()
        if sel_date_b != "すべて" and "日付" in df_b_filtered.columns:
            df_b_filtered = df_b_filtered[df_b_filtered["日付"].astype(str) == sel_date_b]
        if sel_opp_b != "すべて" and "対戦相手" in df_b_filtered.columns:
            df_b_filtered = df_b_filtered[df_b_filtered["対戦相手"].astype(str) == sel_opp_b]
        if sel_player_b != "すべて" and "打者名" in df_b_filtered.columns:
            df_b_filtered = df_b_filtered[df_b_filtered["打者名"].astype(str) == sel_player_b]

        # 動的選択肢の構築
        bat_player_opts = build_options(base_player_options, df_batting_sorted, "打者名")
        bat_pitcher_opts = build_options(base_player_options, df_batting_sorted, "投手名")
        bat_scorer_opts = build_options(base_player_options, df_batting_sorted, "スコアラー")
        bat_match_opts = build_options(BASE_MATCH_TYPES, df_batting_sorted, "試合種別")
        bat_res_opts = build_options(RESULT_OPTIONS, df_batting_sorted, "結果")

        # ----------------------------------------------------
        # モード1: 📱 1件フォーム修正（タブレット向け）
        # ----------------------------------------------------
        if "📱" in edit_mode_b:
            if df_b_filtered.empty:
                st.info("該当するデータがありません。")
            else:
                df_b_filtered["_label"] = df_b_filtered.apply(
                    lambda r: f"ID:{r.get('ID','')} | {r.get('イニング','')} | 打順{r.get('打順','')} | {r.get('打者名','')} | {r.get('結果','')}", axis=1
                )
                selected_label = st.selectbox("📝 修正したいデータを選択してください", df_b_filtered["_label"].tolist(), key="select_b_row")
                
                selected_row = df_b_filtered[df_b_filtered["_label"] == selected_label].iloc[0]
                row_id = selected_row["ID"]

                st.markdown("---")
                st.markdown(f"#### ⚙️ ID: `{row_id}` の詳細編集")
                
                with st.form(key=f"form_edit_b_{row_id}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        e_date = st.date_input("日付", value=pd.to_datetime(selected_row["日付"]).date())
                        e_inn = st.selectbox("イニング", INNING_OPTIONS, index=INNING_OPTIONS.index(selected_row["イニング"]) if selected_row["イニング"] in INNING_OPTIONS else 0)
                        e_order = st.number_input("打順", min_value=1, max_value=30, value=int(selected_row["打順"]) if pd.notnull(selected_row["打順"]) and str(selected_row["打順"]).isdigit() else 1)
                        e_player = st.selectbox("打者名", bat_player_opts, index=bat_player_opts.index(selected_row["打者名"]) if selected_row["打者名"] in bat_player_opts else 0)
                        e_pos = st.selectbox("守備位置", POSITIONS, index=POSITIONS.index(selected_row["守備位置"]) if selected_row["守備位置"] in POSITIONS else 0)

                    with c2:
                        e_result = st.selectbox("結果", bat_res_opts, index=bat_res_opts.index(selected_row["結果"]) if selected_row["結果"] in bat_res_opts else 0)
                        e_dir = st.selectbox("打球方向", POSITIONS, index=POSITIONS.index(selected_row["打球方向"]) if selected_row["打球方向"] in POSITIONS else 0)
                        e_proc = st.text_input("処理野手", value=str(selected_row["処理野手"]))
                        e_err = st.selectbox("エラー野手", POSITIONS, index=POSITIONS.index(selected_row["エラー野手"]) if selected_row["エラー野手"] in POSITIONS else 0)
                        e_r_status = st.selectbox("ランナー状況", RUNNER_OPTIONS, index=RUNNER_OPTIONS.index(selected_row["ランナー状況"]) if selected_row["ランナー状況"] in RUNNER_OPTIONS else 0)

                    with c3:
                        e_rbi = st.number_input("打点", min_value=0, max_value=20, value=int(selected_row["打点"]) if pd.notnull(selected_row["打点"]) else 0)
                        e_pitcher = st.selectbox("相手投手名", bat_pitcher_opts, index=bat_pitcher_opts.index(selected_row["投手名"]) if selected_row["投手名"] in bat_pitcher_opts else 0)
                        e_ground = st.selectbox("グラウンド", ground_list, index=ground_list.index(selected_row["グラウンド"]) if selected_row["グラウンド"] in ground_list else 0)
                        e_opp = st.selectbox("対戦相手", opponents_list, index=opponents_list.index(selected_row["対戦相手"]) if selected_row["対戦相手"] in opponents_list else 0)
                        e_match_type = st.selectbox("試合種別", bat_match_opts, index=bat_match_opts.index(selected_row["試合種別"]) if selected_row["試合種別"] in bat_match_opts else 0)
                        e_scorer = st.selectbox("スコアラー", bat_scorer_opts, index=bat_scorer_opts.index(selected_row["スコアラー"]) if selected_row["スコアラー"] in bat_scorer_opts else 0)

                    btn_col1, btn_col2 = st.columns([2, 1])
                    with btn_col1:
                        submit_update = st.form_submit_button("💾 変更を保存する", type="primary", width="stretch")
                    with btn_col2:
                        submit_delete = st.form_submit_button("🗑 この行を削除する", width="stretch")

                if submit_update:
                    with st.spinner("更新中..."):
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df_work = df_batting_sorted.copy()
                        idx = df_work[df_work["ID"] == row_id].index
                        if not idx.empty:
                            df_work.loc[idx[0], "日付"] = str(e_date)
                            df_work.loc[idx[0], "イニング"] = e_inn
                            df_work.loc[idx[0], "打順"] = e_order
                            df_work.loc[idx[0], "打者名"] = e_player
                            df_work.loc[idx[0], "守備位置"] = e_pos
                            df_work.loc[idx[0], "結果"] = e_result
                            df_work.loc[idx[0], "打球方向"] = e_dir
                            df_work.loc[idx[0], "処理野手"] = e_proc
                            df_work.loc[idx[0], "エラー野手"] = e_err
                            df_work.loc[idx[0], "ランナー状況"] = e_r_status
                            df_work.loc[idx[0], "打点"] = e_rbi
                            df_work.loc[idx[0], "投手名"] = e_pitcher
                            df_work.loc[idx[0], "グラウンド"] = e_ground
                            df_work.loc[idx[0], "対戦相手"] = e_opp
                            df_work.loc[idx[0], "試合種別"] = e_match_type
                            df_work.loc[idx[0], "スコアラー"] = e_scorer

                        save_df = clean_dataframe_for_save(df_work)
                        conn.update(spreadsheet=target_url, worksheet=ws_batting, data=save_df)
                        st.cache_data.clear()
                        st.success(f"ID:{row_id} の打撃データを更新しました！")
                        time.sleep(0.5)
                        st.rerun()

                if submit_delete:
                    with st.spinner("削除中..."):
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df_work = df_batting_sorted[df_batting_sorted["ID"] != row_id].copy()
                        save_df = clean_dataframe_for_save(df_work)
                        conn.update(spreadsheet=target_url, worksheet=ws_batting, data=save_df)
                        st.cache_data.clear()
                        st.success(f"ID:{row_id} を削除しました！")
                        time.sleep(0.5)
                        st.rerun()

        # ----------------------------------------------------
        # モード2: 📊 テーブル一括編集（PC向け）
        # ----------------------------------------------------
        else:
            common_column_config_b = {
                "削除選択": st.column_config.CheckboxColumn("削除", default=False),
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD"),
                "イニング": st.column_config.SelectboxColumn("イニング", options=INNING_OPTIONS),
                "打順": st.column_config.NumberColumn("打順", min_value=1, max_value=30, step=1),
                "打者名": st.column_config.SelectboxColumn("打者名", options=bat_player_opts),
                "守備位置": st.column_config.SelectboxColumn("守備位置", options=POSITIONS),
                "結果": st.column_config.SelectboxColumn("結果", options=bat_res_opts),
                "打球方向": st.column_config.SelectboxColumn("打球方向", options=POSITIONS),
                "処理野手": st.column_config.TextColumn("処理野手"),
                "エラー野手": st.column_config.SelectboxColumn("エラー野手", options=POSITIONS),
                "ランナー状況": st.column_config.SelectboxColumn("ランナー状況", options=RUNNER_OPTIONS),
                "打点": st.column_config.NumberColumn("打点", min_value=0, max_value=10, step=1),
                "投手名": st.column_config.SelectboxColumn("投手名", options=bat_pitcher_opts),
                "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=ground_list),
                "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=opponents_list),
                "試合種別": st.column_config.SelectboxColumn("試合種別", options=bat_match_opts),
                "勝敗": st.column_config.SelectboxColumn("勝敗", options=WIN_LOSE_OPTIONS),
                "スコアラー": st.column_config.SelectboxColumn("スコアラー", options=bat_scorer_opts),
            }

            df_b_work = df_b_filtered.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_b_filtered.columns], errors="ignore")
            df_b_work.insert(0, "削除選択", False)

            edited_b = st.data_editor(
                df_b_work,
                column_config=common_column_config_b,
                width="stretch",
                key="bat_editor_final",
                hide_index=True
            )

            if st.button("チェックした行を削除 ＆ 修正内容を保存", type="primary", width="stretch", key="del_bat_btn"):
                with st.spinner("スプレッドシートを更新中..."):
                    conn = st.connection("gsheets", type=GSheetsConnection)
                    edited_valid = edited_b[edited_b["削除選択"] == False].drop(columns=["削除選択"])
                    
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
    # ⚾️ 投手データ修正タブ
    # ========================================================
    with t2:
        st.subheader("投手データの編集・削除")

        edit_mode_p = st.radio(
            "編集モードの選択", 
            ["📱 1件ずつ選択してフォーム修正（タブレット推奨）", "📊 テーブルで一括編集（PC推奨）"],
            key="edit_mode_p_radio",
            horizontal=True
        )

        with st.expander("🔍 データを絞り込む (日付・対戦相手・投手名)", expanded=True):
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

        df_p_filtered = df_pitching_sorted.copy()
        if sel_date_p != "すべて" and "日付" in df_p_filtered.columns:
            df_p_filtered = df_p_filtered[df_p_filtered["日付"].astype(str) == sel_date_p]
        if sel_opp_p != "すべて" and "対戦相手" in df_p_filtered.columns:
            df_p_filtered = df_p_filtered[df_p_filtered["対戦相手"].astype(str) == sel_opp_p]
        if sel_player_p != "すべて" and "投手名" in df_p_filtered.columns:
            df_p_filtered = df_p_filtered[df_p_filtered["投手名"].astype(str) == sel_player_p]

        pitch_p_opts = build_options(base_player_options, df_pitching_sorted, "投手名")
        pitch_b_opts = build_options(base_player_options, df_pitching_sorted, "打者名")
        pitch_scorer_opts = build_options(base_player_options, df_pitching_sorted, "スコアラー")
        pitch_match_opts = build_options(BASE_MATCH_TYPES, df_pitching_sorted, "試合種別")

        # ----------------------------------------------------
        # モード1: 📱 投手 1件フォーム修正
        # ----------------------------------------------------
        if "📱" in edit_mode_p:
            if df_p_filtered.empty:
                st.info("該当するデータがありません。")
            else:
                df_p_filtered["_label"] = df_p_filtered.apply(
                    lambda r: f"ID:{r.get('ID','')} | {r.get('日付','')} | {r.get('イニング','')} | 投手:{r.get('投手名','')} | 対戦:{r.get('打者名','')}", axis=1
                )
                selected_label_p = st.selectbox("📝 修正したいデータを選択してください", df_p_filtered["_label"].tolist(), key="select_p_row")
                
                selected_row_p = df_p_filtered[df_p_filtered["_label"] == selected_label_p].iloc[0]
                row_id_p = selected_row_p["ID"]

                st.markdown("---")
                st.markdown(f"#### ⚙️ ID: `{row_id_p}` の詳細編集")

                with st.form(key=f"form_edit_p_{row_id_p}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        e_date_p = st.date_input("日付", value=pd.to_datetime(selected_row_p["日付"]).date())
                        e_inn_p = st.selectbox("イニング", INNING_OPTIONS, index=INNING_OPTIONS.index(selected_row_p["イニング"]) if selected_row_p["イニング"] in INNING_OPTIONS else 0)
                        e_pitcher_p = st.selectbox("投手名", pitch_p_opts, index=pitch_p_opts.index(selected_row_p["投手名"]) if selected_row_p["投手名"] in pitch_p_opts else 0)
                        e_batter_p = st.selectbox("相手打者名", pitch_b_opts, index=pitch_b_opts.index(selected_row_p["打者名"]) if selected_row_p["打者名"] in pitch_b_opts else 0)

                    with c2:
                        e_pitches = st.number_input("球数", min_value=0, value=int(selected_row_p["球数"]) if pd.notnull(selected_row_p["球数"]) else 0)
                        e_strikes = st.number_input("ストライク", min_value=0, value=int(selected_row_p["ストライク"]) if pd.notnull(selected_row_p["ストライク"]) else 0)
                        e_balls = st.number_input("ボール", min_value=0, value=int(selected_row_p["ボール"]) if pd.notnull(selected_row_p["ボール"]) else 0)
                        e_fouls = st.number_input("ファール", min_value=0, value=int(selected_row_p["ファールボール"]) if pd.notnull(selected_row_p["ファールボール"]) else 0)

                    with c3:
                        e_er = st.number_input("自責点", min_value=0, value=int(selected_row_p["自責点"]) if pd.notnull(selected_row_p["自責点"]) else 0)
                        e_ground_p = st.selectbox("グラウンド", ground_list, index=ground_list.index(selected_row_p["グラウンド"]) if selected_row_p["グラウンド"] in ground_list else 0)
                        e_opp_p = st.selectbox("対戦相手", opponents_list, index=opponents_list.index(selected_row_p["対戦相手"]) if selected_row_p["対戦相手"] in opponents_list else 0)
                        e_match_p = st.selectbox("試合種別", pitch_match_opts, index=pitch_match_opts.index(selected_row_p["試合種別"]) if selected_row_p["試合種別"] in pitch_match_opts else 0)
                        e_scorer_p = st.selectbox("スコアラー", pitch_scorer_opts, index=pitch_scorer_opts.index(selected_row_p["スコアラー"]) if selected_row_p["スコアラー"] in pitch_scorer_opts else 0)

                    btn_c1, btn_c2 = st.columns([2, 1])
                    with btn_c1:
                        submit_update_p = st.form_submit_button("💾 変更を保存する", type="primary", width="stretch")
                    with btn_c2:
                        submit_delete_p = st.form_submit_button("🗑 この行を削除する", width="stretch")

                if submit_update_p:
                    with st.spinner("更新中..."):
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df_work = df_pitching_sorted.copy()
                        idx = df_work[df_work["ID"] == row_id_p].index
                        if not idx.empty:
                            df_work.loc[idx[0], "日付"] = str(e_date_p)
                            df_work.loc[idx[0], "イニング"] = e_inn_p
                            df_work.loc[idx[0], "投手名"] = e_pitcher_p
                            df_work.loc[idx[0], "打者名"] = e_batter_p
                            df_work.loc[idx[0], "球数"] = e_pitches
                            df_work.loc[idx[0], "ストライク"] = e_strikes
                            df_work.loc[idx[0], "ボール"] = e_balls
                            df_work.loc[idx[0], "ファールボール"] = e_fouls
                            df_work.loc[idx[0], "自責点"] = e_er
                            df_work.loc[idx[0], "グラウンド"] = e_ground_p
                            df_work.loc[idx[0], "対戦相手"] = e_opp_p
                            df_work.loc[idx[0], "試合種別"] = e_match_p
                            df_work.loc[idx[0], "スコアラー"] = e_scorer_p

                        save_df = clean_dataframe_for_save(df_work)
                        conn.update(spreadsheet=target_url, worksheet=ws_pitching, data=save_df)
                        st.cache_data.clear()
                        st.success(f"ID:{row_id_p} の投手データを更新しました！")
                        time.sleep(0.5)
                        st.rerun()

                if submit_delete_p:
                    with st.spinner("削除中..."):
                        conn = st.connection("gsheets", type=GSheetsConnection)
                        df_work = df_pitching_sorted[df_pitching_sorted["ID"] != row_id_p].copy()
                        save_df = clean_dataframe_for_save(df_work)
                        conn.update(spreadsheet=target_url, worksheet=ws_pitching, data=save_df)
                        st.cache_data.clear()
                        st.success(f"ID:{row_id_p} を削除しました！")
                        time.sleep(0.5)
                        st.rerun()

        # ----------------------------------------------------
        # モード2: 📊 投手 テーブル一括編集
        # ----------------------------------------------------
        else:
            common_column_config_p = {
                "削除選択": st.column_config.CheckboxColumn("削除", default=False),
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD"),
                "イニング": st.column_config.SelectboxColumn("イニング", options=INNING_OPTIONS),
                "投手名": st.column_config.SelectboxColumn("投手名", options=pitch_p_opts),
                "打者名": st.column_config.SelectboxColumn("打者名", options=pitch_b_opts),
                "自責点": st.column_config.NumberColumn("自責点", min_value=0, max_value=20, step=1),
                "球数": st.column_config.NumberColumn("球数", min_value=0, step=1),
                "ストライク": st.column_config.NumberColumn("ストライク", min_value=0, step=1),
                "ファールボール": st.column_config.NumberColumn("ファールボール", min_value=0, step=1),
                "ボール": st.column_config.NumberColumn("ボール", min_value=0, step=1),
                "グラウンド": st.column_config.SelectboxColumn("グラウンド", options=ground_list),
                "対戦相手": st.column_config.SelectboxColumn("対戦相手", options=opponents_list),
                "試合種別": st.column_config.SelectboxColumn("試合種別", options=pitch_match_opts),
                "勝敗": st.column_config.SelectboxColumn("勝敗", options=WIN_LOSE_OPTIONS),
                "スコアラー": st.column_config.SelectboxColumn("スコアラー", options=pitch_scorer_opts),
            }

            df_p_work = df_p_filtered.drop(columns=[c for c in UNNECESSARY_COLUMNS if c in df_p_filtered.columns], errors="ignore")
            df_p_work.insert(0, "削除選択", False)

            edited_p = st.data_editor(
                df_p_work,
                column_config=common_column_config_p,
                width="stretch",
                key="pitch_editor_final",
                hide_index=True
            )

            if st.button("チェックした行を削除 ＆ 修正内容を保存", type="primary", width="stretch", key="del_pitch_btn"):
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