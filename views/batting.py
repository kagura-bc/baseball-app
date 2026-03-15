import streamlit as st
import pandas as pd
import datetime
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

# --- ヘルパー関数 ---
def local_fmt(name):
    """configのPLAYER_NUMBERSを使って名前を整形するローカル関数"""
    return fmt_player_name(name, PLAYER_NUMBERS)

# ==========================================
# メイン表示関数
# ==========================================
def show_batting_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order, is_test_mode=False):
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 🧪 テストモード判定で書き込むシートを切り替え
    ws_batting = "打撃成績_テスト" if is_test_mode else "打撃成績"
    ws_pitching = "投手成績_テスト" if is_test_mode else "投手成績"

    # ==========================================
    # 1. 日付変更時のリセット処理 & 初期化
    # ==========================================
    
    # 初回アクセス時またはリロード時のための初期値設定
    if "last_selected_date" not in st.session_state:
        st.session_state["last_selected_date"] = selected_date_str
    
    # 日付が変更されたかどうかを判定
    date_changed = (st.session_state["last_selected_date"] != selected_date_str)
    
    if date_changed:
        # 1. まず現在のセッション状態を完全にクリア
        all_keys = list(st.session_state.keys())
        target_prefixes = ["sn", "sp", "sr", "si"]
        for key in all_keys:
            if any(key.startswith(prefix) for prefix in target_prefixes):
                del st.session_state[key]
        
        # 2. 選択された日付のデータをチェック
        temp_today_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
        
        # 3. データが「存在しない」場合のみ、明示的に空をセットして残像を防ぐ
        if temp_today_df.empty:
            for i in range(15):
                st.session_state[f"sn{i}"] = ""
                st.session_state[f"sp{i}"] = "他"
            st.session_state["saved_lineup"] = {}
            st.session_state["persistent_bench"] = []
            st.session_state["persistent_inn"] = "1回" 
            st.session_state["persistent_scorer"] = "" # ★ 追加
        
        # 4. 管理フラグを更新してリラン
        st.session_state["last_selected_date"] = selected_date_str
        st.rerun()

    # セッションステート変数の初期化（未定義の場合）
    if "saved_lineup" not in st.session_state:
        st.session_state["saved_lineup"] = {}
    if "persistent_bench" not in st.session_state:
        st.session_state["persistent_bench"] = []
    if "persistent_inn" not in st.session_state: 
        st.session_state["persistent_inn"] = "1回"   
    if "persistent_scorer" not in st.session_state: # ★ 追加
        st.session_state["persistent_scorer"] = ""  # ★ 追加

    # ==========================================
    # 2. データのフィルタリング & 読み込み
    # ==========================================
    
    is_kagura_top = (kagura_order == "先攻 (表)")
    
    # 選択された日付のデータを取得
    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str]

    # ★★★ 自動読み込み処理 ★★★
    # 「入力欄が空(sn0なし)」かつ「その日のデータが存在する」場合にデータを復元
    # ※日付変更直後は上でクリアされているため、データがあればここが実行されます
    if "sn0" not in st.session_state and not today_batting_df.empty:
        try:
            for i in range(15):
                target_order = i + 1
                rows = today_batting_df[pd.to_numeric(today_batting_df["打順"], errors='coerce') == target_order]
                
                if not rows.empty:
                        # その打順の最後（最新）のデータを取得
                        last_row = rows.iloc[-1]
                        saved_name = last_row["選手名"]
                        saved_pos = last_row.get("位置", "")
                        
                        # ▼▼▼ ここから修正 ▼▼▼
                        # 入力欄（session_state）にまだ値が存在しない場合のみセットする
                        # （ユーザーが手動で選手を変更した直後の強制上書きを防ぐため）
                        if f"sn{i}" not in st.session_state:
                            st.session_state[f"sn{i}"] = saved_name
                            st.session_state[f"sp{i}"] = saved_pos
                        
                        # 保存用の箱(saved_lineup)にも、まだ記録がなければ同期しておく
                        if "saved_lineup" not in st.session_state:
                            st.session_state["saved_lineup"] = {}
                            
                        if f"name_{i}" not in st.session_state["saved_lineup"]:
                            st.session_state["saved_lineup"][f"name_{i}"] = saved_name
                            st.session_state["saved_lineup"][f"pos_{i}"] = saved_pos
                    
                    # 投手の連携用データもセット
                if saved_pos == "投" and saved_name:
                        st.session_state["shared_starting_pitcher"] = saved_name.split(" (")[0]
                         
        except Exception as e:
            print(f"Data Loading Error: {e}")

    # ==========================================
    # 3. 画面表示 (モード選択など)
    # ==========================================

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
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=pd.concat([df_batting, pd.DataFrame(new_batting_records)], ignore_index=True))
                    if new_pitching_records:
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=pd.concat([df_pitching, pd.DataFrame(new_pitching_records)], ignore_index=True))
                                        
                    st.cache_data.clear()
                    st.success("✅ スコアボードに反映しました")
                    import time
                    time.sleep(1.0)
                    st.rerun()
                except Exception as e:
                    st.error(f"保存エラー: {e}")

    # ---------------------------------------------------------
    # B. まとめ入力モード (詳細不明・過去データ用)
    # ---------------------------------------------------------
    elif input_mode == "選手別まとめ入力 (詳細不明・過去データ用)":
        st.info("複数の選手を表形式で一括登録します。数値はプルダウンから選択してください。")
        
        input_cols = ["打順", "選手名", "守備", "打席数", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策出塁", "打点", "得点", "盗塁"]
        number_options = list(range(21)) # 0〜20の選択肢
        small_options = list(range(5))   # 0〜4の選択肢

        if "bulk_df_state" not in st.session_state:
            initial_data = [[i, "", "他"] + [0]*13 for i in range(1, 16)]
            st.session_state["bulk_df_state"] = pd.DataFrame(initial_data, columns=input_cols)
        
        with st.form("bulk_batting_form"):
            submitted_bulk = st.form_submit_button("🏆 全データを一括登録", type="primary", use_container_width=True)
            
            edited_df = st.data_editor(
                st.session_state["bulk_df_state"], 
                num_rows="dynamic", 
                use_container_width=True,
                column_config={
                    "選手名": st.column_config.SelectboxColumn("選手名", options=[""] + [local_fmt(p) for p in ALL_PLAYERS], width="medium"),
                    "守備": st.column_config.SelectboxColumn("守備", options=["投", "捕", "一", "二", "三", "遊", "左", "中", "右", "指", "控", "他"]),
                    # 数値項目をプルダウン方式に設定
                    "打席数": st.column_config.SelectboxColumn("打席", options=number_options),
                    "単打": st.column_config.SelectboxColumn("単", options=small_options),
                    "二塁打": st.column_config.SelectboxColumn("二", options=small_options),
                    "三塁打": st.column_config.SelectboxColumn("三", options=small_options),
                    "本塁打": st.column_config.SelectboxColumn("本", options=small_options),
                    "三振": st.column_config.SelectboxColumn("振", options=small_options),
                    "四球": st.column_config.SelectboxColumn("四", options=small_options),
                    "死球": st.column_config.SelectboxColumn("死", options=small_options),
                    "犠打": st.column_config.SelectboxColumn("犠", options=small_options),
                    "失策出塁": st.column_config.SelectboxColumn("失", options=small_options),
                    "打点": st.column_config.SelectboxColumn("点", options=number_options),
                    "得点": st.column_config.SelectboxColumn("得", options=small_options),
                    "盗塁": st.column_config.SelectboxColumn("盗", options=small_options),
                }
            )
            bench_selection = st.multiselect("ベンチ入りメンバー", ALL_PLAYERS, format_func=local_fmt)

            # --- まとめ入力の登録ロジック ---
            if submitted_bulk:
                recs = []
                # ベンチメンバーの登録
                for b_raw in bench_selection:
                    b_name = b_raw.split(" (")[0]
                    recs.append({
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": "ベンチ", "選手名": b_name, "位置": "控", "結果": "ベンチ", "種別": "ベンチ"
                    })
                
                # エディタの内容を1行ずつ処理
                for _, row in edited_df.iterrows():
                    raw_name = row["選手名"]
                    if not raw_name: continue
                    p_name = raw_name.split(" (")[0]
                    
                    base_rec = {
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": "まとめ入力", "選手名": p_name, "位置": row["守備"], "打順": row["打順"],
                        "結果": "まとめ", "打点": row["打点"], "得点": row["得点"], "盗塁": row["盗塁"], "種別": "まとめ"
                    }
                    # その他の内訳カラムも追加
                    for col in ["打席数", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策出塁"]:
                        base_rec[col] = row[col]
                    recs.append(base_rec)

                if recs:
                    try:
                        updated_df = pd.concat([df_batting, pd.DataFrame(recs)], ignore_index=True)
                        conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=updated_df)
                        st.cache_data.clear()
                        st.success(f"✅ {len(recs)}件のまとめデータを保存しました")
                        import time
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存エラー: {e}")

    # ---------------------------------------------------------
    # C. 詳細入力モード (通算成績青文字表示 & 自動更新版)
    # ---------------------------------------------------------
    else:
        def submit_everything():
            if "sn0" not in st.session_state: return 

            require_direction_results = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "犠打"]
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
            current_inn = st.session_state.get("current_inn_key", "1回")
            current_scorer = st.session_state.get("scorer_name", "") # スコアラー名を取得
            # ★ 追加：スコアラー名と選手名の画面状態を永続保存（ページ遷移対策）
            st.session_state["persistent_scorer"] = current_scorer
            st.session_state["persistent_inn"] = current_inn # ★ 追加：イニングも永続保存
            
            # ★ 追加：スコアラー名と選手名の画面状態を永続保存（ページ遷移対策）
            st.session_state["persistent_scorer"] = current_scorer
            if "saved_lineup" not in st.session_state:
                st.session_state["saved_lineup"] = {}

            for i in range(15):
                p_name = st.session_state.get(f"sn{i}", "")
                p_pos = st.session_state.get(f"sp{i}", "")
                
                # ★ 追加：スタメン（選手名・守備）を保持用の辞書にコピー
                st.session_state["saved_lineup"][f"name_{i}"] = p_name
                st.session_state["saved_lineup"][f"pos_{i}"] = p_pos
                
                # ★ 追加：守備位置が「投」の選手を投手ページ用に保存
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

                # 結果が「---」以外、または得点が1以上の時のみDB保存対象にする
                if p_name and (p_res != "---" or run_val > 0):
                    record_dict = {
                        "日付": selected_date_str, "グラウンド": ground_name, "対戦相手": opp_team, "試合種別": match_type,
                        "イニング": current_inn, "選手名": p_name, "位置": p_pos, "打順": i+1,
                        "結果": p_res if p_res != "---" else "得点",
                        "打点": rbi_val, "得点": run_val, "盗塁": (1 if p_res == "盗塁" else 0), 
                        "種別": "打席", "打球方向": p_dir if p_dir != "---" else "",
                        "スコアラー": current_scorer # 辞書にスコアラー情報を追加
                    }
                    new_records.append(record_dict)

            # 打席の入力があった場合はデータベースへ保存
            if new_records:
                try:
                    new_df = pd.DataFrame(new_records)
                    updated_df = pd.concat([df_batting, new_df], ignore_index=True)
                    conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=updated_df)
                    st.cache_data.clear()
                    
                    # イニング自動更新ロジック
                    out_res_list = ["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打", "走塁死", "盗塁死"]
                    inn_combined = pd.concat([today_batting_df[today_batting_df["イニング"] == current_inn], new_df])
                    total_outs = len(inn_combined[inn_combined["結果"].isin(out_res_list)])
                    total_outs += len(inn_combined[inn_combined["結果"] == "併殺打"]) * 2

                    if total_outs >= 3:
                        inn_list = [f"{i}回" for i in range(1, 10)] + ["延長"]
                        try:
                            curr_idx = inn_list.index(current_inn)
                            if curr_idx < len(inn_list) - 1:
                                next_inn = inn_list[curr_idx + 1] # 変数に一度入れる
                                st.session_state["current_inn_key"] = next_inn
                                st.session_state["persistent_inn"] = next_inn # ★ 追加
                                st.toast(f"3アウト交代！次イニングへ。")
                        except: pass

                    # 打席結果部分だけリセット
                    for i in range(15):
                        for k in [f"sr{i}", f"sd{i}", f"si{i}", f"st{i}"]: st.session_state[k] = "---"
                    
                    if has_homerun: st.session_state["show_homerun_flg"] = True
                    st.success(f"✅ 打席結果を保存しました")
                    import time
                    time.sleep(1)
                    st.rerun() 
                except Exception as e:
                    st.error(f"保存エラー: {e}")
            else:
                # 選手やスコアラーのセットのみで打席結果が入力されていない場合
                st.success("✅ スタメンとスコアラーの表示を保持しました（※打席結果は未入力です）")
                import time
                time.sleep(1)
                st.rerun()

        # --- 今シーズンのデータ抽出 ---
        this_year = datetime.datetime.now().year
        if not df_batting.empty:
            df_batting["日付_dt"] = pd.to_datetime(df_batting["日付"], errors='coerce')
            df_this_season = df_batting[df_batting["日付_dt"].dt.year == this_year].copy()
        else:
            df_this_season = pd.DataFrame()

        hit_results = ["単打", "二塁打", "三塁打", "本塁打"]
        ab_results = hit_results + ["凡退(ゴロ)", "凡退(フライ)", "失策", "走塁死", "盗塁死", "三振", "併殺打", "野選", "振り逃げ三振"]

        # --- UI構築 ---
        with st.form(key='batting_form', clear_on_submit=False):
            if st.form_submit_button("登録実行 (スコアボード反映)", type="primary", use_container_width=True):
                submit_everything()

            c_inn, c_outs, c_scorer = st.columns([1.5, 2.5, 3.5]) # '_' を 'c_scorer' に変更
            with c_inn:
                # ★ 変更：保管庫からイニングを読み込んで初期値にセットする
                inn_list = [f"{i}回" for i in range(1, 10)] + ["延長"]
                saved_inn = st.session_state.get("persistent_inn", "1回")
                def_inn_ix = inn_list.index(saved_inn) if saved_inn in inn_list else 0
                curr_inn = st.selectbox("イニング", inn_list, index=def_inn_ix, key="current_inn_key")
            with c_outs:
                disp_outs = 0
                if not today_batting_df.empty:
                    inn_df = today_batting_df[today_batting_df["イニング"] == curr_inn]
                    s_outs = len(inn_df[inn_df["結果"].isin(["凡退(ゴロ)", "凡退(フライ)", "三振", "犠打", "走塁死", "盗塁死"])])
                    d_outs = len(inn_df[inn_df["結果"] == "併殺打"]) * 2
                    disp_outs = (s_outs + d_outs) % 3
                st.markdown(render_out_indicator_3(disp_outs), unsafe_allow_html=True)
            with c_scorer: # スコアラー入力欄を追加
                p_list = [""] + ALL_PLAYERS
                saved_scorer = st.session_state.get("persistent_scorer", "")
                def_scorer_ix = p_list.index(saved_scorer) if saved_scorer in p_list else 0
                
                # 💡完全修正版：on_changeを辞め、選ばれた値を直接保管庫に入れる
                selected_scorer = st.selectbox("スコアラー", p_list, index=def_scorer_ix, key="scorer_name", format_func=local_fmt)
                st.session_state["persistent_scorer"] = selected_scorer

            batting_results = ["---", "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策", "盗塁", "得点", "走塁死", "盗塁死", "振り逃げ三振", "打撃妨害"]
            
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
                    # 選手名部分のみ抽出 (「(10)」などの背番号を除去)
                    clean_name = sel_p_name.split(" (")[0]
                    p_stats_df = df_this_season[df_this_season["選手名"] == clean_name]
                    
                    if not p_stats_df.empty:
                        # 打数・安打・打点・本塁打の計算
                        ab_count = len(p_stats_df[p_stats_df["結果"].isin(ab_results)])
                        hit_count = len(p_stats_df[p_stats_df["結果"].isin(hit_results)])
                        rbi_sum = pd.to_numeric(p_stats_df["打点"], errors='coerce').sum()
                        hr_count = len(p_stats_df[p_stats_df["結果"] == "本塁打"])
                        
                        avg = hit_count / ab_count if ab_count > 0 else 0.0
                        avg_str = f"{avg:.3f}".replace("0.", ".") # 0.333 -> .333
                        
                        # 青色で表示
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
                        pa_list_for_history = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打", "失策", "併殺打", "振り逃げ三振", "打撃妨害"]
                        count = 0
                        total_runs = 0
                        for _, row in p_df.iterrows():
                            res = row['結果']
                            raw_dir = row['打球方向']
                            p_dir = str(raw_dir) if pd.notna(raw_dir) and raw_dir != "---" else ""
                            rbi = int(pd.to_numeric(row['打点'], errors='coerce') or 0)
                            total_runs += int(pd.to_numeric(row['得点'], errors='coerce') or 0)
                            
                            res_short = {
                                "本塁打":"本", "三塁打":"三", "二塁打":"二", "単打":"安", 
                                "三振":"振", "凡退(ゴロ)":"ゴ", "凡退(フライ)":"飛", "四球":"球", "死球":"死", "犠打":"犠", "振り逃げ三振":"逃", "打撃妨害":"妨"
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

            st.divider()
            with st.expander(" 🚌 ベンチ入りメンバー", expanded=True):
                # 💡完全修正版：選ばれた値を直接保管庫に入れる
                selected_bench = st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)
                st.session_state["persistent_bench"] = selected_bench