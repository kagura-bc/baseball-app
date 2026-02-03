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
                # (簡易化のためロジック省略)
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
                
                # 安打・失策・メモ保存
                kh_val = parse_val(k_hits); ke_val = parse_val(k_err)
                oh_val = parse_val(o_hits); oe_val = parse_val(o_err)
                
                for _ in range(kh_val): new_batting_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "単打", "打点":0, "得点":0, "盗塁":0, "種別": "チーム安打"})
                for _ in range(oe_val): new_batting_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "失策", "打点":0, "得点":0, "盗塁":0, "種別": "相手失策"})
                for _ in range(oh_val): new_pitching_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "単打", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "被安打"})
                for _ in range(ke_val): new_pitching_records.append({"日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "試合終了", "選手名": "チーム記録", "結果": "失策", "失点": 0, "自責点": 0, "勝敗": "ー", "球数": 0, "種別": "チーム失策"})

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
        number_options = [i for i in range(21)]
        
        input_cols = ["打順", "選手名", "守備", "打席数", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策出塁", "打点", "得点", "盗塁"]
        initial_data = []
        for i in range(1, 16):
            initial_data.append([i, "", "他"] + [0]*13)
        default_data = pd.DataFrame(initial_data, columns=input_cols)
        
        with st.form("bulk_batting_form"):
            edited_df = st.data_editor(
                default_data, num_rows="dynamic", use_container_width=True,
                column_config={
                    "選手名": st.column_config.SelectboxColumn("選手名", options=[""] + [local_fmt(p) for p in ALL_PLAYERS], width="medium"),
                    "守備": st.column_config.SelectboxColumn("守備", options=["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控", "他"]),
                    "打席数": st.column_config.SelectboxColumn("打席", options=number_options),
                    "単打": st.column_config.SelectboxColumn("単", options=number_options),
                    # ... (省略: 他のカラム設定は元のまま)
                }
            )
            
            bench_selection = st.multiselect("ベンチ入りメンバー", ALL_PLAYERS, format_func=local_fmt)
            submitted_bulk = st.form_submit_button("全データを登録")

            if submitted_bulk:
                # (簡易化のためロジック省略: Bモードの登録処理は変更なし)
                st.success("✅ データ登録完了")
                st.rerun()

    # ---------------------------------------------------------
    # C. 詳細入力モード (メイン機能)
    # ---------------------------------------------------------
    else:
        # --- 0. セッションステートの初期化 ---
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}
        if "persistent_bench" not in st.session_state:
            st.session_state["persistent_bench"] = []

        # ★★★ 新規追加: スタメンから投手を検知してセッションに保存 ★★★
        # saved_lineup (sp0, sp1...) または現在のWidget State (sp0, sp1...) を走査
        detected_pitcher = None
        for i in range(15):
            # Widgetの値がまだsession_stateに入っていない初回描画時等はsaved_lineupを見る
            pos_key = f"sp{i}"
            name_key = f"sn{i}"
            
            # Widgetの現在の値があればそれを、なければ保存値を参照
            p_pos = st.session_state.get(pos_key) or st.session_state["saved_lineup"].get(f"pos_{i}")
            p_name = st.session_state.get(name_key) or st.session_state["saved_lineup"].get(f"name_{i}")
            
            if p_pos == "投" and p_name and p_name in ALL_PLAYERS:
                detected_pitcher = p_name
                break # 最初に見つかった投手を優先
        
        if detected_pitcher:
            st.session_state["shared_starting_pitcher"] = detected_pitcher

        # --- 1. データの前処理 ---
        current_season_stats = {}
        today_batting_df = pd.DataFrame()
        
        if not df_batting.empty:
            df_batting_proc = df_batting.copy()
            df_batting_proc["standard_date"] = pd.to_datetime(df_batting_proc["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            today_batting_df = df_batting_proc[df_batting_proc["standard_date"] == selected_date_str].copy()
            
            # (省略: 通算成績計算ロジック)

        # --- 2. 統合登録ロジック ---
        def submit_everything():
            new_records = []
            has_homerun = False
            st.session_state["persistent_bench"] = st.session_state.get("bench_selection_widget", [])
            for i in range(15):
                st.session_state["saved_lineup"][f"pos_{i}"] = st.session_state.get(f"sp{i}")
                st.session_state["saved_lineup"][f"name_{i}"] = st.session_state.get(f"sn{i}")

            is_play_mode = any(st.session_state.get(f"sr{i}", "---") != "---" for i in range(15))

            for i in range(15):
                p_name = st.session_state.get(f"sn{i}")
                p_pos = st.session_state.get(f"sp{i}", "")
                p_res = st.session_state.get(f"sr{i}", "---")
                p_rbi = int(st.session_state.get(f"si{i}", 0))

                if p_name:
                    if is_play_mode:
                        if p_res != "---":
                            pass
                    else:
                        new_records.append({
                            "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                            "イニング": "試合開始", "選手名": p_name, "位置": p_pos, "打順": i+1,
                            "結果": "スタメン", "打点": 0, "得点": 0, "盗塁": 0, "種別": "スタメン"
                        })

            if new_records:
                try:
                    conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True))
                    st.cache_data.clear()
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
            if st.form_submit_button("登録実行 (打席・スタメン一括保存)", type="primary", use_container_width=True):
                submit_everything()

            c_inn, c_outs, _ = st.columns([1.5, 2.5, 3.5])
            with c_inn:
                st.selectbox("イニング", [f"{i}回" for i in range(1, 10)] + ["延長"], key="current_inn_key")
            with c_outs:
                # (省略: アウトカウント表示)
                st.write("")

            batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]
            player_list_with_empty = [""] + ALL_PLAYERS
            col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]

            for i in range(15):
                c = st.columns(col_ratios)
                c[0].write(f"{i+1}")
                
                s_pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
                s_name = st.session_state["saved_lineup"].get(f"name_{i}", "")
                def_pos_ix = ALL_POSITIONS.index(s_pos) if s_pos in ALL_POSITIONS else 0
                def_name_ix = player_list_with_empty.index(s_name) if s_name in player_list_with_empty else 0
                
                # keyにコールバックを指定して、変更即保存を実現するのも手ですが、ここではsubmit時に保存しています
                c[1].selectbox(f"p{i}", ALL_POSITIONS, index=def_pos_ix, key=f"sp{i}", label_visibility="collapsed")
                c[2].selectbox(f"n{i}", player_list_with_empty, index=def_name_ix, key=f"sn{i}", label_visibility="collapsed", format_func=local_fmt)
                
                sel_p_name = st.session_state.get(f"sn{i}")
                c[3].selectbox(f"r{i}", batting_results, key=f"sr{i}", label_visibility="collapsed")
                c[4].selectbox(f"i{i}", [0, 1, 2, 3, 4], key=f"si{i}", label_visibility="collapsed")
                
                # 履歴表示エリア (省略せず表示用に残します)
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
                            rbi = int(pd.to_numeric(row['打点'], errors='coerce') or 0)
                            short = {"本塁打":"本", "三塁打":"3塁", "二塁打":"2塁", "単打":"安", "三振":"振"}.get(res, res)
                            if res in pa_list:
                                count += 1
                                if rbi > 0:
                                    display_text = f"<span style='color:red; font-weight:bold;'>{count}({short}{rbi})</span>"
                                else:
                                    display_text = f"<span>{count}({short})</span>"
                                history_html.append(display_text)
                            else:
                                history_html.append(f"({short})")
                        c[5].markdown(f"<div style='font-size:20px; line-height:1.5;'>{' '.join(history_html)}</div>", unsafe_allow_html=True)
                    else:
                        c[5].write("")
                else:
                    c[5].write("")

            st.divider()
            with st.expander(" 🚌  ベンチ入りメンバー", expanded=True):
                st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)