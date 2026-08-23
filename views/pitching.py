import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL, MY_TEAM
from utils.players import get_active_players
from utils.ui import fmt_player_name
from utils.ui import render_scoreboard
import re

def local_fmt(name):
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))

# --- BSOおよび球数インジケーターのHTML描画関数 ---
def render_bso_indicator(outs, balls, strikes, pitch_count):
    out_circles = "".join([
        f'<span style="display:inline-block; width:22px; height:22px; border-radius:50%; background-color:{"#ef4444" if i < outs else "#d1d5db"}; margin-right:5px;"></span>'
        for i in range(2)
    ])
    ball_circles = "".join([
        f'<span style="display:inline-block; width:22px; height:22px; border-radius:50%; background-color:{"#22c55e" if i < balls else "#d1d5db"}; margin-right:5px;"></span>'
        for i in range(3)
    ])
    strike_circles = "".join([
        f'<span style="display:inline-block; width:22px; height:22px; border-radius:50%; background-color:{"#eab308" if i < strikes else "#d1d5db"}; margin-right:5px;"></span>'
        for i in range(2)
    ])

    return f"""
    <div style="display: flex; align-items: center; gap: 18px; font-weight: bold; font-size: 18px; background-color: #f8f9fa; padding: 8px 14px; border-radius: 8px; border: 1px solid #e5e7eb; margin-bottom: 8px;">
        <div style="display: flex; align-items: center;">
            <span style="margin-right: 6px; color: #ef4444; font-size: 18px;">O</span>{out_circles}
        </div>
        <div style="display: flex; align-items: center;">
            <span style="margin-right: 6px; color: #22c55e; font-size: 18px;">B</span>{ball_circles}
        </div>
        <div style="display: flex; align-items: center;">
            <span style="margin-right: 6px; color: #eab308; font-size: 18px;">S</span>{strike_circles}
        </div>
        <div style="font-size: 14px; color: #374151; background-color: #ffffff; border: 1px solid #d1d5db; padding: 3px 12px; border-radius: 12px; margin-left: auto;">
            球数: <b style="font-size: 16px;">{pitch_count}</b> 球
        </div>
    </div>
    """

def show_pitching_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order):
    ALL_PLAYERS, PLAYER_NUMBERS = get_active_players()
    st.session_state["shared_player_numbers"] = PLAYER_NUMBERS
    
    ws_pitching = "投手成績"
    is_kagura_top = (kagura_order == "先攻 (表)")

    conn = st.connection("gsheets", type=GSheetsConnection)

    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str] if not df_batting.empty and "日付" in df_batting.columns else pd.DataFrame()
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str] if not df_pitching.empty and "日付" in df_pitching.columns else pd.DataFrame()
    
    scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"] if not today_batting_df.empty and "イニング" in today_batting_df.columns else df_batting
    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)

    current_match_id = f"{selected_date_str}_{opp_team}_{match_type}"
    if "last_p_match_id" not in st.session_state:
        st.session_state["last_p_match_id"] = current_match_id
    
    if st.session_state["last_p_match_id"] != current_match_id:
        keys_to_reset = ["p_det_inn", "opp_batter_index", "pitching_quick_sr", "pitching_quick_sd", "pitching_quick_run", "pitching_quick_er", "quick_dec_pitcher", "quick_dec_type", "p_b_count", "p_s_count", "p_pitch_count"]
        for k in list(st.session_state.keys()):
            if k in keys_to_reset or k.startswith("sync_"): 
                del st.session_state[k]
        st.session_state["last_p_match_id"] = current_match_id

    p_inning_suffix = "裏" if is_kagura_top else "表"

    if "opp_batter_index" not in st.session_state: st.session_state["opp_batter_index"] = 1
    if "opp_batter_count" not in st.session_state: st.session_state["opp_batter_count"] = 9
    if "p_det_inn" not in st.session_state: st.session_state["p_det_inn"] = f"1回{p_inning_suffix}"

    sync_key = f"sync_{selected_date_str}"
    if sync_key not in st.session_state:
        history_details = today_pitching_df[today_pitching_df["種別"].str.contains("詳細", na=False)] if not today_pitching_df.empty and "種別" in today_pitching_df.columns else pd.DataFrame()
        if not history_details.empty:
            last_rec = history_details.iloc[-1]
            st.session_state["p_det_inn"] = last_rec.get("イニング", f"1回{p_inning_suffix}")
            try:
                last_idx = int(str(last_rec.get("種別", "")).split(":")[1].replace("番打者", ""))
                st.session_state["opp_batter_index"] = (last_idx % st.session_state["opp_batter_count"]) + 1
            except:
                pass
            
            if not st.session_state.get("scorer_name"):
                valid_scorer_df = today_pitching_df[
                    (today_pitching_df["スコアラー"].astype(str).str.strip() != "") & 
                    (today_pitching_df["スコアラー"].astype(str).str.strip() != "0") &
                    (today_pitching_df["スコアラー"].astype(str).str.strip() != "nan")
                ] if not today_pitching_df.empty and "スコアラー" in today_pitching_df.columns else pd.DataFrame()
                if not valid_scorer_df.empty:
                    st.session_state["scorer_name"] = valid_scorer_df.iloc[-1]["スコアラー"]
            
            st.session_state[sync_key] = True
        else:
            st.session_state["p_det_inn"] = f"1回{p_inning_suffix}"
            st.session_state["opp_batter_index"] = 1
            st.session_state[sync_key] = True

    if st.session_state.get("needs_pitching_form_clear"):
        st.session_state["pitching_quick_sr"] = None
        st.session_state["pitching_quick_sd"] = []
        st.session_state["pitching_quick_run"] = 0
        st.session_state["pitching_quick_er"] = 0
        st.session_state["p_b_count"] = 0
        st.session_state["p_s_count"] = 0
        st.session_state["p_pitch_count"] = 0
        st.session_state["needs_pitching_form_clear"] = False

    inn_options = [f"{i}回{p_inning_suffix}" for i in range(1, 10)] + [f"延長{p_inning_suffix}"]
    current_inn_val = st.session_state.get("p_det_inn", f"1回{p_inning_suffix}")
    
    current_outs_total = 0
    if not today_pitching_df.empty and "イニング" in today_pitching_df.columns:
        p_inn_df_check = today_pitching_df[today_pitching_df["イニング"] == current_inn_val]
        single_out_list = ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"]
        single_outs = len(p_inn_df_check[p_inn_df_check["結果"].isin(single_out_list)]) if "結果" in p_inn_df_check.columns else 0
        double_outs = len(p_inn_df_check[p_inn_df_check["結果"] == "併殺打"]) * 2 if "結果" in p_inn_df_check.columns else 0
        current_outs_total = single_outs + double_outs

    if current_outs_total >= 3:
        try:
            curr_idx = inn_options.index(current_inn_val)
            if curr_idx < len(inn_options) - 1:
                next_inn = inn_options[curr_idx + 1]
                st.session_state["p_det_inn"] = next_inn
                current_inn_val = next_inn
                current_outs_total = 0 
        except ValueError:
            pass

    with st.container():
        submit_detail = st.button("登録実行 (投手成績反映)", type="primary", use_container_width=True, key="submit_pitching_action")

        if st.session_state.get("pitching_error_msg"):
            st.error(st.session_state["pitching_error_msg"])
            st.session_state["pitching_error_msg"] = None

        c_inn, c_outs = st.columns([1.2, 3.8])
        with c_inn:
            def_inn_ix = inn_options.index(current_inn_val) if current_inn_val in inn_options else 0
            current_inn = st.selectbox("イニング選択", inn_options, index=def_inn_ix, label_visibility="collapsed")
            st.session_state["p_det_inn"] = current_inn
        
        with c_outs:
            disp_outs = 0
            if not today_pitching_df.empty and "イニング" in today_pitching_df.columns:
                p_inn_df_disp = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                single_out_list = ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"]
                s_outs = len(p_inn_df_disp[p_inn_df_disp["結果"].isin(single_out_list)]) if "結果" in p_inn_df_disp.columns else 0
                d_outs = len(p_inn_df_disp[p_inn_df_disp["結果"] == "併殺打"]) * 2 if "結果" in p_inn_df_disp.columns else 0
                disp_outs = (s_outs + d_outs) % 3

            b_cnt = st.session_state.get("p_b_count", 0)
            s_cnt = st.session_state.get("p_s_count", 0)
            p_cnt = st.session_state.get("p_pitch_count", 0)

            st.markdown(render_bso_indicator(disp_outs, b_cnt, s_cnt, p_cnt), unsafe_allow_html=True)

            b_col1, b_col2, b_col3, b_col4 = st.columns([1.1, 1.1, 1.1, 0.8])

            with b_col1:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#22c55e;'>🟢 ボール</div>", unsafe_allow_html=True)
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("➖", key="btn_p_b_sub", use_container_width=True):
                        st.session_state["p_pitch_count"] = max(0, p_cnt - 1)
                        st.session_state["p_b_count"] = max(0, b_cnt - 1)
                        st.rerun()
                with bc2:
                    if st.button("➕", key="btn_p_b_add", use_container_width=True):
                        st.session_state["p_pitch_count"] = p_cnt + 1
                        if b_cnt < 3:
                            st.session_state["p_b_count"] = b_cnt + 1
                        st.rerun()

            with b_col2:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#eab308;'>🟡 ストライク</div>", unsafe_allow_html=True)
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button("➖", key="btn_p_s_sub", use_container_width=True):
                        st.session_state["p_pitch_count"] = max(0, p_cnt - 1)
                        st.session_state["p_s_count"] = max(0, s_cnt - 1)
                        st.rerun()
                with sc2:
                    if st.button("➕", key="btn_p_s_add", use_container_width=True):
                        st.session_state["p_pitch_count"] = p_cnt + 1
                        if s_cnt < 2:
                            st.session_state["p_s_count"] = s_cnt + 1
                        st.rerun()

            with b_col3:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#6b7280;'>⚪ ファール</div>", unsafe_allow_html=True)
                fc1, fc2 = st.columns(2)
                with fc1:
                    if st.button("➖", key="btn_p_f_sub", use_container_width=True):
                        st.session_state["p_pitch_count"] = max(0, p_cnt - 1)
                        st.rerun()
                with fc2:
                    if st.button("➕", key="btn_p_f_add", use_container_width=True):
                        st.session_state["p_pitch_count"] = p_cnt + 1
                        if s_cnt < 2:
                            st.session_state["p_s_count"] = s_cnt + 1
                        st.rerun()

            with b_col4:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#374151;'>リセット</div>", unsafe_allow_html=True)
                if st.button("🔄", key="btn_p_reset_bso", use_container_width=True):
                    st.session_state["p_b_count"] = 0
                    st.session_state["p_s_count"] = 0
                    st.session_state["p_pitch_count"] = 0
                    st.rerun()

        st.divider()

        c_mid1, c_mid2, c_mid3, c_mid4 = st.columns([1.0, 1.0, 2.0, 2.0])
        with c_mid1: 
            st.session_state["opp_batter_count"] = st.number_input("相手打順人数", 1, 20, value=st.session_state["opp_batter_count"])
        with c_mid2: 
            st.session_state["opp_batter_index"] = st.number_input("現在の打順", 1, st.session_state["opp_batter_count"], value=st.session_state["opp_batter_index"])
        
        with c_mid3:
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>投球結果</div>", unsafe_allow_html=True)
            current_res = st.session_state.get("pitching_quick_sr")
            current_dirs = st.session_state.get("pitching_quick_sd", [])
            
            current_run = st.session_state.get("pitching_quick_run")
            run_val = current_run if current_run is not None else 0
            
            current_er = st.session_state.get("pitching_quick_er")
            er_val = current_er if current_er is not None else 0
            
            res_label = f" 🟢 {current_res}" if current_res else ""
            dir_label = f" ({''.join(current_dirs)})" if current_dirs else ""
            run_er_label = f" [失点{run_val}/自責{er_val}]" if (run_val > 0 or er_val > 0 or current_res) else ""
            
            summary_btn_label = f"投球結果{res_label}{dir_label}{run_er_label} 🔽"
            
            with st.popover(summary_btn_label, use_container_width=True):
                st.markdown("##### ⚾ 投球結果を選択")
                res_options = ["凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", 
                               "振り逃げ三振", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "ボーク", "暴投", "捕逸", "牽制死", "盗塁死", "盗塁", "走塁死"]
                st.pills(
                    "投球結果",
                    res_options,
                    key="pitching_quick_sr",
                    label_visibility="collapsed"
                )

                st.markdown("---")
                st.markdown("##### ⚾ 打球方向を選択（複数選択可・最大2つ）")
                dir_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                st.pills(
                    "打球方向",
                    dir_options,
                    selection_mode="multi",
                    key="pitching_quick_sd",
                    label_visibility="collapsed"
                )

                st.markdown("---")
                st.markdown("##### ⚾ 失点を選択 (0〜4)")
                run_options = [0, 1, 2, 3, 4]
                st.pills(
                    "失点",
                    run_options,
                    key="pitching_quick_run",
                    label_visibility="collapsed"
                )

                st.markdown("---")
                st.markdown("##### ⚾ 自責点を選択 (0〜4)")
                er_options = [0, 1, 2, 3, 4]
                st.pills(
                    "自責点",
                    er_options,
                    key="pitching_quick_er",
                    label_visibility="collapsed"
                )

                st.markdown("---")
                if st.button("🔄 入力をすべてクリア", use_container_width=True, key="pitching_all_clear_btn"):
                    st.session_state["pitching_quick_sr"] = None
                    st.session_state["pitching_quick_sd"] = []
                    st.session_state["pitching_quick_run"] = 0
                    st.session_state["pitching_quick_er"] = 0
                    st.session_state["p_b_count"] = 0
                    st.session_state["p_s_count"] = 0
                    st.session_state["p_pitch_count"] = 0
                    st.rerun()

        with c_mid4:
            st.markdown("<div style='font-size:14px; font-weight:bold; margin-bottom:4px;'>試合終了・記録確定</div>", unsafe_allow_html=True)
            dec_p_val = st.session_state.get("quick_dec_pitcher")
            dec_t_val = st.session_state.get("quick_dec_type")
            
            dec_p_short = local_fmt(dec_p_val).split(" (")[0] if dec_p_val else ""
            dec_label_part = f" 🟢 {dec_p_short}【{dec_t_val}】" if (dec_p_val and dec_t_val) else ""
            
            dec_btn_label = f"🏆 試合終了・記録確定{dec_label_part} 🔽"
            
            with st.popover(dec_btn_label, use_container_width=True):
                st.markdown("##### 🏆 公式記録（勝敗・セーブ）の確定")
                
                st.markdown("##### 投手を選択")
                st.pills(
                    "公式記録投手",
                    ALL_PLAYERS,
                    format_func=local_fmt,
                    key="quick_dec_pitcher",
                    label_visibility="collapsed"
                )
                
                st.markdown("---")
                st.markdown("##### 記録の種類を選択")
                dec_t_opts = ["勝利", "敗戦", "セーブ", "ホールド"]
                st.pills("記録", dec_t_opts, key="quick_dec_type", label_visibility="collapsed")
                
                st.markdown("---")
                if st.button("🏆 この内容で確定して保存", type="primary", use_container_width=True, key="quick_dec_submit_btn"):
                    dec_p = st.session_state.get("quick_dec_pitcher")
                    dec_t = st.session_state.get("quick_dec_type")
                    if not dec_p:
                        st.error("投手を選択してください")
                    elif not dec_t:
                        st.error("内容を選択してください")
                    else:
                        target_player = dec_p.split(" (")[0]
                        mask = (df_pitching["日付"].astype(str) == selected_date_str) & (df_pitching["選手名"] == target_player) if not df_pitching.empty and "日付" in df_pitching.columns and "選手名" in df_pitching.columns else pd.Series([False]*len(df_pitching))
                        if not df_pitching.empty and not df_pitching[mask].empty:
                            df_pitching.loc[mask, "勝敗"] = dec_t
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=df_pitching)
                            st.cache_data.clear()
                            st.success(f"✅ {target_player} 選手を「{dec_t}」で確定しました！")
                            st.session_state["quick_dec_pitcher"] = None
                            st.session_state["quick_dec_type"] = None
                            import time
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("本日の登板記録が見つかりません。")

        st.divider()

    if submit_detail:
        def_pitcher = ""
        if not today_batting_df.empty and "守備位置" in today_batting_df.columns:
            latest_pitcher_rows = today_batting_df[today_batting_df["守備位置"] == "投"]
            if not latest_pitcher_rows.empty:
                def_pitcher = str(latest_pitcher_rows.iloc[-1]["選手名"])
        if not def_pitcher:
            lineup = st.session_state.get("saved_lineup")
            if isinstance(lineup, dict):
                for i in range(20):
                    if lineup.get(f"pos_{i}") == "投":
                        raw_name = lineup.get(f"name_{i}", "")
                        if raw_name:
                            def_pitcher = str(raw_name).split(" (")[0]
                        break
        if not def_pitcher:
            def_pitcher = str(st.session_state.get("shared_starting_pitcher", ""))
        
        matched_p = next((p for p in ALL_PLAYERS if p.split(" (")[0].strip() == def_pitcher.strip() or p == def_pitcher), None)
        input_name = matched_p if matched_p else "不明"

        def_catcher = ""
        if not today_batting_df.empty and "守備位置" in today_batting_df.columns:
            latest_catcher_rows = today_batting_df[today_batting_df["守備位置"] == "捕"]
            if not latest_catcher_rows.empty:
                def_catcher = str(latest_catcher_rows.iloc[-1]["選手名"])
        if not def_catcher:
            lineup = st.session_state.get("saved_lineup")
            if isinstance(lineup, dict):
                for i in range(20):
                    if lineup.get(f"pos_{i}") == "捕":
                        raw_name = lineup.get(f"name_{i}", "")
                        if raw_name:
                            def_catcher = str(raw_name).split(" (")[0]
                        break
        
        matched_c = next((p for p in ALL_PLAYERS if p.split(" (")[0].strip() == def_catcher.strip() or p == def_catcher), None)
        target_catcher_disp = matched_c if matched_c else "不明"
        
        p_res = st.session_state.get("pitching_quick_sr")
        target_fielder_pos_list = st.session_state.get("pitching_quick_sd", [])
        
        p_run = st.session_state.get("pitching_quick_run")
        p_run = p_run if p_run is not None else 0
        
        p_er = st.session_state.get("pitching_quick_er")
        p_er = p_er if p_er is not None else 0
        
        require_dir_results = ["凡退(ゴロ)", "凡退(フライ)", "失策(ゴロ)", "失策(フライ)", "併殺打", "犠打(ゴロ)", "犠打(フライ)", "野選"]

        if not p_res:
            st.session_state["pitching_error_msg"] = "⚠️ 結果を選択してください。"
            st.rerun()
        elif p_res in require_dir_results and not target_fielder_pos_list:
            st.session_state["pitching_error_msg"] = f"⚠️ 「{p_res}」を登録するには、打球方向を選択してください。"
            st.rerun()
        elif p_res == "本塁打" and p_run == 0: 
            st.session_state["pitching_error_msg"] = "⚠️ 本塁打は失点1以上必須です。"
            st.rerun()
        else:
            target_pitcher_name = str(input_name).split(" (")[0].strip()
            target_fielder_pos_str = "-".join(target_fielder_pos_list)

            fielder_display = ""
            if target_fielder_pos_list:
                lineup = st.session_state.get("saved_lineup", {})
                name_parts = []
                for pos in target_fielder_pos_list:
                    found_name = ""
                    for i in range(20):
                        if lineup.get(f"pos_{i}") == pos:
                            found_name = lineup.get(f"name_{i}", "").split(" (")[0].strip()
                            break
                    if not found_name and not today_batting_df.empty and "守備位置" in today_batting_df.columns:
                        match_pos = today_batting_df[today_batting_df["守備位置"] == pos]
                        if not match_pos.empty:
                            found_name = str(match_pos.iloc[-1]["選手名"]).split(" (")[0].strip()

                    if found_name:
                        name_parts.append(found_name)
                    else:
                        name_parts.append(f"({pos})")
                fielder_display = "-".join(name_parts)

            add_outs = 0
            if p_res == "併殺打":
                add_outs = 2
            elif p_res in ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"]:
                add_outs = 1
            
            add_hits = 1 if p_res in ["単打", "二塁打", "三塁打", "本塁打"] else 0
            add_strikeouts = 1 if p_res in ["三振", "振り逃げ三振"] else 0
            batter_idx_str = f"{st.session_state['opp_batter_index']}"

            if p_res in ["盗塁", "盗塁死"]:
                target_fielder_pos_str = "捕"
                target_catcher_name = str(target_catcher_disp).split(" (")[0].strip() if target_catcher_disp else ""
                fielder_display = target_catcher_name

            rec = {
                "日付": selected_date_str, 
                "グラウンド": ground_name, 
                "対戦相手": opp_team, 
                "試合種別": match_type,
                "イニング": current_inn, 
                "選手名": target_pitcher_name,       
                "守備位置": target_fielder_pos_str,  
                "打球方向": target_fielder_pos_str,  
                "処理野手": fielder_display,         
                "結果": p_res,                   
                "失点": p_run, 
                "自責点": p_er,
                "勝敗": "ー", 
                "被安打": add_hits, 
                "奪三振": add_strikeouts,        
                "アウト数": add_outs, 
                "種別": f"詳細:{batter_idx_str}番打者"
            }

            records_to_save = [rec] 

            conn.update(
                spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=pd.concat([df_pitching, pd.DataFrame(records_to_save)], 
                ignore_index=True)
            )
            st.cache_data.clear()

            st.session_state["needs_pitching_form_clear"] = True
            
            p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn] if not today_pitching_df.empty and "イニング" in today_pitching_df.columns else pd.DataFrame()
            single_out_list = ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"]
            existing_single_outs = len(p_inn_df[p_inn_df["結果"].isin(single_out_list)]) if not p_inn_df.empty and "結果" in p_inn_df.columns else 0
            existing_double_outs = len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2 if not p_inn_df.empty and "結果" in p_inn_df.columns else 0
            total_outs_after = existing_single_outs + existing_double_outs + add_outs
            
            if total_outs_after >= 3:
                try:
                    curr_idx = inn_options.index(current_inn)
                    if curr_idx < len(inn_options) - 1:
                        st.session_state["p_det_inn"] = inn_options[curr_idx + 1]
                        st.toast(f"⚾️ 3アウトチェンジ！ {st.session_state['p_det_inn']}へ進みます")
                    else: 
                        st.session_state["p_det_inn"] = current_inn
                except: 
                    st.session_state["p_det_inn"] = current_inn
            else:
                st.session_state["p_det_inn"] = current_inn

            non_batter_events = ["盗塁", "盗塁死", "牽制死", "暴投", "捕逸", "ボーク", "走塁死"]
            if p_res not in non_batter_events:
                st.session_state["opp_batter_index"] = (st.session_state["opp_batter_index"] % st.session_state["opp_batter_count"]) + 1
            
            st.success(f"✅ {target_pitcher_name}投手の記録を保存しました")
            import time
            time.sleep(0.5)
            st.rerun()

    st.write("")
    st.markdown("#### 📊 全イニング 攻撃・守備 詳細履歴")
    
    has_batting_history = not today_batting_df.empty
    has_pitching_history = not today_pitching_df.empty and "種別" in today_pitching_df.columns and not today_pitching_df[today_pitching_df["種別"].str.contains("詳細", na=False)].empty

    if has_batting_history or has_pitching_history:
        exclude_res = ["スタメン", "守備変更", "交代", "ベンチ", "試合前", "まとめ入力", "", "nan"]
        valid_batting_df = pd.DataFrame()
        if not today_batting_df.empty and "結果" in today_batting_df.columns:
            valid_batting_df = today_batting_df[~today_batting_df["結果"].astype(str).isin(exclude_res)].copy()

        valid_pitching_df = pd.DataFrame()
        if not today_pitching_df.empty and "種別" in today_pitching_df.columns:
            valid_pitching_df = today_pitching_df[today_pitching_df["種別"].str.contains("詳細", na=False)].copy()

        raw_inns = list(set(
            (valid_batting_df["イニング"].dropna().astype(str).tolist() if not valid_batting_df.empty and "イニング" in valid_batting_df.columns else []) + 
            (valid_pitching_df["イニング"].dropna().astype(str).tolist() if not valid_pitching_df.empty and "イニング" in valid_pitching_df.columns else [])
        ))
        
        exclude_inns = ["まとめ入力", "試合前", "ベンチ", "", "nan", "None"]
        active_innings = [inn for inn in raw_inns if inn not in exclude_inns]

        def inning_sort_key(inn):
            inn_str = str(inn)
            is_ext = 1 if "延長" in inn_str else 0
            m = re.search(r'(\d+)', inn_str)
            num = int(m.group(1)) if m else 99
            if "表" in inn_str:
                sub = 0
            elif "裏" in inn_str:
                sub = 1
            else:
                sub = 2
            return (is_ext, num, sub)

        active_innings.sort(key=inning_sort_key)

        if active_innings:
            for inn in active_innings:
                inn_id = inn.replace("回", "").replace("表", "").replace("裏", "")
                st.markdown(f"<div id='inning-{inn_id}' style='scroll-margin-top: 100px;'></div>", unsafe_allow_html=True)
                
                inn_bat_df = valid_batting_df[valid_batting_df["イニング"] == inn] if not valid_batting_df.empty and "イニング" in valid_batting_df.columns else pd.DataFrame()
                if not inn_bat_df.empty:
                    st.markdown("---")
                    st.markdown(f"### 📍 **{inn}（攻撃）**")
                    bat_items = []
                    for _, row in inn_bat_df.iterrows():
                        b_order = row.get("打順", "")
                        try:
                            b_order_str = f"{int(float(b_order))}番" if pd.notna(b_order) and str(b_order).strip() != "" else ""
                        except:
                            b_order_str = f"{b_order}番" if b_order else ""

                        p_name = row.get("選手名", "")
                        res = row.get("結果", "")
                        direction = row.get("打球方向", "")
                        rbi = pd.to_numeric(row.get("打点", 0), errors='coerce')
                        run = pd.to_numeric(row.get("得点", 0), errors='coerce')
                        
                        res_str = str(res)
                        if direction and str(direction) not in ["---", "nan", "None", ""]:
                            res_str = f"{direction}{res_str}"
                        if pd.notna(rbi) and rbi > 0:
                            res_str = f"{res_str} ・ 打点{int(rbi)}"
                        if pd.notna(run) and run > 0:
                            res_str = f"{res_str} 🟢得点"
                            
                        bat_items.append({
                            "打順": b_order_str,
                            "選手名": p_name,
                            "結果": res_str
                        })
                    df_bat_disp = pd.DataFrame(bat_items).T
                    
                    def highlight_batting(val):
                        if isinstance(val, str):
                            if "打点" in val:
                                return "color: red; font-weight: bold;"
                            elif any(hit in val for hit in ["単打", "二塁打", "三塁打", "本塁打"]):
                                return "color: blue; font-weight: bold;"
                        return ""
                        
                    try:
                        styled_bat = df_bat_disp.style.map(highlight_batting)
                    except AttributeError:
                        styled_bat = df_bat_disp.style.applymap(highlight_batting)
                        
                    st.dataframe(styled_bat, use_container_width=True)

                inn_pit_df = valid_pitching_df[valid_pitching_df["イニング"] == inn] if not valid_pitching_df.empty and "イニング" in valid_pitching_df.columns else pd.DataFrame()
                if not inn_pit_df.empty:
                    st.markdown("---")
                    st.markdown(f"### 📍 **{inn}（守備）**")
                    pit_items = []
                    for _, row in inn_pit_df.iterrows():
                        raw_b_idx = str(row["種別"]).split(":")[1].replace("番打者", "") if ":" in str(row["種別"]) else "?"
                        try:
                            b_idx = f"{int(float(raw_b_idx))}番"
                        except:
                            b_idx = f"{raw_b_idx}番" if raw_b_idx != "?" else "?"

                        raw_res = str(row.get('結果', ''))
                        pos_str = str(row.get('打球方向', '')) or str(row.get('守備位置', ''))
                        if pos_str and pos_str not in ["nan", "None", ""]:
                            raw_res = f"{raw_res}({pos_str})"
                        fielder_name = str(row.get('処理野手', ''))
                        if fielder_name and fielder_name not in ["nan", "None", ""]:
                            clean_name = fielder_name.replace("(", "").replace(")", "")
                            res_text = f"{raw_res} [{clean_name}]"
                        else:
                            res_text = raw_res
                        rows_val = pd.to_numeric(row.get('失点', 0), errors='coerce')
                        runs = int(rows_val) if pd.notna(rows_val) else 0
                        if runs > 0:
                            res_text = f"{res_text} 💥失点{runs}"
                        pit_items.append({
                            "打順": b_idx, 
                            "投手": row["選手名"], 
                            "結果": res_text
                        })
                    df_pit_disp = pd.DataFrame(pit_items).T
                    
                    def highlight_pitching(val):
                        if isinstance(val, str):
                            if "💥失点" in val:
                                return "color: red; font-weight: bold;"
                            elif any(hit in val for hit in ["単打", "二塁打", "三塁打", "本塁打"]):
                                return "color: blue; font-weight: bold;"
                        return ""
                    
                    try:
                        styled_pit = df_pit_disp.style.map(highlight_pitching)
                    except AttributeError:
                        styled_pit = df_pit_disp.style.applymap(highlight_pitching)
                        
                    st.dataframe(styled_pit, use_container_width=True)
        else:
            st.caption("詳細データはまだありません。")
    else:
        st.caption("詳細データはまだありません。")