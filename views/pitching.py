import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import SPREADSHEET_URL, MY_TEAM, ALL_POSITIONS
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
    pos_options = [p for p in ALL_POSITIONS if p != ""] + ["未選択"]

    conn = st.connection("gsheets", type=GSheetsConnection)

    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str] if not df_batting.empty and "日付" in df_batting.columns else pd.DataFrame()
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str] if not df_pitching.empty and "日付" in df_pitching.columns else pd.DataFrame()
    
    scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"] if not today_batting_df.empty and "イニング" in today_batting_df.columns else df_batting
    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)

    current_match_id = f"{selected_date_str}_{opp_team}_{match_type}"
    if "last_p_match_id" not in st.session_state:
        st.session_state["last_p_match_id"] = current_match_id
    
    if st.session_state["last_p_match_id"] != current_match_id:
        keys_to_reset = ["p_det_inn", "opp_batter_index", "pitching_quick_sr", "pitching_quick_sd", "pitching_quick_run", "pitching_quick_er", "quick_dec_pitcher", "quick_dec_type", "p_b_count", "p_s_count", "p_pitch_count", "p_persistent_runners", "p_runner_1b", "p_runner_2b", "p_runner_3b", "p_runner_1b_res", "p_runner_2b_res", "p_runner_3b_res", "p_runner_1b_fielder", "p_runner_2b_fielder", "p_runner_3b_fielder", "opp_sn_dh_pitcher"]
        for k in list(st.session_state.keys()):
            if k in keys_to_reset or k.startswith("sync_") or k.startswith("opp_sp_") or k.startswith("opp_sn_"): 
                del st.session_state[k]
        st.session_state["last_p_match_id"] = current_match_id

    # 走者状態の初期化
    if "p_persistent_runners" not in st.session_state:
        st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}

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

    # 画面描画前の安全なフォームリセット処理
    if st.session_state.get("needs_pitching_form_clear"):
        st.session_state["pitching_quick_sr"] = None
        st.session_state["pitching_quick_sd"] = []
        st.session_state["pitching_quick_run"] = 0
        st.session_state["pitching_quick_er"] = 0
        st.session_state["p_b_count"] = 0
        st.session_state["p_s_count"] = 0
        st.session_state["p_pitch_count"] = 0
        for b_key in ["1b", "2b", "3b"]:
            st.session_state[f"p_runner_{b_key}_res"] = None
            st.session_state[f"p_runner_{b_key}_fielder"] = None
            st.session_state[f"p_runner_{b_key}"] = "走者" if st.session_state.get("p_persistent_runners", {}).get(b_key) else "なし"
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
                st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
                for b_key in ["1b", "2b", "3b"]:
                    st.session_state[f"p_runner_{b_key}"] = "なし"
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
                    if st.button("➖", key="btn_p_b_sub", use_container_width=True, disabled=(b_cnt <= 0)):
                        st.session_state["p_pitch_count"] = max(0, p_cnt - 1)
                        st.session_state["p_b_count"] = max(0, b_cnt - 1)
                        st.rerun()
                with bc2:
                    if st.button("➕", key="btn_p_b_add", use_container_width=True, disabled=(b_cnt >= 3)):
                        st.session_state["p_pitch_count"] = p_cnt + 1
                        if b_cnt < 3:
                            st.session_state["p_b_count"] = b_cnt + 1
                        st.rerun()

            with b_col2:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#eab308;'>🟡 ストライク</div>", unsafe_allow_html=True)
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button("➖", key="btn_p_s_sub", use_container_width=True, disabled=(s_cnt <= 0)):
                        st.session_state["p_pitch_count"] = max(0, p_cnt - 1)
                        st.session_state["p_s_count"] = max(0, s_cnt - 1)
                        st.rerun()
                with sc2:
                    if st.button("➕", key="btn_p_s_add", use_container_width=True, disabled=(s_cnt >= 2)):
                        st.session_state["p_pitch_count"] = p_cnt + 1
                        if s_cnt < 2:
                            st.session_state["p_s_count"] = s_cnt + 1
                        st.rerun()

            with b_col3:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#6b7280;'>⚪ ファール</div>", unsafe_allow_html=True)
                fc1, fc2 = st.columns(2)
                with fc1:
                    if st.button("➖", key="btn_p_f_sub", use_container_width=True, disabled=(p_cnt <= 0)):
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
                    st.session_state["needs_pitching_form_clear"] = True
                    st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
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
                            save_cols = [c for c in df_pitching.columns if c not in ["_date_str", "Year", "スコアラー"]]
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=df_pitching[save_cols])
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

        # ==========================================
        # 🏃 走者状況
        # ==========================================
        st.markdown("##### 🏃 走者状況")
        
        p_runners = st.session_state.get("p_persistent_runners", {"1b": None, "2b": None, "3b": None})

        for b_key in ["1b", "2b", "3b"]:
            sel_key = f"p_runner_{b_key}"
            if sel_key not in st.session_state or st.session_state[sel_key] is None:
                st.session_state[sel_key] = "走者" if p_runners.get(b_key) else "なし"

        runner_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死", "進塁1", "進塁2"]
        out_fielder_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

        r_cols = st.columns(3)

        # --- 3塁 (左側) ---
        with r_cols[0]:
            st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>3塁</div>", unsafe_allow_html=True)
            
            r3_val = st.session_state.get("p_runner_3b")
            r3_label = "🟢 走者 🔽" if r3_val == "走者" else "走者選択 🔽"
            with st.popover(r3_label, use_container_width=True):
                st.markdown("##### 3塁走者を選択")
                st.pills("3塁走者", ["なし", "走者"], key="p_runner_3b", label_visibility="collapsed")

            r3_res = st.session_state.get("p_runner_3b_res")
            r3_f = st.session_state.get("p_runner_3b_fielder")
            r3_btn = f"🟢 {r3_res}({r3_f}) 🔽" if (r3_res in ["走塁死", "盗塁死", "牽制死"] and r3_f) else (f"🟢 {r3_res} 🔽" if r3_res else "走塁結果 🔽")
            with st.popover(r3_btn, use_container_width=True):
                st.markdown("##### 3塁 走塁結果を選択")
                cur_r3_res = st.pills("3塁結果ピル", runner_res_options, key="p_runner_3b_res", label_visibility="collapsed")
                if cur_r3_res in ["走塁死", "盗塁死", "牽制死"]:
                    st.markdown("---")
                    st.markdown("##### 🎯 処理野手（補殺）を選択")
                    st.pills("3塁処理野手ピル", out_fielder_options, key="p_runner_3b_fielder", label_visibility="collapsed")

        # --- 2塁 (中央) ---
        with r_cols[1]:
            st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>2塁</div>", unsafe_allow_html=True)
            
            r2_val = st.session_state.get("p_runner_2b")
            r2_label = "🟢 走者 🔽" if r2_val == "走者" else "走者選択 🔽"
            with st.popover(r2_label, use_container_width=True):
                st.markdown("##### 2塁走者を選択")
                st.pills("2塁走者", ["なし", "走者"], key="p_runner_2b", label_visibility="collapsed")

            r2_res = st.session_state.get("p_runner_2b_res")
            r2_f = st.session_state.get("p_runner_2b_fielder")
            r2_btn = f"🟢 {r2_res}({r2_f}) 🔽" if (r2_res in ["走塁死", "盗塁死", "牽制死"] and r2_f) else (f"🟢 {r2_res} 🔽" if r2_res else "走塁結果 🔽")
            with st.popover(r2_btn, use_container_width=True):
                st.markdown("##### 2塁 走塁結果を選択")
                cur_r2_res = st.pills("2塁結果ピル", runner_res_options, key="p_runner_2b_res", label_visibility="collapsed")
                if cur_r2_res in ["走塁死", "盗塁死", "牽制死"]:
                    st.markdown("---")
                    st.markdown("##### 🎯 処理野手（補殺）を選択")
                    st.pills("2塁処理野手ピル", out_fielder_options, key="p_runner_2b_fielder", label_visibility="collapsed")

        # --- 1塁 (右側) ---
        with r_cols[2]:
            st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>1塁</div>", unsafe_allow_html=True)
            
            r1_val = st.session_state.get("p_runner_1b")
            r1_label = "🟢 走者 🔽" if r1_val == "走者" else "走者選択 🔽"
            with st.popover(r1_label, use_container_width=True):
                st.markdown("##### 1塁走者を選択")
                st.pills("1塁走者", ["なし", "走者"], key="p_runner_1b", label_visibility="collapsed")

            r1_res = st.session_state.get("p_runner_1b_res")
            r1_f = st.session_state.get("p_runner_1b_fielder")
            r1_btn = f"🟢 {r1_res}({r1_f}) 🔽" if (r1_res in ["走塁死", "盗塁死", "牽制死"] and r1_f) else (f"🟢 {r1_res} 🔽" if r1_res else "走塁結果 🔽")
            with st.popover(r1_btn, use_container_width=True):
                st.markdown("##### 1塁 走塁結果を選択")
                cur_r1_res = st.pills("1塁結果ピル", runner_res_options, key="p_runner_1b_res", label_visibility="collapsed")
                if cur_r1_res in ["走塁死", "盗塁死", "牽制死"]:
                    st.markdown("---")
                    st.markdown("##### 🎯 処理野手（補殺）を選択")
                    st.pills("1塁処理野手ピル", out_fielder_options, key="p_runner_1b_fielder", label_visibility="collapsed")

        st.session_state["p_persistent_runners"] = {
            "1b": "走者" if st.session_state.get("p_runner_1b") == "走者" else None,
            "2b": "走者" if st.session_state.get("p_runner_2b") == "走者" else None,
            "3b": "走者" if st.session_state.get("p_runner_3b") == "走者" else None,
        }

        st.divider()

        # ==========================================
        # 👥 相手オーダー一覧（可変人数対応：最大20名）
        # ==========================================
        opp_count = st.session_state.get("opp_batter_count", 9)
        curr_opp_idx = st.session_state.get("opp_batter_index", 1)

        # 打撃成績と完全統一した結果変換マップ
        RES_SHORT_MAP = {
            "本塁打": "本", "三塁打": "三", "二塁打": "二", "単打": "安",
            "三振": "振", "凡退(ゴロ)": "ゴ", "凡退(フライ)": "飛", "四球": "球", "死球": "死",
            "犠打(ゴロ)": "犠", "犠打(フライ)": "犠", "犠飛": "犠飛", "失策(ゴロ)": "失",
            "失策(フライ)": "失", "野選": "野", "併殺打": "併", "振り逃げ三振": "逃", "打撃妨害": "妨"
        }

        # 打者ごとの本日対戦履歴を事前集計（走塁「得点」を打席履歴から除外）
        opp_history_dict = {}
        if not today_pitching_df.empty and "種別" in today_pitching_df.columns:
            detail_df = today_pitching_df[today_pitching_df["種別"].str.contains("詳細:", na=False)].copy()
            
            for b_num in range(1, opp_count + 1):
                b_target_str = f"詳細:{b_num}番打者"
                rows = detail_df[detail_df["種別"] == b_target_str]
                
                if rows.empty:
                    continue
                    
                history_html = []
                count = 0
                stolen_base_count = 0
                total_runs = 0
                
                for _, row in rows.iterrows():
                    res = str(row.get("結果", ""))
                    runs_val = pd.to_numeric(row.get("失点", 0), errors='coerce')
                    r_val = int(runs_val) if pd.notna(runs_val) else 0
                    total_runs += r_val
                    
                    if res in ["盗塁", "盗塁成功"]:
                        stolen_base_count += 1
                        continue
                    elif res in ["盗塁死", "走塁死", "牽制死", "走塁記録", "進塁1", "進塁2", "進塁", "得点"]:
                        continue
                        
                    count += 1
                    res_short = RES_SHORT_MAP.get(res, res[:2] if len(res) >= 2 else res)
                    
                    raw_dir = str(row.get("打球方向", ""))
                    p_dir = raw_dir if raw_dir not in ["---", "nan", "None", "ー", ""] else ""
                    
                    if r_val > 0:
                        disp_text = f"{p_dir}{res_short}・{r_val}" if p_dir else f"{res_short}・{r_val}"
                    else:
                        disp_text = f"{p_dir}{res_short}" if p_dir else f"{res_short}"
                        
                    color_style = ""
                    is_hit = res in ["単打", "二塁打", "三塁打", "本塁打"]
                    
                    if is_hit and r_val > 0:
                        color_style = "color: red;"
                    elif r_val > 0:
                        color_style = "color: red;"
                    elif is_hit:
                        color_style = "color: blue;"
                        
                    history_html.append(f"<span style='{color_style}'>{count}({disp_text})</span>")
                
                if stolen_base_count > 0:
                    history_html.append(f"<span style='color: #800080;'>盗{stolen_base_count}</span>")
                
                if total_runs > 0:
                    history_html.append(f"<span style='color: green;'>得{total_runs}</span>")
                    
                opp_history_dict[b_num] = " ".join(history_html)

        for i in range(opp_count):
            order_num = i + 1
            pos_key = f"opp_sp_{i}"
            name_key = f"opp_sn_{i}"

            if pos_key not in st.session_state: st.session_state[pos_key] = "未選択"
            if name_key not in st.session_state: st.session_state[name_key] = "選手"

            is_current = (order_num == curr_opp_idx)

            with st.container(border=True):
                c_row = st.columns([0.8, 2.5, 3.5, 5.2])

                with c_row[0]:
                    prefix = "📍 " if is_current else ""
                    st.markdown(f"<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px; color:{'#22c55e' if is_current else '#333'};'>{prefix}{order_num}</div>", unsafe_allow_html=True)

                with c_row[1]:
                    cur_pos = st.session_state.get(pos_key, "未選択")
                    pos_btn_label = f"🟢 {cur_pos} 🔽" if cur_pos != "未選択" else "未選択 🔽"
                    with st.popover(pos_btn_label, use_container_width=True):
                        st.markdown(f"##### {order_num}番 守備位置を選択")
                        st.pills(f"相手守備 {i}", pos_options, key=pos_key, label_visibility="collapsed")

                with c_row[2]:
                    cur_name = st.session_state.get(name_key, "選手")
                    name_btn_label = f"🟢 {cur_name} 🔽" if cur_name != "選手" else "選手 🔽"
                    with st.popover(name_btn_label, use_container_width=True):
                        st.markdown(f"##### {order_num}番 選手を選択")
                        st.pills(f"相手選手 {i}", ["選手"], key=name_key, label_visibility="collapsed")

                with c_row[3]:
                    history_text = opp_history_dict.get(order_num, "")
                    st.markdown(f"<div style='font-size:15px; line-height:1.4; padding-top:6px; color:#444; overflow-x:auto; white-space:nowrap;'>{history_text}</div>", unsafe_allow_html=True)

        # ------------------------------------------
        # ⚾ 相手投手専用枠 (DH制使用時)
        # ------------------------------------------
        with st.container(border=True):
            c_dh_row = st.columns([0.8, 2.5, 3.5, 5.2])
            with c_dh_row[0]:
                st.markdown("<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;'>投</div>", unsafe_allow_html=True)
            with c_dh_row[1]:
                st.markdown("<div style='text-align:center; font-size:14px; font-weight:bold; padding-top:10px; color:#4f46e5;'>🟢 投 (DH時)</div>", unsafe_allow_html=True)
            with c_dh_row[2]:
                cur_opp_dh_p = st.session_state.get("opp_sn_dh_pitcher", "選手")
                name_btn_label = f"🟢 {cur_opp_dh_p} 🔽" if cur_opp_dh_p != "選手" else "相手投手 (DH時) 🔽"
                with st.popover(name_btn_label, use_container_width=True):
                    st.markdown("##### ⚾ 相手投手を選択")
                    st.pills("相手DH投手ピル", ["選手"], key="opp_sn_dh_pitcher", label_visibility="collapsed")
            with c_dh_row[3]:
                st.markdown("<div style='font-size:13px; color:#6b7280; padding-top:10px;'>※ DH制で打順に入らない相手投手を設定</div>", unsafe_allow_html=True)

        st.divider()
        col_disp1, col_disp2, col_disp3 = st.columns([2.0, 1.0, 1.0])
        with col_disp1:
            st.markdown(f"<div style='font-weight:bold; font-size:16px; line-height:2.4;'>👥 相手打順の表示人数: {st.session_state.get('opp_batter_count', 9)}人</div>", unsafe_allow_html=True)
        with col_disp2:
            if st.button("➖ 減らす", key="btn_opp_dec", use_container_width=True):
                if st.session_state["opp_batter_count"] > 9:
                    st.session_state["opp_batter_count"] -= 1
                    idx = st.session_state["opp_batter_count"]
                    for k in [f"opp_sn_{idx}", f"opp_sp_{idx}"]:
                        st.session_state.pop(k, None)
                    st.rerun()
        with col_disp3:
            if st.button("➕ 追加 (最大20)", key="btn_opp_inc", use_container_width=True):
                if st.session_state["opp_batter_count"] < 20:
                    st.session_state["opp_batter_count"] += 1
                    st.rerun()

        st.divider()

    if submit_detail:
        final_ground = ground_name or st.session_state.get("ground_name", "")
        final_opp = opp_team or st.session_state.get("opp_team", "")
        final_match_type = match_type or st.session_state.get("match_type", "")

        if not today_pitching_df.empty:
            if not final_ground and "グラウンド" in today_pitching_df.columns:
                valid_g = today_pitching_df["グラウンド"].dropna().astype(str).str.strip()
                valid_g = valid_g[~valid_g.isin(["", "nan", "None"])]
                if not valid_g.empty: final_ground = valid_g.iloc[-1]
            if not final_opp and "対戦相手" in today_pitching_df.columns:
                valid_o = today_pitching_df["対戦相手"].dropna().astype(str).str.strip()
                valid_o = valid_o[~valid_o.isin(["", "nan", "None"])]
                if not valid_o.empty: final_opp = valid_o.iloc[-1]
            if not final_match_type and "試合種別" in today_pitching_df.columns:
                valid_m = today_pitching_df["試合種別"].dropna().astype(str).str.strip()
                valid_m = valid_m[~valid_m.isin(["", "nan", "None"])]
                if not valid_m.empty: final_match_type = valid_m.iloc[-1]

        POS_ALIASES = {
            "投": ["投", "投手", "P", "1"],
            "捕": ["捕", "捕手", "C", "2"],
            "一": ["一", "一塁", "一塁手", "ファースト", "1B", "3"],
            "二": ["二", "二塁", "二塁手", "セカンド", "2B", "4"],
            "三": ["三", "三塁", "三塁手", "サード", "3B", "5"],
            "遊": ["遊", "遊撃", "遊撃手", "ショート", "SS", "6"],
            "左": ["左", "左翼", "左翼手", "レフト", "LF", "7"],
            "中": ["中", "中堅", "中堅手", "センター", "CF", "8"],
            "右": ["右", "右翼", "右翼手", "ライト", "RF", "9"],
            "指": ["指", "DH", "指名打者", "10"],
        }

        def is_same_pos(p1, p2):
            s1, s2 = str(p1).strip(), str(p2).strip()
            if not s1 or not s2: return False
            if s1 == s2: return True
            for k, aliases in POS_ALIASES.items():
                if s1 in aliases and s2 in aliases:
                    return True
            return False

        def get_player_by_position(target_pos):
            if not target_pos: return ""

            # DH使用時の投手優先検索
            if is_same_pos(target_pos, "投"):
                dh_p = st.session_state.get("sn_dh_pitcher", "")
                if dh_p:
                    clean_n = str(dh_p).split(" (")[0].strip()
                    if clean_n and clean_n not in ["nan", "None", "", "－"]:
                        return clean_n

            for dict_key in ["shared_lineup", "lineup_states", "saved_lineup"]:
                data = st.session_state.get(dict_key, {})
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            p_pos = v.get("pos", "")
                            p_name = v.get("name", "")
                            if p_pos and p_name and is_same_pos(p_pos, target_pos):
                                clean_n = str(p_name).split(" (")[0].strip()
                                if clean_n and clean_n not in ["nan", "None", "", "－"]:
                                    return clean_n
                    for i in range(20):
                        p_pos = data.get(f"pos_{i}", "")
                        p_name = data.get(f"name_{i}", "")
                        if p_pos and p_name and is_same_pos(p_pos, target_pos):
                            clean_n = str(p_name).split(" (")[0].strip()
                            if clean_n and clean_n not in ["nan", "None", "", "－"]:
                                return clean_n

            display_count = st.session_state.get("display_order_count", 20)
            for i in range(display_count):
                p_pos = st.session_state.get(f"sp{i}", "")
                p_name = st.session_state.get(f"sn{i}", "")
                if p_pos and p_name and is_same_pos(p_pos, target_pos):
                    clean_n = str(p_name).split(" (")[0].strip()
                    if clean_n and clean_n not in ["nan", "None", "", "－"]:
                        return clean_n

            if not today_batting_df.empty:
                for col in ["位置", "守備位置"]:
                    if col in today_batting_df.columns and "選手名" in today_batting_df.columns:
                        matched = today_batting_df[today_batting_df[col].astype(str).apply(lambda x: is_same_pos(x, target_pos))]
                        if not matched.empty:
                            for name_val in reversed(matched["選手名"].dropna().tolist()):
                                clean_n = str(name_val).split(" (")[0].strip()
                                if clean_n and clean_n not in ["nan", "None", "", "－"]:
                                    return clean_n

            return ""

        def_pitcher = get_player_by_position("投")
        if not def_pitcher:
            def_pitcher = str(st.session_state.get("shared_starting_pitcher", ""))
        
        matched_p = next((p for p in ALL_PLAYERS if p.split(" (")[0].strip() == def_pitcher.strip() or p == def_pitcher), None)
        input_name = matched_p if matched_p else (def_pitcher if def_pitcher else "不明")

        def_catcher = get_player_by_position("捕")
        matched_c = next((p for p in ALL_PLAYERS if p.split(" (")[0].strip() == def_catcher.strip() or p == def_catcher), None)
        target_catcher_disp = matched_c if matched_c else (def_catcher if def_catcher else "不明")
        
        p_res = st.session_state.get("pitching_quick_sr")
        target_fielder_pos_list = st.session_state.get("pitching_quick_sd", [])
        
        p_run = st.session_state.get("pitching_quick_run")
        p_run = p_run if p_run is not None else 0
        
        p_er = st.session_state.get("pitching_quick_er")
        p_er = p_er if p_er is not None else 0
        
        require_dir_results = ["凡退(ゴロ)", "凡退(フライ)", "失策(ゴロ)", "失策(フライ)", "併殺打", "犠打(ゴロ)", "犠打(フライ)", "野選"]

        has_runner_res = any(
            st.session_state.get(f"p_runner_{b_key}_res") for b_key in ["1b", "2b", "3b"]
        )

        cur_1b_runner = (st.session_state.get("p_runner_1b") == "走者")
        cur_2b_runner = (st.session_state.get("p_runner_2b") == "走者")
        cur_3b_runner = (st.session_state.get("p_runner_3b") == "走者")

        res_1b = st.session_state.get("p_runner_1b_res")
        res_2b = st.session_state.get("p_runner_2b_res")
        res_3b = st.session_state.get("p_runner_3b_res")

        b_to_1b_results = ["単打", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]
        b_to_2b_results = ["二塁打"]
        b_to_3b_results = ["三塁打"]

        if not p_res and not has_runner_res:
            st.session_state["pitching_error_msg"] = "⚠️ 投球結果または走塁結果を選択してください。"
            st.rerun()
        elif p_res and p_res in require_dir_results and not target_fielder_pos_list:
            st.session_state["pitching_error_msg"] = f"⚠️ 「{p_res}」を登録するには、打球方向を選択してください。"
            st.rerun()
        elif p_res == "本塁打" and p_run == 0: 
            st.session_state["pitching_error_msg"] = "⚠️ 本塁打は失点1以上必須です。"
            st.rerun()
        elif cur_1b_runner and p_res in b_to_1b_results and not res_1b:
            st.session_state["pitching_error_msg"] = "⚠️ 1塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        elif cur_2b_runner and p_res in b_to_2b_results and not res_2b:
            st.session_state["pitching_error_msg"] = "⚠️ 2塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        elif cur_3b_runner and p_res in b_to_3b_results and not res_3b:
            st.session_state["pitching_error_msg"] = "⚠️ 3塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        else:
            target_pitcher_name = str(input_name).split(" (")[0].strip()
            batter_idx_str = f"{st.session_state['opp_batter_index']}"
            records_to_save = []
            add_outs_total = 0

            # 1. 投球結果（打席結果）のレコード追加
            if p_res:
                target_fielder_pos_str = "-".join(target_fielder_pos_list)

                fielder_display = ""
                if target_fielder_pos_list:
                    name_parts = []
                    for pos in target_fielder_pos_list:
                        found_name = get_player_by_position(pos)
                        name_parts.append(found_name if found_name else f"({pos})")
                    fielder_display = "-".join(name_parts)

                add_outs = 0
                if p_res == "併殺打":
                    add_outs = 2
                elif p_res in ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"]:
                    add_outs = 1
                
                add_hits = 1 if p_res in ["単打", "二塁打", "三塁打", "本塁打"] else 0
                add_strikeouts = 1 if p_res in ["三振", "振り逃げ三振"] else 0

                if p_res in ["盗塁", "盗塁死"]:
                    target_fielder_pos_str = "捕"
                    target_catcher_name = str(target_catcher_disp).split(" (")[0].strip() if target_catcher_disp else ""
                    fielder_display = target_catcher_name

                # 打球・完了分として1球加算
                p_cnt_val = st.session_state.get("p_pitch_count", 0)
                final_pitch_count = p_cnt_val + 1

                rec = {
                    "日付": selected_date_str, 
                    "グラウンド": final_ground, 
                    "対戦相手": final_opp, 
                    "試合種別": final_match_type,
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
                    "種別": f"詳細:{batter_idx_str}番打者",
                    "球数": final_pitch_count,
                    "ストライク": st.session_state.get("p_s_count", 0),
                    "ボール": st.session_state.get("p_b_count", 0)
                }
                records_to_save.append(rec)
                add_outs_total += add_outs

            # 2. 独立した走塁結果のレコード追加
            for b_key in ["1b", "2b", "3b"]:
                r_res = st.session_state.get(f"p_runner_{b_key}_res")
                r_f = st.session_state.get(f"p_runner_{b_key}_fielder", "")

                if r_res:
                    r_outs = 1 if r_res in ["走塁死", "盗塁死", "牽制死"] else 0
                    r_run = 1 if r_res == "得点" else 0
                    
                    fielder_disp = ""
                    if r_f:
                        found_f_name = get_player_by_position(r_f)
                        fielder_disp = found_f_name if found_f_name else f"({r_f})"

                    runner_rec = {
                        "日付": selected_date_str, 
                        "グラウンド": final_ground, 
                        "対戦相手": final_opp, 
                        "試合種別": final_match_type,
                        "イニング": current_inn, 
                        "選手名": target_pitcher_name,       
                        "守備位置": r_f if r_f else "ー",  
                        "打球方向": r_f if r_f else "ー",  
                        "処理野手": fielder_disp,         
                        "結果": r_res,                   
                        "失点": r_run if not p_res else 0,
                        "自責点": r_run if not p_res else 0,
                        "勝敗": "ー", 
                        "被安打": 0, 
                        "奪三振": 0,        
                        "アウト数": r_outs, 
                        "種別": f"詳細:{batter_idx_str}番打者",
                        "ストライク": 0,
                        "ボール": 0
                    }
                    records_to_save.append(runner_rec)
                    add_outs_total += r_outs

            if records_to_save:
                updated_p_df = pd.concat([df_pitching, pd.DataFrame(records_to_save)], ignore_index=True)
                save_cols = [c for c in updated_p_df.columns if c not in ["_date_str", "Year", "スコアラー"]]
                conn.update(
                    spreadsheet=SPREADSHEET_URL, 
                    worksheet=ws_pitching, 
                    data=updated_p_df[save_cols]
                )
                st.cache_data.clear()

            # 打順進塁の判定（打席結果を伴う場合のみ進める）
            non_batter_events = ["盗塁", "盗塁死", "牽制死", "暴投", "捕逸", "ボーク", "走塁死"]
            if p_res and p_res not in non_batter_events:
                st.session_state["opp_batter_index"] = (st.session_state["opp_batter_index"] % st.session_state["opp_batter_count"]) + 1

            # 3アウト判定および走者の進塁計算
            p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn] if not today_pitching_df.empty and "イニング" in today_pitching_df.columns else pd.DataFrame()
            single_out_list = ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"]
            existing_single_outs = len(p_inn_df[p_inn_df["結果"].isin(single_out_list)]) if not p_inn_df.empty and "結果" in p_inn_df.columns else 0
            existing_double_outs = len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2 if not p_inn_df.empty and "結果" in p_inn_df.columns else 0
            total_outs_after = existing_single_outs + existing_double_outs + add_outs_total
            
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

            if total_outs_after >= 3:
                st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
            else:
                cur_1b = st.session_state["p_persistent_runners"]["1b"] is not None
                cur_2b = st.session_state["p_persistent_runners"]["2b"] is not None
                cur_3b = st.session_state["p_persistent_runners"]["3b"] is not None

                r1_next = "1b" if cur_1b else None
                r2_next = "2b" if cur_2b else None
                r3_next = "3b" if cur_3b else None

                # 1塁走者の結果反映
                if cur_1b and res_1b:
                    if res_1b in ["盗塁", "進塁1", "進塁"]:
                        r1_next = "2b"
                    elif res_1b == "進塁2":
                        r1_next = "3b"
                    elif res_1b in ["得点", "走塁死", "盗塁死", "牽制死"]:
                        r1_next = None

                # 2塁走者の結果反映
                if cur_2b and res_2b:
                    if res_2b in ["盗塁", "進塁1", "進塁"]:
                        r2_next = "3b"
                    elif res_2b in ["進塁2", "得点"]:
                        r2_next = None
                    elif res_2b in ["走塁死", "盗塁死", "牽制死"]:
                        r2_next = None

                # 3塁走者の結果反映
                if cur_3b and res_3b:
                    if res_3b in ["得点", "走塁死", "盗塁死", "牽制死", "盗塁", "進塁1", "進塁2", "進塁"]:
                        r3_next = None

                # 四球・死球（押し出し）
                if p_res in ["四球", "死球"]:
                    r1_next = "2b" if cur_1b else None
                    r2_next = "3b" if (cur_2b and cur_1b) else ("2b" if cur_2b else None)
                    r3_next = None if (cur_3b and cur_2b and cur_1b) else ("3b" if cur_3b else None)

                new_1b = (r1_next == "1b" or r2_next == "1b" or r3_next == "1b")
                new_2b = (r1_next == "2b" or r2_next == "2b" or r3_next == "2b")
                new_3b = (r1_next == "3b" or r2_next == "3b" or r3_next == "3b")

                # 打者自身の出塁による占有
                if p_res in ["単打", "四球", "死球", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]:
                    new_1b = True
                elif p_res == "二塁打":
                    new_2b = True
                elif p_res == "三塁打":
                    new_3b = True
                elif p_res in ["本塁打", "併殺打"]:
                    new_1b = False
                    new_2b = False
                    new_3b = False

                st.session_state["p_persistent_runners"] = {
                    "1b": "走者" if new_1b else None,
                    "2b": "走者" if new_2b else None,
                    "3b": "走者" if new_3b else None,
                }

            # 安全にフォームクリアを行うフラグを立てる
            st.session_state["needs_pitching_form_clear"] = True

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