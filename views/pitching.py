import streamlit as st
import pandas as pd
import requests
from streamlit_gsheets import GSheetsConnection
from config.settings import ALL_PLAYERS, SPREADSHEET_URL, PLAYER_NUMBERS, MY_TEAM
from utils.ui import render_scoreboard, render_out_indicator_3, fmt_player_name

def local_fmt(name):
    return fmt_player_name(name, PLAYER_NUMBERS)

def show_pitching_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order):
    conn = st.connection("gsheets", type=GSheetsConnection)
    is_kagura_top = (kagura_order == "先攻 (表)")

    # フィルタリング
    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str]

    # モード選択
    st.markdown("### 📝 入力モード")
    input_mode_p = st.radio("モードを選択してください", ["詳細入力 (1打席ごと)", "選手別まとめ入力 (詳細不明・過去データ用)"], horizontal=True, key="pitching_mode_radio")
    
    scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"] if not today_batting_df.empty else today_batting_df
    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()

    # ---------------------------------------------------------
    # A. 詳細入力モード
    # ---------------------------------------------------------
    if input_mode_p == "詳細入力 (1打席ごと)":
        # 0. 日付変更の検知とクリア (別の日付のデータが混ざるのを防ぐ)
        if "last_p_date" not in st.session_state:
            st.session_state["last_p_date"] = selected_date_str
        
        if st.session_state["last_p_date"] != selected_date_str:
            # 日付が変わった場合、関連するセッション状態をリセット
            keys_to_reset = ["p_det_inn", "opp_batter_index", f"sync_{st.session_state['last_p_date']}"]
            for k in keys_to_reset:
                if k in st.session_state: del st.session_state[k]
            st.session_state["last_p_date"] = selected_date_str

        # 1. セッションステートの初期化
        if "opp_batter_index" not in st.session_state: st.session_state["opp_batter_index"] = 1
        if "opp_batter_count" not in st.session_state: st.session_state["opp_batter_count"] = 9
        if "p_det_inn" not in st.session_state: st.session_state["p_det_inn"] = "1回"

        # 2. 【復元ロジック】日付選択後の初回のみ、スプレッドシートから状態を復元
        sync_key = f"sync_{selected_date_str}"
        if sync_key not in st.session_state:
            history_details = today_pitching_df[today_pitching_df["種別"].str.contains("詳細", na=False)]
            if not history_details.empty:
                last_rec = history_details.iloc[-1]
                st.session_state["p_det_inn"] = last_rec["イニング"]
                try:
                    last_idx = int(str(last_rec["種別"]).split(":")[1].replace("番打者", ""))
                    st.session_state["opp_batter_index"] = (last_idx % st.session_state["opp_batter_count"]) + 1
                except:
                    pass
            else:
                st.session_state["p_det_inn"] = "1回"
                st.session_state["opp_batter_index"] = 1
            st.session_state[sync_key] = True

        # --- 成績計算ロジック (既存) ---
        current_season_pitching = {}
        if not df_pitching.empty:
            target_year = str(pd.to_datetime(selected_date_str).year)
            df_p_season = df_pitching[pd.to_datetime(df_pitching["日付"]).dt.year.astype(str) == target_year].copy()
            for p in ALL_PLAYERS:
                p_df = df_p_season[(df_p_season["投手名"] == p) | (df_p_season["選手名"] == p)]
                p_key = local_fmt(p)
                if p_df.empty:
                    current_season_pitching[p_key] = " 防御率 -.-- (0勝 0敗)"
                    continue
                er = pd.to_numeric(p_df["自責点"], errors='coerce').fillna(0).sum()
                outs = pd.to_numeric(p_df["アウト数"], errors='coerce').fillna(0).sum()
                wins = p_df[p_df["勝敗"].astype(str).str.contains("勝")].shape[0]
                loses = p_df[p_df["勝敗"].astype(str).str.contains("負|敗")].shape[0]
                era = (er * 7) / (outs / 3) if outs > 0 else 0.0
                current_season_pitching[p_key] = f" 防御率 {era:.2f} ({wins}勝 {loses}敗)"

        # 3. 入力フォームエリア
        with st.form(key='score_input_form', clear_on_submit=True):
            # --- 上段：イニングとアウトカウント表示 ---
            c_top1, c_top2 = st.columns([1, 1])
            with c_top1:
                inn_options = [f"{i}回" for i in range(1, 10)] + ["延長"]
                current_val = st.session_state.get("p_det_inn", "1回")
                default_idx = inn_options.index(current_val) if current_val in inn_options else 0
                current_inn = st.selectbox("イニング", inn_options, index=default_idx)
            
            with c_top2:
                current_outs_db = 0
                if not today_pitching_df.empty:
                    p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                    outs_1 = len(p_inn_df[p_inn_df["結果"].isin(["三振", "凡退", "犠打", "犠飛", "凡打"])])
                    outs_2 = len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2
                    current_outs_db = (outs_1 + outs_2) % 3
                st.markdown(render_out_indicator_3(current_outs_db), unsafe_allow_html=True)

            # --- 中段：打順と投手選択 ---
            c_mid1, c_mid2, c_mid3 = st.columns([1.2, 1.2, 2.5])
            with c_mid1: 
                st.session_state["opp_batter_count"] = st.number_input("相手打順人数", 1, 20, value=st.session_state["opp_batter_count"])
            with c_mid2: 
                st.session_state["opp_batter_index"] = st.number_input("現在の打順", 1, st.session_state["opp_batter_count"], value=st.session_state["opp_batter_index"])
            
            with c_mid3:
                pitcher_list_opts = [""] + [local_fmt(p) for p in ALL_PLAYERS]
                default_pitcher_idx = 0
                shared_pitcher = st.session_state.get("shared_starting_pitcher")
                if shared_pitcher:
                    for i, p_opt in enumerate(pitcher_list_opts):
                        if shared_pitcher in p_opt:
                            default_pitcher_idx = i
                            break
                target_pitcher_disp = st.selectbox("登板投手", pitcher_list_opts, index=default_pitcher_idx)
                
                # 投手成績のクイック表示
                if "current_season_pitching" in locals() and target_pitcher_disp in current_season_pitching:
                    st.markdown(f"<div style='font-size:14px; color:#1e3a8a;'>{current_season_pitching[target_pitcher_disp]}</div>", unsafe_allow_html=True)

            # --- 下段：具体的な成績入力 ---
            st.divider()

            # カラム定義（c_er をここで定義するので NameError を防げます）
            c_res, c_np, c_run, c_er = st.columns([2, 1, 1, 1])
            
            with c_res:
                p_res = st.selectbox("結果", ["三振", "凡退", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "犠打", "犠飛", "併殺打", "失策", "野選", "打撃妨害", "ボーク", "暴投", "捕逸"], key="p_det_res")
            with c_np:
                p_np = st.number_input("球数", 0, 20, 1, key="p_det_np")
            with c_run:
                p_run = st.number_input("失点", 0, 4, 0, key="p_det_run")
            with c_er:
                # 解説をすべて help（ポップアップ）に移動
                p_er = st.number_input(
                    "自責", 
                    0, 4, 0, 
                    key="p_det_er", 
                    help="""【自責点(ER)の判定ガイド】
        ミスがないと仮定して、投手の責任で取られた点数か判断します。

        ✅ 自責点になる (YES)
        ・安打、四死球での出塁
        ・盗塁、暴投（WP）での進塁
        ・ミスがなければ生還していた場合

        ❌ 自責にならない (NO)
        ・エラー（失策）、パスボール（PB）
        ・打撃妨害での出塁
        ・「エラーがなければ3アウトでチェンジだった」後の失点

        💡 判定のコツ：
        「野手のミスが1つもなかったら、このランナーはホームに帰れたか？」で考えます。"""
                )

            submit_detail = st.form_submit_button("登録実行", type="primary", use_container_width=True)

        # 4. 登録実行処理
        if submit_detail:
            input_name = target_pitcher_disp if target_pitcher_disp else st.session_state.get("shared_starting_pitcher", "")
            if not input_name: 
                st.error("⚠️ 投手を選択してください")
            elif p_res == "本塁打" and p_runs == 0: 
                st.error("⚠️ 本塁打は失点1以上必須")
            elif p_res in ["凡退", "失策", "併殺打", "犠打", "野選"] and target_fielder_pos == "": 
                st.error("⚠️ 打球方向を選択してください")
            else:
                target_player = str(input_name).split(" (")[0].strip()
                target_pos = "投"
                
                fielder_display = f"({target_fielder_pos})"
                if target_fielder_pos:
                    lineup = st.session_state.get("saved_lineup", {})
                    for i in range(15):
                        if lineup.get(f"pos_{i}") == target_fielder_pos:
                            f_name = lineup.get(f"name_{i}", "").split(" (")[0]
                            if f_name: fielder_display = f"{f_name} ({target_fielder_pos})"
                            break

                add_outs = 2 if p_res == "併殺打" else (1 if p_res in ["三振", "凡退", "犠打", "犠飛", "野選"] else 0)
                add_hits = 1 if p_res in ["安打", "本塁打"] else 0
                batter_idx_str = f"{st.session_state['opp_batter_index']}"

                rec = {
                    "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": current_inn, "選手名": target_player, "位置": target_pos, "結果": p_res, 
                    "失点": p_runs, "自責点": p_er, "勝敗": "ー", "球数": 0, "被安打": add_hits, 
                    "アウト数": add_outs, "処理野手": fielder_display, "種別": f"詳細:{batter_idx_str}番打者"
                }
                
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, pd.DataFrame([rec])], ignore_index=True))
                st.cache_data.clear()
                
                # --- 3アウト自動進行ロジック ---
                p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                total_outs_after = (len(p_inn_df[p_inn_df["結果"].isin(["三振", "凡退", "犠打", "犠飛", "凡打"])]) + 
                                   len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2 + add_outs)
                
                if total_outs_after >= 3:
                    try:
                        curr_idx = inn_options.index(current_inn)
                        if curr_idx < len(inn_options) - 1:
                            st.session_state["p_det_inn"] = inn_options[curr_idx + 1]
                            st.toast(f"⚾️ 3アウトチェンジ！ {st.session_state['p_det_inn']}へ進みます")
                        else: st.session_state["p_det_inn"] = current_inn
                    except: st.session_state["p_det_inn"] = current_inn
                else:
                    st.session_state["p_det_inn"] = current_inn

                st.session_state["opp_batter_index"] = (st.session_state["opp_batter_index"] % st.session_state["opp_batter_count"]) + 1
                
                st.success(f"✅ {target_player}投手の記録を保存しました")
                import time
                time.sleep(0.5)
                st.rerun()
        
        # 責任投手登録
        with st.expander("🏆 試合終了・公式記録の確定", expanded=False):
            with st.form("pitcher_dec_form"):
                st.markdown("##### 1. 公式記録（勝敗・セーブ）の登録")
                c_d1, c_d2 = st.columns(2)
                dec_p = c_d1.selectbox("投手", [""] + [local_fmt(p) for p in ALL_PLAYERS])
                dec_t = c_d2.selectbox("内容", ["勝利", "敗戦", "セーブ", "ホールド"])
                if st.form_submit_button("🏆 確定して保存", type="primary", use_container_width=True):
                    if not dec_p: st.error("投手を選択してください")
                    else:
                        target_player = dec_p.split(" (")[0]
                        mask = (df_pitching["日付"].astype(str) == selected_date_str) & (df_pitching["選手名"] == target_player)
                        if not df_pitching[mask].empty:
                            df_pitching.loc[mask, "勝敗"] = dec_t
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=df_pitching)
                            st.cache_data.clear()
                            st.success(f"✅ {target_player} 選手を「{dec_t}」で確定")
                        else: st.warning("本日の登板記録が見つかりません。")

        # 5. 履歴表示 (消えていた部分を再実装)
        st.write("")
        st.markdown("#### 📊 全イニング 対戦詳細履歴")
        if not today_pitching_df.empty:
            history_df = today_pitching_df[today_pitching_df["種別"].str.contains("詳細", na=False)].copy()
            if not history_df.empty:
                for inn in [f"{i}回" for i in range(1, 10)] + ["延長"]:
                    inn_df = history_df[history_df["イニング"] == inn]
                    if not inn_df.empty:
                        st.write(f"**【{inn}】**")
                        display_items = []
                        for _, row in inn_df.iterrows():
                            b_idx = str(row["種別"]).split(":")[1].replace("番打者", "") if ":" in str(row["種別"]) else "?"
                            res_text = f"{row['結果']}({row['処理野手']})" if row['処理野手'] else row['結果']
                            display_items.append({"打順": f"{b_idx}番", "投手": local_fmt(row["選手名"]), "結果": res_text})
                        st.dataframe(pd.DataFrame(display_items).T, use_container_width=True)
            else: st.caption("詳細データはまだありません。")

        
    # ---------------------------------------------------------
    # B. まとめ入力モード
    # ---------------------------------------------------------
    elif input_mode_p == "選手別まとめ入力 (詳細不明・過去データ用)":
        st.info("複数の投手をまとめて入力します")
        input_cols_p = ["選手名", "勝敗", "投球回(整数)", "投球回(端数)", "球数", "被安打", "被本塁打", "奪三振", "与四死球", "失点", "自責点"]
        default_df_p = pd.DataFrame([["", "ー", 0, 0, 0, 0, 0, 0, 0, 0, 0]] * 5, columns=input_cols_p)

        options_stats = [i for i in range(51)]
        options_balls = [i for i in range(201)]
        
        with st.form("bulk_pitching_form"):
            edited_p = st.data_editor(
                default_df_p, num_rows="dynamic", use_container_width=True,
                column_config={
                    "選手名": st.column_config.SelectboxColumn("選手名", options=[""] + [local_fmt(p) for p in ALL_PLAYERS]),
                    "勝敗": st.column_config.SelectboxColumn("勝敗", options=["ー", "勝", "負", "S", "H"]),
                    "投球回(整数)": st.column_config.SelectboxColumn("回", options=options_stats, width="small"),
                    "投球回(端数)": st.column_config.SelectboxColumn("端数", options=[0, 1, 2], help="0, 1/3, 2/3"),
                    "球数": st.column_config.SelectboxColumn("球数", options=options_balls, width="small"),
                    "被安打": st.column_config.SelectboxColumn("被安", options=options_stats, width="small"),
                    "被本塁打": st.column_config.SelectboxColumn("被本", options=options_stats, width="small"),
                    "奪三振": st.column_config.SelectboxColumn("奪三", options=options_stats, width="small"),
                    "与四死球": st.column_config.SelectboxColumn("四死", options=options_stats, width="small"),
                    "失点": st.column_config.SelectboxColumn("失点", options=options_stats, width="small"),
                    "自責点": st.column_config.SelectboxColumn("自責", options=options_stats, width="small"),
                }
            )
            if st.form_submit_button("全データを登録"):
                recs = []
                for _, row in edited_p.iterrows():
                    p_name = row["選手名"]
                    display_name = row["選手名"]
                    p_name = display_name.split(" (")[0]
                    if not p_name: continue
                    i_int = int(row.get("投球回(整数)", 0))
                    i_frac = int(row.get("投球回(端数)", 0))
                    outs = (i_int * 3) + i_frac
                    
                    base_rec = {
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type, "イニング": "まとめ入力", "選手名": p_name,
                        "結果": "まとめ", "勝敗": row.get("勝敗", "ー"), "アウト数": outs, 
                        "球数": int(row.get("球数", 0)), "失点": int(row.get("失点", 0)), "自責点": int(row.get("自責点", 0)),
                        "被安打": int(row.get("被安打", 0)), "被本塁打": int(row.get("被本塁打", 0)), "奪三振": int(row.get("奪三振", 0)), "与四球": int(row.get("与四死球", 0)),
                        "種別": "まとめ"
                    }
                    recs.append(base_rec)
                
                if recs:
                    conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, pd.DataFrame(recs)], ignore_index=True))
                    st.cache_data.clear()
                    st.success("✅ 登録完了")
                    st.rerun()