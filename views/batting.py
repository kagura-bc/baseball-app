import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
from config.settings import ALL_POSITIONS, SPREADSHEET_URL
from utils.players import get_active_players
from utils.ui import render_scoreboard, render_out_indicator_3, show_homerun_effect, fmt_player_name

# --- コールバック関数 (入力状態の保存用) ---
def save_lineup_item(i, item_type):
    if "saved_lineup" not in st.session_state:
        st.session_state["saved_lineup"] = {}
        
    prefix_map = {"pos": "sp", "name": "sn", "res": "sr", "rbi": "si"}
    widget_key = f"{prefix_map[item_type]}{i}"
    
    if widget_key in st.session_state:
        val = st.session_state[widget_key]
        st.session_state["saved_lineup"][f"{item_type}_{i}"] = val

# --- ヘルパー関数 ---
def local_fmt(name):
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))

# ==========================================
# メイン表示関数
# ==========================================
def show_batting_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order, is_test_mode=False):
    ALL_PLAYERS, PLAYER_NUMBERS = get_active_players()
    st.session_state["shared_player_numbers"] = PLAYER_NUMBERS
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    ws_batting = "打撃成績"
    ws_pitching = "投手成績"
    b_inning_suffix = "表" if kagura_order == "先攻 (表)" else "裏"

    pos_options = [p for p in ALL_POSITIONS if p != ""]
    player_options = [p for p in ALL_PLAYERS if p != ""]

    # ▼▼▼ フォームクリアのフラグ処理 ▼▼▼
    if st.session_state.get("needs_batting_clear"):
        for i in range(15):
            for k in [f"sp{i}", f"sn{i}", f"sr{i}", f"si{i}", f"st{i}"]:
                if k in st.session_state:
                    st.session_state[k] = "---" if k.startswith("si") else None
            if f"sd{i}" in st.session_state:
                st.session_state[f"sd{i}"] = []
        if "quick_sr" in st.session_state:
            st.session_state["quick_sr"] = None
        if "quick_sd" in st.session_state:
            st.session_state["quick_sd"] = []
        if "quick_si" in st.session_state:
            st.session_state["quick_si"] = None
        st.session_state["needs_batting_clear"] = False

    # ==========================================
    # 1. 試合設定変更時のリセット & 初期化
    # ==========================================
    current_match_id = f"{selected_date_str}_{opp_team}_{match_type}"
    
    if "last_match_id" not in st.session_state:
        st.session_state["last_match_id"] = current_match_id
    
    match_changed = (st.session_state["last_match_id"] != current_match_id)
    
    if match_changed:
        all_keys = list(st.session_state.keys())
        target_prefixes = ["sn", "sp", "sr", "si", "st", "sd", "quick_", "persistent_", "batting_inning_select", "scorer_name_ui", "saved_lineup"]
        for key in all_keys:
            if any(key.startswith(prefix) for prefix in target_prefixes):
                del st.session_state[key]
        
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"
        st.session_state["scorer_name_ui"] = ""
        st.session_state["saved_lineup"] = {}
        st.session_state["last_match_id"] = current_match_id
        st.rerun()

    if "saved_lineup" not in st.session_state:
        st.session_state["saved_lineup"] = {}
    if "persistent_inn" not in st.session_state:
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"
    if "scorer_name_ui" not in st.session_state:
        st.session_state["scorer_name_ui"] = ""

    # ==========================================
    # 2. データの読み込み & 状態同期
    # ==========================================
    is_kagura_top = (kagura_order == "先攻 (表)")
    
    today_batting_df = df_batting[
        (df_batting["日付"].astype(str) == selected_date_str) & 
        (df_batting["対戦相手"] == opp_team) & 
        (df_batting["試合種別"] == match_type)
    ]
    today_pitching_df = df_pitching[
        (df_pitching["日付"].astype(str) == selected_date_str) & 
        (df_pitching["対戦相手"] == opp_team) & 
        (df_pitching["試合種別"] == match_type)
    ]

    # 初回読み込み時、またはセッションにデータがない場合にスプレッドシートからスタメン情報を復元
    if "sn0" not in st.session_state and not today_batting_df.empty:
        try:
            valid_inn_df = today_batting_df[~today_batting_df["イニング"].astype(str).isin(["まとめ入力", "試合終了", "", "nan"])]
            if not valid_inn_df.empty:
                last_inn = valid_inn_df.iloc[-1]["イニング"]
                st.session_state["persistent_inn"] = last_inn

            valid_scorer_df = today_batting_df[
                (today_batting_df["スコアラー"].astype(str).str.strip() != "") & 
                (today_batting_df["スコアラー"].astype(str).str.strip() != "0") &
                (today_batting_df["スコアラー"].astype(str).str.strip() != "nan")
            ]
            if not valid_scorer_df.empty:
                st.session_state["scorer_name_ui"] = valid_scorer_df.iloc[-1]["スコアラー"]

            # 1〜15打順それぞれの最新スタメン情報を取得
            for i in range(15):
                target_order = i + 1
                
                # 「スタメン」として記録されている行、または「試合前」イニングの行を最優先で取得
                lineup_rows = today_batting_df[
                    (pd.to_numeric(today_batting_df["打順"], errors='coerce') == target_order) & 
                    ((today_batting_df["結果"].astype(str) == "スタメン") | (today_batting_df["イニング"].astype(str) == "試合前"))
                ]
                
                if lineup_rows.empty:
                    # 見つからない場合は該当打順の最後の行をフォールバックとして利用
                    lineup_rows = today_batting_df[pd.to_numeric(today_batting_df["打順"], errors='coerce') == target_order]

                if not lineup_rows.empty:
                    last_row = lineup_rows.iloc[-1]
                    saved_name = str(last_row["選手名"])
                    saved_pos = str(last_row.get("位置", ""))
                    
                    # 選手名の完全一致または名前部分（背番号除く）の一致を確認
                    matched_name = None
                    if saved_name in player_options:
                        matched_name = saved_name
                    else:
                        matched_name = next((p for p in player_options if p.split(" (")[0] == saved_name.split(" (")[0]), None)

                    matched_pos = saved_pos if saved_pos in pos_options else None

                    if matched_name:
                        st.session_state[f"sn{i}"] = matched_name
                        st.session_state["saved_lineup"][f"name_{i}"] = matched_name
                    if matched_pos:
                        st.session_state[f"sp{i}"] = matched_pos
                        st.session_state["saved_lineup"][f"pos_{i}"] = matched_pos
                    
                    if matched_pos == "投" and matched_name:
                        st.session_state["shared_starting_pitcher"] = matched_name.split(" (")[0]
                        
        except Exception as e:
            print(f"Data Loading Error: {e}")

    # ==========================================
    # 3. スコアボード表示
    # ==========================================
    if not today_batting_df.empty:
        scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"]
    else:
        scoreboard_df = today_batting_df

    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()

    # ==========================================
    # 4. 詳細入力 (打席結果登録)
    # ==========================================
    this_year = datetime.datetime.now().year
    if not df_batting.empty:
        df_batting["日付_dt"] = pd.to_datetime(df_batting["日付"], errors='coerce')
        df_this_season = df_batting[df_batting["日付_dt"].dt.year == this_year].copy()
    else:
        df_this_season = pd.DataFrame()

    hit_results = ["単打", "二塁打", "三塁打", "本塁打"]
    ab_results = hit_results + ["凡退(ゴロ)", "凡退(フライ)", "失策", "走塁死", "盗塁死", "三振", "併殺打", "野選", "振り逃げ三振"]

    inn_list = [f"{i}回{b_inning_suffix}" for i in range(1, 10)] + [f"延長{b_inning_suffix}"]
    current_inn_val = st.session_state.get("persistent_inn", f"1回{b_inning_suffix}")
    
    if not today_batting_df.empty:
        inn_df_check = today_batting_df[today_batting_df["イニング"] == current_inn_val]
        single_out_list = ["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "振り逃げ三振", "野選", "牽制死"]
        s_outs = len(inn_df_check[inn_df_check["結果"].isin(single_out_list)])
        d_outs = len(inn_df_check[inn_df_check["結果"] == "併殺打"]) * 2
        
        if (s_outs + d_outs) >= 3:
            try:
                curr_idx = inn_list.index(current_inn_val)
                if curr_idx < len(inn_list) - 1:
                    current_inn_val = inn_list[curr_idx + 1]
                    st.session_state["persistent_inn"] = current_inn_val
            except ValueError:
                pass

    # --- 登録実行関数 ---
    def submit_everything(selected_inn):
        if "sn0" not in st.session_state: return 

        active_orders_temp = 9
        for idx_temp in range(14, -1, -1):
            if st.session_state.get(f"sn{idx_temp}"):
                active_orders_temp = idx_temp + 1
                break
        valid_pa_temp = today_batting_df[
            ~today_batting_df["イニング"].astype(str).isin(["まとめ入力", "試合終了", "", "nan"]) & 
            ~today_batting_df["結果"].astype(str).isin(["スタメン", "守備変更", "交代"])
        ] if not today_batting_df.empty else pd.DataFrame()
        cur_batter_idx = len(valid_pa_temp) % active_orders_temp

        q_res_val = st.session_state.get("quick_sr")
        if q_res_val:
            st.session_state[f"sr{cur_batter_idx}"] = q_res_val
            st.session_state[f"sd{cur_batter_idx}"] = st.session_state.get("quick_sd", [])
            q_si_val = st.session_state.get("quick_si")
            if q_si_val is not None:
                st.session_state[f"si{cur_batter_idx}"] = q_si_val

        require_direction_results = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "犠打(ゴロ)", "犠打(フライ)", "失策(ゴロ)", "失策(フライ)", "併殺打"]
        validation_errors = []

        for i in range(15):
            p_name = st.session_state.get(f"sn{i}")
            p_res = st.session_state.get(f"sr{i}")
            
            p_dir_raw = st.session_state.get(f"sd{i}", [])
            p_dir = "-".join(p_dir_raw) if p_dir_raw else "---"
            
            if p_name and p_res:
                if p_res in require_direction_results and p_dir == "---":
                    validation_errors.append(f"打順{i+1} ({p_name}): 「{p_res}」の打球方向を選択してください。")

        if validation_errors:
            for err in validation_errors: st.error(err)
            return

        new_records = []
        has_homerun = False
        
        current_inn = selected_inn
        current_scorer = st.session_state.get("scorer_name_ui", "")
        
        st.session_state["persistent_scorer"] = current_scorer
        st.session_state["persistent_inn"] = current_inn
        
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}

        for i in range(15):
            p_name = st.session_state.get(f"sn{i}", "")
            p_pos = st.session_state.get(f"sp{i}", "")
            
            st.session_state["saved_lineup"][f"name_{i}"] = p_name if p_name else ""
            st.session_state["saved_lineup"][f"pos_{i}"] = p_pos if p_pos else ""
            
            if p_pos == "投" and p_name != "":
                st.session_state["saved_pitcher_name"] = p_name
            
            p_res = st.session_state.get(f"sr{i}")
            
            p_dir_raw = st.session_state.get(f"sd{i}", [])
            p_dir = "-".join(p_dir_raw) if p_dir_raw else "---"
            
            def to_int(val):
                if val is None: return 0
                try: return int(val)
                except: return 0

            rbi_val = to_int(st.session_state.get(f"si{i}"))
            run_val_raw = st.session_state.get(f"st{i}")
            run_val = int(run_val_raw) if run_val_raw is not None else 0

            if p_res == "本塁打":
                run_val = 1
                if rbi_val == 0: rbi_val = 1
                has_homerun = True

            last_name = ""
            last_pos = ""
            if not today_batting_df.empty:
                order_records = today_batting_df[pd.to_numeric(today_batting_df["打順"], errors='coerce') == i+1]
                if not order_records.empty:
                    last_record = order_records.iloc[-1]
                    last_name = str(last_record.get("選手名", ""))
                    if last_name == "nan": last_name = ""
                    last_pos = str(last_record.get("位置", ""))
                    if last_pos == "nan": last_pos = ""

            if p_name and p_pos:
                if last_name == "":
                    record_dict = {
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": "試合前", "選手名": p_name, "位置": p_pos, "打順": i+1,
                        "結果": "スタメン",
                        "打点": 0, "得点": 0, "盗塁": 0, 
                        "種別": "スタメン", "打球方向": "",
                        "スコアラー": current_scorer
                    }
                    new_records.append(record_dict)
                elif p_name == last_name and p_pos != last_pos:
                    record_dict = {
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": current_inn, "選手名": p_name, "位置": p_pos, "打順": i+1,
                        "結果": "守備変更",
                        "打点": 0, "得点": 0, "盗塁": 0, 
                        "種別": "守備変更", "打球方向": "",
                        "スコアラー": current_scorer
                    }
                    new_records.append(record_dict)
                elif p_name != last_name and last_name != "":
                    record_dict = {
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": current_inn, "選手名": p_name, "位置": p_pos, "打順": i+1,
                        "結果": "交代",
                        "打点": 0, "得点": 0, "盗塁": 0, 
                        "種別": "交代", "打球方向": "",
                        "スコアラー": current_scorer
                    }
                    new_records.append(record_dict)

            if p_name and (p_res is not None or run_val > 0):
                actual_res = p_res if p_res is not None else "得点"
                record_dict = {
                    "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": current_inn, "選手名": p_name, "位置": p_pos, "打順": i+1,
                    "結果": actual_res,
                    "打点": rbi_val, "得点": run_val, "盗塁": 0, 
                    "種別": "打席", "打球方向": p_dir if p_dir != "---" else "",
                    "スコアラー": current_scorer
                }
                new_records.append(record_dict)

        if new_records:
            try:
                new_df = pd.DataFrame(new_records)
                updated_df = pd.concat([df_batting, new_df], ignore_index=True)
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=updated_df)
                st.cache_data.clear()
                
                out_res_list = ["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "振り逃げ三振"]
                inn_combined = pd.concat([today_batting_df[today_batting_df["イニング"] == current_inn], new_df])
                total_outs = len(inn_combined[inn_combined["結果"].isin(out_res_list)])
                total_outs += len(inn_combined[inn_combined["結果"] == "併殺打"]) * 2

                if total_outs >= 3:
                    try:
                        curr_idx = inn_list.index(current_inn)
                        if curr_idx < len(inn_list) - 1:
                            next_inn = inn_list[curr_idx + 1]
                            st.session_state["persistent_inn"] = next_inn
                            st.toast(f"3アウトチェンジ！次イニング({next_inn})へ進みます。")
                    except: pass

                st.session_state["needs_batting_clear"] = True
                
                if has_homerun: st.session_state["show_homerun_flg"] = True
                st.success(f"✅ 入力内容を保存しました")
                import time
                time.sleep(1)
                st.rerun() 
            except Exception as e:
                st.error(f"保存エラー: {e}")
        else:
            st.success("✅ 表示状態を保持しました（※変更点はありません）")
            import time
            time.sleep(1)
            st.rerun()

    # --- フォーム開始 ---
    with st.form(key='batting_form', clear_on_submit=False):
        submitted = st.form_submit_button("登録実行 (スコアボード反映)", type="primary", use_container_width=True)

        c_inn, c_outs, c_scorer = st.columns([1.5, 2.5, 3.5])
        
        with c_inn:
            def_inn_ix = inn_list.index(current_inn_val) if current_inn_val in inn_list else 0
            curr_inn = st.selectbox("イニング", inn_list, index=def_inn_ix)
            st.session_state["persistent_inn"] = curr_inn
        
        with c_outs:
            disp_outs = 0
            if not today_batting_df.empty:
                inn_df = today_batting_df[today_batting_df["イニング"] == curr_inn]
                single_out_list = ["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "振り逃げ三振", "野選", "牽制死"]
                s_outs = len(inn_df[inn_df["結果"].isin(single_out_list)])
                d_outs = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                disp_outs = (s_outs + d_outs) % 3
            st.markdown(render_out_indicator_3(disp_outs), unsafe_allow_html=True)
        
        with c_scorer: 
            p_list = [""] + ALL_PLAYERS
            saved_scorer = st.session_state.get("persistent_scorer", "")
            def_scorer_ix = p_list.index(saved_scorer) if saved_scorer in p_list else 0
            selected_scorer = st.selectbox("スコアラー", p_list, key="scorer_name_ui", format_func=local_fmt, index=def_scorer_ix)
            st.session_state["persistent_scorer"] = selected_scorer

        # ==========================================
        # 📍 現在の打順・打者インジケータ ＋ クイック入力欄（打席結果・方向・打点）
        # ==========================================
        active_orders = 9
        for i in range(14, -1, -1):
            if st.session_state.get(f"sn{i}"):
                active_orders = i + 1
                break

        if not today_batting_df.empty:
            valid_pa_df = today_batting_df[
                ~today_batting_df["イニング"].astype(str).isin(["まとめ入力", "試合終了", "", "nan"]) & 
                ~today_batting_df["結果"].astype(str).isin(["スタメン", "守備変更", "交代"])
            ]
            total_pa_count = len(valid_pa_df)
        else:
            total_pa_count = 0

        current_batter_index = total_pa_count % active_orders
        current_order_num = current_batter_index + 1
        raw_batter_name = st.session_state.get(f"sn{current_batter_index}", "")
        formatted_batter_name = local_fmt(raw_batter_name) if raw_batter_name else "（未設定）"

        batting_results = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", 
                           "失策(ゴロ)", "失策(フライ)", "野選", "併殺打", "振り逃げ三振", "打撃妨害"]

        q_cols = [3.4, 1.8, 2.0, 1.0]
        qc = st.columns(q_cols)

        with qc[0]:
            st.markdown(f"""
            <div style="background-color: #f0f2f6; padding: 8px 14px; border-radius: 8px; border-left: 6px solid #ff4b4b; height: 100%; display: flex; align-items: center; justify-content: flex-start; gap: 12px;">
                <span style="font-size: 13px; color: #555; font-weight: bold; white-space: nowrap;">📍 現在の打席</span>
                <span style="font-size: 16px; color: #111; font-weight: bold; white-space: nowrap;">第 {current_order_num} 打順</span>
                <span style="font-size: 18px; color: #ff4b4b; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{formatted_batter_name}</span>
            </div>
            """, unsafe_allow_html=True)
        with qc[1]:
            st.selectbox("結果(クイック)", batting_results, key="quick_sr", placeholder="打席結果", index=None, label_visibility="collapsed")
        with qc[2]:
            st.multiselect("方向(クイック)", ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"], key="quick_sd", label_visibility="collapsed", max_selections=2, placeholder="方向選択")
        with qc[3]:
            st.selectbox("打点(クイック)", [0, 1, 2, 3, 4], key="quick_si", placeholder="打点", index=None, label_visibility="collapsed")
        # ==========================================

        st.divider()

        run_results = ["盗塁", "盗塁死", "走塁死"]

        col_ratios = [0.5, 0.8, 1.5, 1.4, 0.7, 3.6]
        h = st.columns(col_ratios)
        headers = ["打順", "守備", "選手名", "結果", "得点", "今日の成績"]
        for idx, title in enumerate(headers):
            h[idx].markdown(f"<div style='text-align:center; font-size:12px; color:gray;'>{title}</div>", unsafe_allow_html=True)

        for i in range(15):
            c = st.columns(col_ratios)
            c[0].markdown(f"<div style='text-align:center; line-height:2.5;'>{i+1}</div>", unsafe_allow_html=True)
            
            # セッションステートから値を取得（未設定時はNoneにしてplaceholderを表示させる）
            s_pos = st.session_state.get(f"sp{i}")
            s_name = st.session_state.get(f"sn{i}")
            
            def_pos_ix = pos_options.index(s_pos) if s_pos in pos_options else None
            def_name_ix = player_options.index(s_name) if s_name in player_options else None
            
            c[1].selectbox(f"p{i}", pos_options, index=def_pos_ix, key=f"sp{i}", placeholder="守備", label_visibility="collapsed")
            c[2].selectbox(f"n{i}", player_options, index=def_name_ix, key=f"sn{i}", placeholder="選手名", format_func=local_fmt, label_visibility="collapsed")
            
            sel_p_name = st.session_state.get(f"sn{i}")
            if sel_p_name and not df_this_season.empty:
                clean_name = sel_p_name.split(" (")[0]
                p_stats_df = df_this_season[df_this_season["選手名"] == clean_name]
                
                if not p_stats_df.empty:
                    ab_count = len(p_stats_df[p_stats_df["結果"].isin(ab_results)])
                    hit_count = len(p_stats_df[p_stats_df["結果"].isin(hit_results)])
                    rbi_sum = pd.to_numeric(p_stats_df["打点"], errors='coerce').sum()
                    hr_count = len(p_stats_df[p_stats_df["結果"] == "本塁打"])
                    
                    avg = hit_count / ab_count if ab_count > 0 else 0.0
                    avg_str = f"{avg:.3f}".replace("0.", ".") 
                    
                    c[2].markdown(f"<div style='color:#1E90FF; font-size:11px; margin-top:-5px; text-align:center;'>{avg_str} {int(rbi_sum)}点 {hr_count}本</div>", unsafe_allow_html=True)
                else:
                    c[2].markdown(f"<div style='color:#1E90FF; font-size:11px; margin-top:-5px; text-align:center;'>.000 0点 0本</div>", unsafe_allow_html=True)

            c[3].selectbox(f"r{i}", run_results, key=f"sr{i}", placeholder="走塁結果", index=None, label_visibility="collapsed")
            c[4].selectbox(f"t{i}", [0, 1], key=f"st{i}", placeholder="得点", index=None, label_visibility="collapsed") 
            
            if not today_batting_df.empty and sel_p_name:
                p_df = today_batting_df[
                    (today_batting_df["選手名"] == sel_p_name) & 
                    (~today_batting_df["結果"].isin(["スタメン", "守備変更", "交代"]))
                ]
                if not p_df.empty:
                    history_html = []
                    count = 0
                    total_runs = 0
                    for _, row in p_df.iterrows():
                        res = row['結果']
                        runs_val = pd.to_numeric(row['得点'], errors='coerce')
                        total_runs += int(runs_val) if pd.notna(runs_val) else 0
                        
                        res_short = {
                            "本塁打":"本", "三塁打":"三", "二塁打":"二", "単打":"安", 
                            "三振":"振", "凡退(ゴロ)":"ゴ", "凡退(フライ)":"飛", "四球":"球", "死球":"死", "犠打(ゴロ)":"犠", "犠打(フライ)":"犠", "犠飛":"犠飛", "失策(ゴロ)":"失", "失策(フライ)":"失", "野選":"野", "併殺打":"併", 
                            "振り逃げ三振":"逃", "打撃妨害":"妨", "盗塁":"盗", "盗塁死":"盗死", "走塁死":"走死"
                        }.get(res, res[:2])
                        
                        count += 1
                        raw_dir = row['打球方向']
                        p_dir = str(raw_dir) if pd.notna(raw_dir) and raw_dir != "---" else ""
                        disp_text = f"{p_dir}{res_short}" if p_dir else f"{res_short}"
                        html = f"<span>{count}({disp_text})</span>"
                        history_html.append(html)
                    
                    if total_runs > 0:
                        history_html.append(f"<span style='color:blue; font-size:14px; margin-left:5px;'>[計{total_runs}得点]</span>")
                    
                    c[5].markdown(f"<div style='font-size:18px; line-height:1.2; padding-top:5px;'>{' '.join(history_html)}</div>", unsafe_allow_html=True)

        if submitted:
            submit_everything(curr_inn)

    with st.expander(" 🚌 ベンチ入りメンバー", expanded=True):
        selected_bench = st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)
        st.session_state["persistent_bench"] = selected_bench