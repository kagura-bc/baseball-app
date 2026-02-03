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
        if "opp_batter_index" not in st.session_state: st.session_state["opp_batter_index"] = 1
        if "opp_batter_count" not in st.session_state: st.session_state["opp_batter_count"] = 9

        # 今季成績計算
        current_season_pitching = {}
        if not df_pitching.empty:
            # (省略: 成績計算ロジックは元のまま)
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

        # 入力フォームエリア
        with st.form(key='score_input_form', clear_on_submit=True):
            c_top1, c_top2 = st.columns([1, 1])
            with c_top1:
                # イニング選択: ここのキー(p_det_inn)を使って後で履歴をフィルタリングします
                current_inn = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)] + ["延長"], key="p_det_inn")
            with c_top2:
                current_outs_db = 0
                if not today_pitching_df.empty:
                    p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                    outs_1 = len(p_inn_df[p_inn_df["結果"].isin(["三振", "凡退", "犠打", "犠飛", "凡打"])])
                    outs_2 = len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2
                    current_outs_db = (outs_1 + outs_2) % 3
                st.markdown(render_out_indicator_3(current_outs_db), unsafe_allow_html=True)

            c_mid1, c_mid2, c_mid3 = st.columns([1.2, 1.2, 2.5])
            with c_mid1: st.session_state["opp_batter_count"] = st.number_input("相手打順人数", 1, 20, st.session_state["opp_batter_count"])
            with c_mid2: st.session_state["opp_batter_index"] = st.number_input("現在の打順", 1, st.session_state["opp_batter_count"], st.session_state["opp_batter_index"])
            with c_mid3:
                # ★★★ 修正: 打撃画面から引き継いだ投手をデフォルトに設定 ★★★
                pitcher_list_opts = [""] + [local_fmt(p) for p in ALL_PLAYERS]
                default_pitcher_idx = 0
                
                # session_stateに保存された投手がいれば、そのインデックスを探す
                shared_pitcher = st.session_state.get("shared_starting_pitcher")
                if shared_pitcher:
                    # fmt_player_nameを通した形式とマッチングさせるか、元のリスト内で探す
                    # ここではリスト内の文字列に含まれているか確認（簡易検索）
                    for i, p_opt in enumerate(pitcher_list_opts):
                        if shared_pitcher in p_opt:
                            default_pitcher_idx = i
                            break

                target_pitcher_disp = st.selectbox("登板投手", pitcher_list_opts, index=default_pitcher_idx, key="p_det_name")
                
                if target_pitcher_disp in current_season_pitching:
                    st.markdown(f"<div style='font-size:14px; color:#1e3a8a;'>{current_season_pitching[target_pitcher_disp]}</div>", unsafe_allow_html=True)

            st.divider()
        
        # 結果登録フォーム
            c_res, c_fld, c_run, c_er = st.columns([1.5, 1.2, 0.8, 0.8])
            p_res = c_res.selectbox("打席結果", ["凡退", "三振", "安打", "本塁打", "四球", "死球", "犠打", "失策", "併殺打", "野選"], key="p_det_res")
            target_fielder_pos = c_fld.selectbox("打球方向 / 処理野手", [""] + ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"], key="p_det_fielder")
            p_runs = c_run.number_input("失点", min_value=0, step=1, key="p_det_r")
            p_er = c_er.number_input("自責", min_value=0, step=1, key="p_det_er")

            submit_detail = st.form_submit_button("登録実行", type="primary", use_container_width=True)

        if submit_detail:
            if not target_pitcher_disp: st.error("⚠️ 投手を選択してください")
            elif p_res == "本塁打" and p_runs == 0: st.error("⚠️ 本塁打は失点1以上必須")
            elif p_res in ["凡退", "失策", "併殺打", "犠打", "野選"] and target_fielder_pos == "": st.error("⚠️ 打球方向を選択してください")
            else:
                target_player = target_pitcher_disp.split(" (")[0]
                add_outs = 2 if p_res == "併殺打" else (1 if p_res in ["三振", "凡退", "犠打", "犠飛", "野選"] else 0)
                add_hits = 1 if p_res in ["安打", "本塁打"] else 0
                saved_fielder_str = f"({target_fielder_pos})" if target_fielder_pos else ""
                
                # 種別に詳細情報を埋め込む
                batter_idx_str = f"{st.session_state['opp_batter_index']}"

                rec = {
                    "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": current_inn, "選手名": target_player, 
                    "結果": p_res, "失点": p_runs, "自責点": p_er, "勝敗": "ー", "球数": 0,
                    "被安打": add_hits, "アウト数": add_outs, "処理野手": saved_fielder_str,
                    "種別": f"詳細:{batter_idx_str}番打者" # 打順をここに記録
                }
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=pd.concat([df_pitching, pd.DataFrame([rec])], ignore_index=True))
                st.cache_data.clear()
                
                st.session_state["opp_batter_index"] = (st.session_state["opp_batter_index"] % st.session_state["opp_batter_count"]) + 1
                st.success(f"✅ {p_res} を登録")
                import time
                time.sleep(0.5)
                st.rerun()

        # 責任投手登録 & 試合終了レポート
        with st.expander("🏆 試合終了・公式記録の確定", expanded=False):
            with st.form("pitcher_dec_form"):
                st.markdown("##### 1. 公式記録（勝敗・セーブ）の登録")
                c_d1, c_d2 = st.columns(2)
                dec_p = c_d1.selectbox("投手", [""] + [local_fmt(p) for p in ALL_PLAYERS])
                dec_t = c_d2.selectbox("内容", ["勝利", "敗戦", "セーブ", "ホールド"])
                
                # ボタン配置用のカラム
                c_btn1, c_btn2 = st.columns(2)
                
                with c_btn1:
                    # 現場で馴染みのある「公式記録」という表現に
                    submit_dec = st.form_submit_button("🏆 公式記録を確定", use_container_width=True)
                
                with c_btn2:
                    # LINE Notify終了に伴い、コピー用のレポートを生成するボタンに変更
                    send_report = st.form_submit_button("📋 共有用レポートを作成", type="primary", use_container_width=True)

                # --- A. 責任投手登録のロジック ---
                if submit_dec:
                    if not dec_p:
                        st.error("投手を選択してください")
                    else:
                        target_player = dec_p.split(" (")[0]
                        mask = (df_pitching["日付"].astype(str) == selected_date_str) & (df_pitching["選手名"] == target_player)
                        if not df_pitching[mask].empty:
                            df_pitching.loc[mask, "勝敗"] = dec_t
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet="投手成績", data=df_pitching)
                            st.cache_data.clear()
                            st.success(f"✅ {target_player} 選手の記録を「{dec_t}」で確定しました")
                        else:
                            st.warning("本日の登板記録が見つかりません。先に詳細入力を完了させてください。")

            # --- B. レポート表示ロジック (Formの外に出すことでコピーしやすく) ---
            if send_report:
                if today_pitching_df.empty:
                    st.error("本日の登板データがありません")
                else:
                    # 投手成績の集計
                    p_summary = today_pitching_df.groupby("選手名").agg({
                        "アウト数": "sum",
                        "被安打": "sum",
                        "失点": "sum",
                        "自責点": "sum",
                        "結果": lambda x: (x == "三振").sum() 
                    }).reset_index()

                    # メッセージ構築
                    msg = f"【試合終了レポート】\n"
                    msg += f"対戦: {opp_team}\n"
                    msg += f"球場: {ground_name}\n"
                    msg += "--------------------\n"
                    msg += "◆投手成績\n"
                    
                    for _, row in p_summary.iterrows():
                        inn_int = row['アウト数'] // 3
                        inn_frac = row['アウト数'] % 3
                        inn_str = f"{inn_int}.{inn_frac}" if inn_frac > 0 else f"{inn_int}"
                        msg += f"・{row['選手名']}: {inn_str}回 被安{row['被安打']} 奪三{row['結果']} 失{row['失点']}\n"
                    
                    msg += "--------------------\n"
                    msg += "※この内容をコピーしてLINEグループへ貼り付けてください。"

                    # 画面に表示
                    st.info("👇 下の枠内のテキストをコピーしてください")
                    st.text_area("LINE共有用テキスト", value=msg, height=250)
                    st.balloons() # 試合終了のお祝い演出
                    
        # ★★★ 新規追加: イニング別打席結果表示エリア ★★★
        st.write("")
        st.markdown("#### 📊 全イニング 対戦詳細履歴")
        
        if not today_pitching_df.empty:
            # 「詳細」を含むデータのみ抽出
            history_df = today_pitching_df[today_pitching_df["種別"].str.contains("詳細", na=False)].copy()
            
            if not history_df.empty:
                # イニングのリストを取得
                recorded_innings = [f"{i}回" for i in range(1, 10)] + ["延長"]
                
                for inn in recorded_innings:
                    inn_df = history_df[history_df["イニング"] == inn]
                    if not inn_df.empty:
                        st.write(f"**【{inn}】**")
                        
                        # 表示用データの作成
                        display_items = []
                        for _, row in inn_df.iterrows():
                            # 「詳細:X番」から数字を抽出、もしくは打順カラムから取得
                            b_idx = row.get("打順")
                            if pd.isna(b_idx) and ":" in str(row["種別"]):
                                b_idx = row["種別"].split(":")[1].replace("番", "")
                            
                            p_name = local_fmt(row["選手名"])
                            res_text = f"{row['結果']}({row['処理野手']})" if row['処理野手'] else row['結果']
                            
                            display_items.append({
                                "打順": f"{b_idx}番",
                                "投手": p_name,
                                "結果": res_text
                            })
                        
                        # 横長のエクセル風テーブルに変換
                        res_df = pd.DataFrame(display_items).set_index("打順").T
                        st.dataframe(res_df, use_container_width=True)
            else:
                st.caption("詳細データはまだありません。")

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