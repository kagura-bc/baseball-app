import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
from config.settings import ALL_PLAYERS, ALL_POSITIONS, SPREADSHEET_URL, PLAYER_NUMBERS
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
    return fmt_player_name(name, PLAYER_NUMBERS)

# ==========================================
# メイン表示関数
# ==========================================
def show_batting_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order, is_test_mode=False):
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    ws_batting = "打撃成績"
    ws_pitching = "投手成績"
    b_inning_suffix = "表" if kagura_order == "先攻 (表)" else "裏"

    # ==========================================
    # 1. 日付変更時のリセット & 初期化
    # ==========================================
    if "last_selected_date" not in st.session_state:
        st.session_state["last_selected_date"] = selected_date_str
    
    date_changed = (st.session_state["last_selected_date"] != selected_date_str)
    
    if date_changed:
        all_keys = list(st.session_state.keys())
        target_prefixes = ["sn", "sp", "sr", "si", "persistent_", "batting_inning_select", "scorer_name_ui"]
        for key in all_keys:
            if any(key.startswith(prefix) for prefix in target_prefixes):
                del st.session_state[key]
        
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"
        st.session_state["scorer_name_ui"] = ""
        st.session_state["saved_lineup"] = {}
        st.session_state["last_selected_date"] = selected_date_str
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
    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str]

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

            for i in range(15):
                target_order = i + 1
                rows = today_batting_df[pd.to_numeric(today_batting_df["打順"], errors='coerce') == target_order]
                if not rows.empty:
                    last_row = rows.iloc[-1]
                    saved_name = last_row["選手名"]
                    saved_pos = last_row.get("位置", "")
                    
                    st.session_state[f"sn{i}"] = saved_name
                    st.session_state[f"sp{i}"] = saved_pos
                    st.session_state["saved_lineup"][f"name_{i}"] = saved_name
                    st.session_state["saved_lineup"][f"pos_{i}"] = saved_pos
                    
                    if saved_pos == "投" and saved_name:
                        st.session_state["shared_starting_pitcher"] = saved_name.split(" (")[0]
                        
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

    # --- 【重要】イニング自動進行ロジック（フォーム描画前に計算） ---
    inn_list = [f"{i}回{b_inning_suffix}" for i in range(1, 10)] + [f"延長{b_inning_suffix}"]
    current_inn_val = st.session_state.get("persistent_inn", f"1回{b_inning_suffix}")
    
    if not today_batting_df.empty:
        inn_df_check = today_batting_df[today_batting_df["イニング"] == current_inn_val]
        s_outs = len(inn_df_check[inn_df_check["結果"].isin(["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "振り逃げ三振"])])
        d_outs = len(inn_df_check[inn_df_check["結果"] == "併殺打"]) * 2
        
        # もし3アウト以上になっていれば次のイニングへ
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

        require_direction_results = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "犠打(ゴロ)", "犠打(フライ)", "失策(ゴロ)", "失策(フライ)"]
        validation_errors = []

        for i in range(15):
            p_name = st.session_state.get(f"sn{i}")
            p_res = st.session_state.get(f"sr{i}", "---")
            p_dir = st.session_state.get(f"sd{i}", "---")
            if p_name and p_res != "---":
                if p_res in require_direction_results and p_dir == "---":
                    validation_errors.append(f"打順{i+1} ({p_name}): 「{p_res}」の打球方向を選択してください。")

        if validation_errors:
            for err in validation_errors: st.error(err)
            return

        new_records = []
        has_homerun = False
        
        # フォームから渡されたイニングを使用
        current_inn = selected_inn
        current_scorer = st.session_state.get("scorer_name_ui", "")
        
        st.session_state["persistent_scorer"] = current_scorer
        st.session_state["persistent_inn"] = current_inn
        
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}

        for i in range(15):
            p_name = st.session_state.get(f"sn{i}", "")
            p_pos = st.session_state.get(f"sp{i}", "")
            
            st.session_state["saved_lineup"][f"name_{i}"] = p_name
            st.session_state["saved_lineup"][f"pos_{i}"] = p_pos
            
            if p_pos == "投" and p_name != "":
                st.session_state["saved_pitcher_name"] = p_name
            
            p_res = st.session_state.get(f"sr{i}", "---")
            p_dir = st.session_state.get(f"sd{i}", "---")
            
            def to_int(val):
                if val == "---" or val is None: return 0
                try: return int(val)
                except: return 0

            rbi_val = to_int(st.session_state.get(f"si{i}"))
            run_val = to_int(st.session_state.get(f"st{i}"))

            if p_res == "本塁打":
                run_val = 1
                if rbi_val == 0: rbi_val = 1
                has_homerun = True

            if p_name and (p_res != "---" or run_val > 0):
                record_dict = {
                    "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": current_inn, "選手名": p_name, "位置": p_pos, "打順": i+1,
                    "結果": p_res if p_res != "---" else "得点",
                    "打点": rbi_val, "得点": run_val, "盗塁": (1 if p_res == "盗塁" else 0), 
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

                for i in range(15):
                    for k in [f"sr{i}", f"sd{i}", f"si{i}", f"st{i}"]: 
                        if k in st.session_state:
                            st.session_state[k] = "---"
                
                if has_homerun: st.session_state["show_homerun_flg"] = True
                st.success(f"✅ 打席結果を保存しました")
                import time
                time.sleep(1)
                st.rerun() 
            except Exception as e:
                st.error(f"保存エラー: {e}")
        else:
            st.success("✅ スタメンとスコアラーの表示を保持しました（※打席結果は未入力です）")
            import time
            time.sleep(1)
            st.rerun()

    # --- フォーム開始 ---
    with st.form(key='batting_form', clear_on_submit=False):
        # 1. 登録ボタン
        submitted = st.form_submit_button("登録実行 (スコアボード反映)", type="primary", use_container_width=True)

        # 2. イニング・アウト・スコアラー選択
        c_inn, c_outs, c_scorer = st.columns([1.5, 2.5, 3.5])
        
        with c_inn:
            def_inn_ix = inn_list.index(current_inn_val) if current_inn_val in inn_list else 0
            # ★【修正の核心】keyを削除して固着を防止し、初期値(index)で制御する
            curr_inn = st.selectbox("イニング", inn_list, index=def_inn_ix)
            st.session_state["persistent_inn"] = curr_inn # 手動変更に対応
        
        with c_outs:
            disp_outs = 0
            if not today_batting_df.empty:
                inn_df = today_batting_df[today_batting_df["イニング"] == curr_inn]
                s_outs = len(inn_df[inn_df["結果"].isin(["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "走塁死", "盗塁死", "振り逃げ三振"])])
                d_outs = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                disp_outs = (s_outs + d_outs) % 3
            st.markdown(render_out_indicator_3(disp_outs), unsafe_allow_html=True)
        
        with c_scorer: 
            p_list = [""] + ALL_PLAYERS
            saved_scorer = st.session_state.get("persistent_scorer", "")
            def_scorer_ix = p_list.index(saved_scorer) if saved_scorer in p_list else 0
            selected_scorer = st.selectbox("スコアラー", p_list, key="scorer_name_ui", format_func=local_fmt, index=def_scorer_ix)
            st.session_state["persistent_scorer"] = selected_scorer

        st.divider()

        # 3. 打席入力テーブル
        batting_results = ["---", "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", 
                           "失策(ゴロ)", "失策(フライ)", "野選", "併殺打",  "盗塁", "得点", "走塁死", "盗塁死", "振り逃げ三振", "打撃妨害"]
        
        col_ratios = [0.5, 1.1, 1.8, 1.4, 0.9, 0.8, 0.8, 3.5]
        h = st.columns(col_ratios)
        headers = ["打順", "守備", "選手名", "結果", "方向", "打点", "得点", "今日の成績"]
        for idx, title in enumerate(headers):
            h[idx].markdown(f"<div style='text-align:center; font-size:12px; color:gray;'>{title}</div>", unsafe_allow_html=True)

        for i in range(15):
            c = st.columns(col_ratios)
            c[0].markdown(f"<div style='text-align:center; line-height:2.5;'>{i+1}</div>", unsafe_allow_html=True)
            
            s_pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
            s_name = st.session_state["saved_lineup"].get(f"name_{i}", "")
            def_pos_ix = ALL_POSITIONS.index(s_pos) if s_pos in ALL_POSITIONS else 0
            p_list = [""] + ALL_PLAYERS
            def_name_ix = p_list.index(s_name) if s_name in p_list else 0
            
            c[1].selectbox(f"p{i}", ALL_POSITIONS, index=def_pos_ix, key=f"sp{i}", label_visibility="collapsed")
            c[2].selectbox(f"n{i}", p_list, index=def_name_ix, key=f"sn{i}", label_visibility="collapsed", format_func=local_fmt)
            
            # --- 青色で通算成績を表示 ---
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

            c[3].selectbox(f"r{i}", batting_results, key=f"sr{i}", label_visibility="collapsed")
            c[4].selectbox(f"d{i}", ["---", "投", "捕", "一", "二", "三", "遊", "左", "中", "右"], key=f"sd{i}", label_visibility="collapsed")
            c[5].selectbox(f"i{i}", ["---", 0, 1, 2, 3, 4], key=f"si{i}", label_visibility="collapsed")
            c[6].selectbox(f"t{i}", ["---", 0, 1], key=f"st{i}", label_visibility="collapsed") 
            
            # --- 今日の成績履歴 ---
            if not today_batting_df.empty and sel_p_name:
                p_df = today_batting_df[
                    (today_batting_df["選手名"] == sel_p_name) & 
                    (~today_batting_df["結果"].isin(["スタメン"]))
                ]
                if not p_df.empty:
                    history_html = []
                    pa_list_for_history = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", 
                                           "失策(ゴロ)", "失策(フライ)", "野選", "併殺打", "振り逃げ三振", "打撃妨害"]
                    count = 0
                    total_runs = 0
                    for _, row in p_df.iterrows():
                        res = row['結果']
                        raw_dir = row['打球方向']
                        p_dir = str(raw_dir) if pd.notna(raw_dir) and raw_dir != "---" else ""
                        
                        rbi_val = pd.to_numeric(row['打点'], errors='coerce')
                        rbi = int(rbi_val) if pd.notna(rbi_val) else 0
                        
                        runs_val = pd.to_numeric(row['得点'], errors='coerce')
                        total_runs += int(runs_val) if pd.notna(runs_val) else 0
                        
                        res_short = {
                            "本塁打":"本", "三塁打":"三", "二塁打":"二", "単打":"安", 
                            "三振":"振", "凡退(ゴロ)":"ゴ", "凡退(フライ)":"飛", "四球":"球", "死球":"死", "犠打(ゴロ)":"犠", "犠打(フライ)":"犠", "犠飛":"犠飛", "失策(ゴロ)":"失", "失策(フライ)":"失", "野選":"野", "併殺打":"併", 
                            "振り逃げ三振":"逃", "打撃妨害":"妨", "守備変更":"守"
                        }.get(res, res[:1])
                        
                        if res in pa_list_for_history:
                            count += 1
                            disp_text = f"{p_dir}{res_short}"
                            if rbi > 0:
                                html = f"<span style='color:red; font-weight:bold;'>{count}({disp_text}{rbi})</span>"
                            else:
                                html = f"<span>{count}({disp_text})</span>"
                            history_html.append(html)
                    
                    if total_runs > 0:
                        history_html.append(f"<span style='color:blue; font-size:14px; margin-left:5px;'>[計{total_runs}得点]</span>")
                    
                    c[7].markdown(f"<div style='font-size:18px; line-height:1.2; padding-top:5px;'>{' '.join(history_html)}</div>", unsafe_allow_html=True)

        # フォーム内でボタンが押された場合に実行
        if submitted:
            submit_everything(curr_inn)

    # --- ベンチ入りメンバー (フォーム外) ---
    with st.expander(" 🚌 ベンチ入りメンバー", expanded=True):
        selected_bench = st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)
        st.session_state["persistent_bench"] = selected_bench