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
                    "選手名": st.column_config.SelectboxColumn("選手名", options=[""] + [local_fmt(p) for p in ALL_PLAYERS]),
                    "守備": st.column_config.SelectboxColumn("守備", options=["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控", "他"]),
                    "打席数": st.column_config.NumberColumn("打席", min_value=0, step=1)
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
        # 今シーズンの成績計算 (表示用)
        current_season_stats = {}
        if not df_batting.empty:
            target_year_str = str(pd.to_datetime(selected_date_str).year)
            df_season = df_batting[pd.to_datetime(df_batting["日付"]).dt.year.astype(str) == target_year_str].copy()
            no_ab_list = ["四球", "死球", "犠打", "打撃妨害", "盗塁", "得点", "走塁死", "盗塁死", "牽制死", "スタメン", "ベンチ", "試合終了", "---", "守備交代"]
            hit_list = ["単打", "二塁打", "三塁打", "本塁打", "安打"]

            for p in ALL_PLAYERS:
                p_df = df_season[df_season["選手名"] == p]
                if p_df.empty:
                    current_season_stats[p] = " -.--- (0本 0点)"
                    continue
                hits = p_df[p_df["結果"].isin(hit_list)].shape[0]
                abs_count = p_df[~p_df["結果"].isin(no_ab_list)].shape[0]
                hr_count = p_df[p_df["結果"] == "本塁打"].shape[0]
                rbi_count = pd.to_numeric(p_df["打点"], errors='coerce').fillna(0).sum()
                avg = hits / abs_count if abs_count > 0 else 0.0
                current_season_stats[p] = f" .{int(avg*1000):03d} ({hr_count}本 {int(rbi_count)}点)"

        # 登録関数
        def submit_batting():
            current_bench = st.session_state.get("persistent_bench", [])
            new_records = []
            current_starters = []
            new_outs_count = 0
            has_homerun = False

            for i in range(15):
                p_name = st.session_state.get(f"sn{i}")
                p_res = st.session_state.get(f"sr{i}", "---")
                
                if p_name and p_res != "---":
                    current_starters.append(p_name)
                    p_pos = st.session_state.get(f"sp{i}", "")
                    rbi_val = int(st.session_state.get(f"si{i}", 0))

                    # バリデーション
                    if p_res == "本塁打" and rbi_val == 0:
                        st.error(f"⚠️ {p_name}: 本塁打は打点1以上が必要です")
                        return

                    run_val = 0; sb_val = 0; type_val = "打撃"
                    if p_res == "本塁打":
                        run_val = 1; has_homerun = True
                    elif p_res == "得点":
                        run_val = 1; type_val = "得点"; rbi_val = 0
                    elif p_res == "盗塁":
                        sb_val = 1; type_val = "盗塁"; rbi_val = 0

                    if p_res in ["三振", "犠打", "凡退", "走塁死", "盗塁死", "併殺打"]:
                        new_outs_count += 2 if p_res == "併殺打" else 1

                    new_records.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": st.session_state.get("current_inn_key"), "選手名": p_name, "位置": p_pos,
                        "結果": p_res, "打点": rbi_val, "得点": run_val, "盗塁": sb_val, "種別": type_val
                    })

            # 重複チェック
            if set(current_starters) & set(current_bench):
                st.error("⚠️ スタメンとベンチに重複選手がいます")
                return

            # ベンチ登録
            for bp in current_bench:
                new_records.append({
                    "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                    "イニング": "ベンチ", "選手名": bp, "位置": "控", "結果": "ー", "打点":0, "得点":0, "盗塁":0, "種別": "ベンチ"
                })
            
            # メタデータ
            new_records.append({
                 "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                 "イニング": "試合情報", "選手名": "チーム記録", "位置": kagura_order, "結果": "ー", "打点":0, "得点":0, "盗塁":0, "種別": "メタデータ"
            })

            if new_records:
                try:
                    conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(new_records)], ignore_index=True))
                    st.cache_data.clear()
                    
                    # 入力欄リセット
                    if "saved_lineup" not in st.session_state: st.session_state["saved_lineup"] = {}
                    for i in range(15):
                        st.session_state[f"sr{i}"] = "---"
                        st.session_state["saved_lineup"][f"res_{i}"] = "---"
                        st.session_state[f"si{i}"] = 0
                        st.session_state["saved_lineup"][f"rbi_{i}"] = 0
                    
                    # イニング自動更新ロジック
                    current_inn_str = st.session_state.get("current_inn_key", "1回")
                    pre_outs = 0
                    if not today_batting_df.empty:
                        inn_df = today_batting_df[(today_batting_df["イニング"] == current_inn_str) & (today_batting_df["イニング"] != "まとめ入力")]
                        o1 = len(inn_df[inn_df["結果"].isin(["三振", "犠打", "凡退", "走塁死", "盗塁死"])])
                        o2 = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                        pre_outs = (o1 + o2) % 3 
                    
                    msg = f"✅ {len(new_records)} 件登録"
                    if pre_outs + new_outs_count >= 3:
                        msg += " ➝ 3アウトチェンジ"
                        try:
                            curr_num = int(current_inn_str.replace("回", ""))
                            next_inn = f"{curr_num + 1}回" if curr_num < 9 else "延長"
                            st.session_state["current_inn_key"] = next_inn
                        except: pass
                    
                    st.success(msg)
                    if has_homerun: st.session_state["show_homerun_flg"] = True
                    else: 
                        import time
                        time.sleep(0.5)
                except Exception as e:
                    st.error(f"保存エラー: {e}")
            else:
                st.warning("登録データがありません")

        # UI構築
        st.button("登録実行", type="primary", on_click=submit_batting, use_container_width=True)
        
        # ホームラン演出
        if st.session_state.get("show_homerun_flg"):
            show_homerun_effect()
            import time
            time.sleep(3.5)
            st.session_state["show_homerun_flg"] = False
            st.rerun()

        with st.form(key='batting_form', clear_on_submit=False):
            # --- イニング・アウトカウント ---
            c_inn, c_outs, _ = st.columns([1.5, 2.5, 3.5])
            with c_inn:
                selected_inn = st.selectbox("イニング", [f"{i}回" for i in range(1, 10)] + ["延長"], key="current_inn_key")
            with c_outs:
                # フォーム内なので「直前の確定データ」に基づいて計算
                current_outs_db = 0
                if not today_batting_df.empty:
                    inn_df = today_batting_df[(today_batting_df["イニング"] == selected_inn) & (today_batting_df["イニング"] != "まとめ入力")]
                    outs_1 = len(inn_df[inn_df["結果"].isin(["三振", "犠打", "凡退", "走塁死", "盗塁死"])])
                    outs_2 = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                    current_outs_db = (outs_1 + outs_2) % 3
                st.markdown(render_out_indicator_3(current_outs_db), unsafe_allow_html=True)

            # --- スタメン入力テーブル ---
            batting_results = ["---", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "盗塁", "得点", "走塁死", "盗塁死"]
            player_list_with_empty = [""] + ALL_PLAYERS
            if "saved_lineup" not in st.session_state: st.session_state["saved_lineup"] = {}

            col_ratios = [0.5, 1.2, 2.0, 1.5, 1.2, 4.2]
            h_cols = st.columns(col_ratios)
            for col, label in zip(h_cols, ["打", "守備", "氏名", "結果", "打点", "成績"]): col.write(f"**{label}**")

            # ループ処理（on_changeを削除）
            for i in range(15):
                c = st.columns(col_ratios)
                c[0].write(f"{i+1}")
                
                # 初期値設定（session_state["saved_lineup"]から復元）
                s_pos = st.session_state["saved_lineup"].get(f"pos_{i}", "")
                def_pos_ix = ALL_POSITIONS.index(s_pos) if s_pos in ALL_POSITIONS else 0
                
                s_name = st.session_state["saved_lineup"].get(f"name_{i}", "")
                def_name_ix = player_list_with_empty.index(s_name) if s_name in player_list_with_empty else 0
                
                s_res = st.session_state.get(f"sr{i}", "---") # 結果は一時的なので直接keyから取得でOK
                def_res_ix = batting_results.index(s_res) if s_res in batting_results else 0
                
                s_rbi = st.session_state.get(f"si{i}", 0)

                # ★ウィジェット作成（on_changeは全て削除）
                c[1].selectbox(f"p{i}", ALL_POSITIONS, index=def_pos_ix, key=f"sp{i}", label_visibility="collapsed")
                c[2].selectbox(f"n{i}", player_list_with_empty, index=def_name_ix, key=f"sn{i}", label_visibility="collapsed", format_func=local_fmt)
                
                # 今季成績表示
                sel_p_name = st.session_state.get(f"sn{i}")
                if sel_p_name and sel_p_name in current_season_stats:
                    c[2].markdown(f"<div style='font-size:12px; color:#1e3a8a; margin-top:-5px;'>{current_season_stats[sel_p_name]}</div>", unsafe_allow_html=True)

                c[3].selectbox(f"r{i}", batting_results, index=def_res_ix, key=f"sr{i}", label_visibility="collapsed")
                c[4].selectbox(f"i{i}", [0, 1, 2, 3, 4], index=int(s_rbi), key=f"si{i}", label_visibility="collapsed")

                # 今日の打席履歴
                if not today_batting_df.empty and sel_p_name:
                    p_df = today_batting_df[(today_batting_df["選手名"] == sel_p_name) & (~today_batting_df["イニング"].isin(["まとめ入力", "ベンチ"]))]
                    if not p_df.empty:
                        history_items = []
                        pa_count = 0
                        pa_list = ["単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "凡退", "失策", "併殺打", "野選", "振り逃げ", "打撃妨害"]
                        for _, row in p_df.iterrows():
                            res_text = row['結果']
                            short_res = {"本塁打":"本", "三塁打":"3塁", "二塁打":"2塁", "単打":"安", "三振":"振", "四球":"四", "死球":"死"}.get(res_text, res_text)
                            if row['結果'] in pa_list:
                                pa_count += 1
                                history_items.append(f"{pa_count}({short_res})")
                            else:
                                history_items.append(f"({short_res})")
                        c[5].markdown(f"<div style='font-size:11px; color:#333;'>{' '.join(history_items)}</div>", unsafe_allow_html=True)
                    else: c[5].write("")
                else: c[5].write("")

            st.divider()
            
            # --- ベンチ登録 ---
            with st.expander(" 🚌  ベンチ入りメンバー", expanded=True):
                # ここも on_change は削除
                st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)
            
            # --- 送信ボタンエリア（2つのボタンを並べる） ---
            c_btn1, c_btn2 = st.columns([2, 1])
            # 1. プレイ記録ボタン
            submit_play_btn = c_btn1.form_submit_button("登録実行", type="primary", use_container_width=True)
            # 2. 試合開始スタメン登録ボタン
            start_game_btn = c_btn2.form_submit_button("スタメン登録 (試合開始)", use_container_width=True)

        # ---------------------------------------------------------
        # 処理ロジック（フォームの外で判定）
        # ---------------------------------------------------------
        
        # 共通：入力データの保存処理（on_changeの代わり）
        if submit_play_btn or start_game_btn:
            # セッションステートへの手動保存
            st.session_state["persistent_bench"] = st.session_state["bench_selection_widget"]
            for i in range(15):
                st.session_state["saved_lineup"][f"pos_{i}"] = st.session_state[f"sp{i}"]
                st.session_state["saved_lineup"][f"name_{i}"] = st.session_state[f"sn{i}"]
                # 結果(res)や打点(rbi)は一時的なので、あえてsaved_lineupには保存せず、キー(sr{i})に残る値を使います

        # A. プレイ記録ボタンが押された場合
        if submit_play_btn:
            submit_batting() # 定義済みの登録関数を実行

        # B. スタメン登録ボタンが押された場合
        if start_game_btn:
             starter_records = []
             for i in range(15):
                 p_name = st.session_state.get(f"sn{i}")
                 p_pos = st.session_state.get(f"sp{i}", "")
                 if p_name:
                     starter_records.append({
                         "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                         "イニング": "試合開始", "選手名": p_name, "位置": p_pos, "打順": i + 1,
                         "結果": "スタメン", "打点":0, "得点":0, "盗塁":0, "種別": "スタメン"
                     })
             if starter_records:
                 conn.update(spreadsheet=SPREADSHEET_URL, data=pd.concat([df_batting, pd.DataFrame(starter_records)], ignore_index=True))
                 st.cache_data.clear()
                 st.success("✅ スタメン登録完了")
                 import time
                 time.sleep(1.0)
                 st.rerun()