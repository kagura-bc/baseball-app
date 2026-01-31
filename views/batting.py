import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import ALL_PLAYERS, ALL_POSITIONS, SPREADSHEET_URL, PLAYER_NUMBERS
from utils.ui import render_scoreboard, render_out_indicator_3, show_homerun_effect, fmt_player_name

# --- コールバック関数 (入力状態の保存用) ---
def save_lineup_item(i, item_type):
    """
    入力内容が変更された瞬間に、データを永続保存領域(saved_lineup)に記録する
    """
    if "saved_lineup" not in st.session_state:
        st.session_state["saved_lineup"] = {}
        
    prefix_map = {"pos": "sp", "name": "sn", "res": "sr", "rbi": "si"}
    widget_key = f"{prefix_map[item_type]}{i}"
    
    if widget_key in st.session_state:
        val = st.session_state[widget_key]
        st.session_state["saved_lineup"][f"{item_type}_{i}"] = val

def update_bench_state():
    """ベンチメンバーの選択状態をsession_stateに保存するコールバック"""
    st.session_state["persistent_bench"] = st.session_state.bench_selection_widget

# --- ヘルパー関数 ---
def local_fmt(name):
    """configのPLAYER_NUMBERSを使って名前を整形するローカル関数"""
    return fmt_player_name(name, PLAYER_NUMBERS)

# ==========================================
# メイン表示関数
# ==========================================
def show_batting_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order):
    conn = st.connection("gsheets", type=GSheetsConnection)
    is_kagura_top = (kagura_order == "先攻 (表)")

    # フィルタリング (スコアボード表示用)
    # 日付型を文字列に変換して比較
    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str]

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
        scoreboard_df = today_batting_df

    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    
    st.divider()

    # ---------------------------------------------------------
    # A. スコアのみ登録モード
    # ---------------------------------------------------------
    if input_mode == "スコアのみ登録 (詳細完全不明)":
        st.warning("【注意】このモードで登録したデータは個人成績には反映されません（チーム得点として記録されます）。")
        
        with st.form("score_board_form_dropdown"):
            st.write("### 🔢 イニングスコア入力")
            score_opts = ["-", "✖"] + list(range(31))
            default_idx = score_opts.index(0)

            # KAGURA
            st.markdown("🦅 **KAGURA**")
            k_cols = st.columns(9)
            k_innings = [k_cols[i].selectbox(f"{i+1}回", score_opts, index=default_idx, key=f"k{i+1}_d") for i in range(9)]
            
            c_h, c_e = st.columns(2)
            k_hits = c_h.selectbox("KAGURA 安打", score_opts, index=default_idx, key="kh_d")
            k_err  = c_e.selectbox("KAGURA 失策", score_opts, index=default_idx, key="ke_d")

            st.divider()

            # 相手
            st.markdown(f"🆚 **{opp_team}**")
            o_cols = st.columns(9)
            o_innings = [o_cols[i].selectbox(f"{i+1}回", score_opts, index=default_idx, key=f"o{i+1}_d") for i in range(9)]

            c_h2, c_e2 = st.columns(2)
            o_hits = c_h2.selectbox("相手 安打", score_opts, index=default_idx, key="oh_d")
            o_err  = c_e2.selectbox("相手 失策", score_opts, index=default_idx, key="oe_d")
            
            st.write("")
            comment = st.text_area("試合メモ (任意)")
            
            submit_score = st.form_submit_button("スコアを登録する", type="primary")
            
            if submit_score:
                # (簡易化のためロジック省略なしで実装)
                def parse_val(v): return 0 if v in ["-", "✖"] else int(v)
                
                new_batting_records = []
                new_pitching_records = []

                # KAGURA得点保存
                for idx, val in enumerate(k_innings):
                    if val == "-": continue
                    inn_label = f"{idx + 1}回"
                    if val == "✖":
                        new_batting_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", "位置": kagura_order, "結果": "✖", "打点":0, "得点":0, "盗塁":0, "種別": "打ち切り"
                        })
                        continue
                    run = int(val)
                    if run > 0:
                        for _ in range(run):
                            new_batting_records.append({
                                "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                                "イニング": inn_label, "選手名": "チーム記録", "位置": kagura_order, "結果": "得点", "打点":0, "得点":1, "盗塁":0, "種別": "得点"
                            })
                    else:
                        new_batting_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", "位置": kagura_order, "結果": "ー", "打点":0, "得点":0, "盗塁":0, "種別": "イニング経過"
                        })

                # 相手得点保存
                for idx, val in enumerate(o_innings):
                    if val == "-": continue
                    inn_label = f"{idx + 1}回"
                    if val == "✖":
                         new_pitching_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", "結果": "✖", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "打ち切り"
                        })
                         continue
                    run = int(val)
                    if run > 0:
                        new_pitching_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", "結果": "失点", "失点": run, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "相手得点"
                        })
                    else:
                        new_pitching_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, 
                            "イニング": inn_label, "選手名": "チーム記録", "結果": "ー", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "イニング経過"
                        })
                
                # 安打・失策・メモ保存 (メタデータ)
                kh_val = parse_val(k_hits); ke_val = parse_val(k_err)
                oh_val = parse_val(o_hits); oe_val = parse_val(o_err)
                
                # 安打・失策をダミーレコードとして追加
                for _ in range(kh_val): new_batting_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "単打", "打点":0, "得点":0, "盗塁":0, "種別": "チーム安打"})
                for _ in range(oe_val): new_batting_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "失策", "打点":0, "得点":0, "盗塁":0, "種別": "相手失策"})
                for _ in range(oh_val): new_pitching_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "単打", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "被安打"})
                for _ in range(ke_val): new_pitching_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "失策", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "チーム失策"})

                # 保存実行
                try:
                    if new_batting_records:
                        conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(new_batting_records)], ignore_index=True))
                    if new_pitching_records:
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, pd.DataFrame(new_pitching_records)], ignore_index=True))
                    
                    st.cache_data.clear()
                    st.success("✅ スコアボードに反映しました")
                    import time
                    time.sleep(1.0)
                    st.rerun()
                except Exception as e:
                    st.error(f"保存エラー: {e}")

    # ---------------------------------------------------------
    # B. 選手別まとめ入力モード
    # ---------------------------------------------------------
    elif input_mode == "選手別まとめ入力 (詳細不明・過去データ用)":                             
        st.info("複数の選手を表形式で入力します。")
        st.caption("※行を追加するには表の下（または右上）の「＋」を押してください。")

        # --- 1. 選択肢の定義 ---
        player_options = [fmt_player_name(p,PLAYER_NUMBERS) for p in ALL_PLAYERS]
        number_options = [i for i in range(21)]
        pos_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控", "他"]

        # テンプレートデータ
        initial_data = []
        for i in range(1, 16):
            initial_data.append([i, "", "他"] + [0]*13)
        
        input_cols = ["打順", "選手名", "守備", "打席数", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策出塁", "打点", "得点", "盗塁"]
        default_data = pd.DataFrame(initial_data, columns=input_cols)
        
        with st.form("bulk_batting_form"):
            edited_df = st.data_editor(
                default_data, num_rows="dynamic", use_container_width=True,
                column_config={
                    "選手名": st.column_config.SelectboxColumn("選手名", options=[""] + [local_fmt(p) for p in ALL_PLAYERS], width="medium"),
                    "守備": st.column_config.SelectboxColumn("守備", options=["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控", "他"]),
                    "打席数": st.column_config.SelectboxColumn("打席", options=number_options),
                    "単打": st.column_config.SelectboxColumn("単", options=number_options),
                    "二塁打": st.column_config.SelectboxColumn("二", options=number_options),
                    "三塁打": st.column_config.SelectboxColumn("三", options=number_options),
                    "本塁打": st.column_config.SelectboxColumn("本", options=number_options),
                    "三振": st.column_config.SelectboxColumn("振", options=number_options),
                    "四球": st.column_config.SelectboxColumn("四", options=number_options),
                    "死球": st.column_config.SelectboxColumn("死", options=number_options),
                    "犠打": st.column_config.SelectboxColumn("犠", options=number_options),
                    "失策出塁": st.column_config.SelectboxColumn("失策", options=number_options),
                    "打点": st.column_config.SelectboxColumn("点", options=number_options),
                    "得点": st.column_config.SelectboxColumn("得", options=number_options),
                    "盗塁": st.column_config.SelectboxColumn("盗", options=number_options),
                }
            )
            
            bench_selection = st.multiselect("ベンチ入りメンバー", ALL_PLAYERS, format_func=local_fmt)
            submitted_bulk = st.form_submit_button("全データを登録")

            if submitted_bulk:
                new_bulk_records = []
                # 出場選手
                for _, row in edited_df.iterrows():
                    d_name = row["選手名"]
                    if not d_name: continue
                    
                    # 名前復元 (簡易ロジック: カッコの前を取得)
                    real_name = d_name.split(" (")[0] if "(" in d_name else d_name
                    
                    pa = int(row.get("打席数", 0))
                    if pa == 0: continue
                    
                    # 各数値を int に変換して取得
                    vals = {k: int(row.get(k, 0)) for k in ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策出塁", "打点", "得点", "盗塁"]}
                    
                    hits_outs = vals["単打"]+vals["二塁打"]+vals["三塁打"]+vals["本塁打"]+vals["三振"]+vals["四球"]+vals["死球"]+vals["犠打"]+vals["失策出塁"]
                    calc_outs = pa - hits_outs
                    
                    def create_rec(res):
                        return {"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "まとめ入力", "選手名": real_name, "位置": row.get("守備", "他"), "打順": int(row.get("打順", 0)), "結果": res, "打点":0, "得点":0, "盗塁":0, "種別": "打撃"}

                    recs = []
                    for _ in range(vals["単打"]): recs.append(create_rec("単打"))
                    for _ in range(vals["二塁打"]): recs.append(create_rec("二塁打"))
                    for _ in range(vals["三塁打"]): recs.append(create_rec("三塁打"))
                    for _ in range(vals["本塁打"]): recs.append(create_rec("本塁打"))
                    for _ in range(vals["三振"]): recs.append(create_rec("三振"))
                    for _ in range(vals["四球"]): recs.append(create_rec("四球"))
                    for _ in range(vals["死球"]): recs.append(create_rec("死球"))
                    for _ in range(vals["犠打"]): recs.append(create_rec("犠打"))
                    for _ in range(vals["失策出塁"]): recs.append(create_rec("失策"))
                    for _ in range(calc_outs): recs.append(create_rec("凡退"))
                    
                    if recs:
                        recs[0]["打点"] = vals["打点"]
                        recs[0]["得点"] = vals["得点"]
                        recs[0]["盗塁"] = vals["盗塁"]
                        new_bulk_records.extend(recs)

                # ベンチ
                for bp in bench_selection:
                    new_bulk_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": "ベンチ", "選手名": bp, "位置": "控", "結果": "ー", "打点":0, "得点":0, "盗塁":0, "種別": "ベンチ"
                    })

                # メタデータ (先攻/後攻)
                new_bulk_records.append({
                    "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": "試合情報", "選手名": "チーム記録", "位置": kagura_order, "結果": "ー", "打点":0, "得点":0, "盗塁":0, "種別": "メタデータ"
                })

                if new_bulk_records:
                    conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(new_bulk_records)], ignore_index=True))
                    st.cache_data.clear()
                    st.success("✅ データ登録完了")
                    st.rerun()

    # ---------------------------------------------------------
    # C. 詳細入力モード (メイン機能)
    # ---------------------------------------------------------
    else:
        # --- 0. セッションステートの初期化 (KeyError対策) ---
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}
        if "persistent_bench" not in st.session_state:
            st.session_state["persistent_bench"] = []

        # --- 1. データの前処理 (成績計算・本日データの抽出) ---
        current_season_stats = {}
        today_batting_df = pd.DataFrame()
        
        if not df_batting.empty:
            # 日付比較を安全にするため標準化
            df_batting_proc = df_batting.copy()
            df_batting_proc["standard_date"] = pd.to_datetime(df_batting_proc["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            
            # 本日のデータ抽出 (成績欄用)
            today_batting_df = df_batting_proc[df_batting_proc["standard_date"] == selected_date_str].copy()
            
            # 今シーズンの通算成績計算 (表示用)
            try:
                target_year = pd.to_datetime(selected_date_str).year
                df_season = df_batting_proc[pd.to_datetime(df_batting_proc["日付"], errors='coerce').dt.year == target_year]
                
                no_ab_list = ["四球", "死球", "犠打", "打撃妨害", "盗塁", "得点", "走塁死", "盗塁死", "牽制死", "スタメン", "ベンチ", "試合情報", "---", "守備交代"]
                hit_list = ["単打", "二塁打", "三塁打", "本塁打", "安打"]
                
                for p in ALL_PLAYERS:
                    p_df = df_season[df_season["選手名"] == p]
                    if not p_df.empty:
                        hits = p_df[p_df["結果"].isin(hit_list)].shape[0]
                        abs_count = p_df[~p_df["結果"].isin(no_ab_list)].shape[0]
                        hr_count = p_df[p_df["結果"] == "本塁打"].shape[0]
                        rbi_count = pd.to_numeric(p_df["打点"], errors='coerce').fillna(0).sum()
                        avg = hits / abs_count if abs_count > 0 else 0.0
                        current_season_stats[p] = f".{int(avg*1000):03d} ({hr_count}本 {int(rbi_count)}点)"
            except:
                pass

        # --- 2. 統合登録ロジックの定義 ---
        def submit_everything():
            new_records = []
            has_homerun = False
            
            # フォーム内の値をセッションにバックアップ (リロード対策)
            st.session_state["persistent_bench"] = st.session_state.get("bench_selection_widget", [])
            for i in range(15):
                st.session_state["saved_lineup"][f"pos_{i}"] = st.session_state.get(f"sp{i}")
                st.session_state["saved_lineup"][f"name_{i}"] = st.session_state.get(f"sn{i}")

            # 「結果」が1つでも入力されているかチェック
            is_play_mode = any(st.session_state.get(f"sr{i}", "---") != "---" for i in range(15))

            for i in range(15):
                p_name = st.session_state.get(f"sn{i}")
                p_pos = st.session_state.get(f"sp{i}", "")
                p_res = st.session_state.get(f"sr{i}", "---")
                p_rbi = int(st.session_state.get(f"si{i}", 0))

                if p_name:
                    if is_play_mode:
                        # A. プレイ記録モード (結果がある行のみ登録)
                        if p_res != "---":
                            run_val = 1 if p_res in ["本塁打", "得点"] else 0
                            sb_val = 1 if p_res == "盗塁" else 0
                            type_val = "打撃"
                            if p_res == "得点": type_val = "得点"
                            if p_res == "盗塁": type_val = "盗塁"
                            if p_res == "本塁打": has_homerun = True
                            
                            new_records.append({
                                "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                                "イニング": st.session_state.get("current_inn_key", "1回"), "選手名": p_name, "位置": p_pos, "打順": i+1,
                                "結果": p_res, "打点": p_rbi, "得点": run_val, "盗塁": sb_val, "種別": type_val
                            })
                    else:
                        # B. スタメン登録モード (結果が全て空の時、名前がある人を全員登録)
                        new_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                            "イニング": "試合開始", "選手名": p_name, "位置": p_pos, "打順": i+1,
                            "結果": "スタメン", "打点": 0, "得点": 0, "盗塁": 0, "種別": "スタメン"
                        })

            if new_records:
                try:
                    conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True))
                    st.cache_data.clear()
                    
                    # 登録成功後、結果入力欄のみリセット
                    for i in range(15):
                        st.session_state[f"sr{i}"] = "---"
                        st.session_state[f"si{i}"] = 0
                    
                    if has_homerun: st.session_state["show_homerun_flg"] = True
                    st.success(f"✅ {len(new_records)}件のデータを保存しました")
                    import time
                    time.sleep(1.0)
                    st.rerun()
                except Exception as e:
                    st.error(f"保存エラー: {e}")

        # --- 3. UI構築 ---
        if st.session_state.get("show_homerun_flg"):
            show_homerun_effect()
            import time
            time.sleep(3.5)
            st.session_state["show_homerun_flg"] = False
            st.rerun()

        with st.form(key='batting_form', clear_on_submit=False):
            # ボタン集約：上部の登録ボタン
            if st.form_submit_button("登録実行 (打席・スタメン一括保存)", type="primary", use_container_width=True):
                submit_everything()

            # イニング・アウトカウント
            c_inn, c_outs, _ = st.columns([1.5, 2.5, 3.5])
            with c_inn:
                st.selectbox("イニング", [f"{i}回" for i in range(1, 10)] + ["延長"], key="current_inn_key")
            with c_outs:
                current_outs_db = 0
                if not today_batting_df.empty:
                    # 本日のイニング別アウト数計算
                    inn_df = today_batting_df[today_batting_df["イニング"] == st.session_state.get("current_inn_key", "1回")]
                    o1 = len(inn_df[inn_df["結果"].isin(["三振", "犠打", "凡退", "走塁死", "盗塁死"])])
                    o2 = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                    current_outs_db = (o1 + o2) % 3
                st.markdown(render_out_indicator_3(current_outs_db), unsafe_allow_html=True)

            # テーブル見出し
            batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]
            player_list_with_empty = [""] + ALL_PLAYERS
            col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]
            h_cols = st.columns(col_ratios)
            for col, label in zip(h_cols, ["打", "守備", "氏名", "結果", "打点", "成績"]): col.write(f"**{label}**")

            # 15行の入力行
            for i in range(15):
                c = st.columns(col_ratios)
                c[0].write(f"{i+1}")
                
                # KeyError対策済みの初期値取得
                s_pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
                s_name = st.session_state["saved_lineup"].get(f"name_{i}", "")
                def_pos_ix = ALL_POSITIONS.index(s_pos) if s_pos in ALL_POSITIONS else 0
                def_name_ix = player_list_with_empty.index(s_name) if s_name in player_list_with_empty else 0
                
                c[1].selectbox(f"p{i}", ALL_POSITIONS, index=def_pos_ix, key=f"sp{i}", label_visibility="collapsed")
                c[2].selectbox(f"n{i}", player_list_with_empty, index=def_name_ix, key=f"sn{i}", label_visibility="collapsed", format_func=local_fmt)
                
                # 通算成績表示
                sel_p_name = st.session_state.get(f"sn{i}")
                if sel_p_name and sel_p_name in current_season_stats:
                    c[2].markdown(f"<div style='font-size:12px; color:#1e3a8a; margin-top:-5px;'>{current_season_stats[sel_p_name]}</div>", unsafe_allow_html=True)

                c[3].selectbox(f"r{i}", batting_results, key=f"sr{i}", label_visibility="collapsed")
                c[4].selectbox(f"i{i}", [0, 1, 2, 3, 4], key=f"si{i}", label_visibility="collapsed")

                # --- 本日の結果履歴表示 ---
                if not today_batting_df.empty and sel_p_name:
                    p_df = today_batting_df[
                        (today_batting_df["選手名"] == sel_p_name) & 
                        (~today_batting_df["イニング"].isin(["まとめ入力", "ベンチ", "試合情報"])) &
                        (~today_batting_df["結果"].isin(["スタメン"]))
                    ]
                    
                    if not p_df.empty:
                        history_html = []
                        pa_list = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "併殺打"]
                        count = 0
                        for _, row in p_df.iterrows():
                            res = row['結果']
                            # 打点数を取得（数値に変換）
                            rbi = int(pd.to_numeric(row['打点'], errors='coerce') or 0)
                            
                            short = {"本塁打":"本", "三塁打":"3塁", "二塁打":"2塁", "単打":"安", "三振":"振"}.get(res, res)
                            
                            if res in pa_list:
                                count += 1
                                # 打点がある場合は赤字にする
                                if rbi > 0:
                                    # タイムリー：赤色・太字、打点を( )で付与
                                    display_text = f"<span style='color:red; font-weight:bold;'>{count}({short}{rbi})</span>"
                                else:
                                    # 通常：黒色
                                    display_text = f"<span>{count}({short})</span>"
                                history_html.append(display_text)
                            else:
                                # 得点や盗塁など
                                history_html.append(f"({short})")
                        
                        # 結合して表示（文字サイズ大きく設定）
                        c[5].markdown(f"<div style='font-size:20px; line-height:1.5;'>{' '.join(history_html)}</div>", unsafe_allow_html=True)
                    else:
                        c[5].write("")
                else:
                    c[5].write("")

            st.divider()
            with st.expander(" 🚌  ベンチ入りメンバー", expanded=True):
                st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)
            