import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from config.settings import ALL_PLAYERS, SPREADSHEET_URL, PLAYER_NUMBERS, MY_TEAM
from utils.ui import render_scoreboard, render_out_indicator_3, fmt_player_name

def local_fmt(name):
    return fmt_player_name(name, PLAYER_NUMBERS)

def show_pitching_page(df_batting, df_pitching, selected_date_str, match_type, ground_name, opp_team, kagura_order, is_test_mode=False):
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # 🧪 テストモード判定で書き込むシートを切り替え
    ws_pitching = "投手成績_テスト" if is_test_mode else "投手成績"
    is_kagura_top = (kagura_order == "先攻 (表)")

    # フィルタリング
    today_batting_df = df_batting[df_batting["日付"].astype(str) == selected_date_str]
    today_pitching_df = df_pitching[df_pitching["日付"].astype(str) == selected_date_str]

    # モード選択
    st.markdown("### 📝 入力モード")
    input_mode_p = st.radio("モードを選択してください", ["詳細入力 (1打席ごと)", "選手別まとめ入力 (詳細不明・過去データ用)"], horizontal=True, key="pitching_mode_radio")
    
    scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"] if not today_batting_df.empty else today_batting_df
    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)

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

        # --- 成績計算ロジック ---
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
        
        # --- フォームのリセット処理 ---
        if st.session_state.get("needs_form_clear"):
            st.session_state["p_det_res"] = "凡退(ゴロ)" # デフォルト値を文字列に修正(タプルだとエラーになる場合があるため)
            st.session_state["p_det_pos_list"] = []
            st.session_state["p_det_run"] = 0
            st.session_state["p_det_er"] = 0
            st.session_state["needs_form_clear"] = False 

        # --- 【追加】イニング自動進行ロジック（フォーム描画前に計算） ---
        inn_options = [f"{i}回" for i in range(1, 10)] + ["延長"]
        
        # セッションステートから現在のイニングを取得（未設定なら1回）
        current_inn_val = st.session_state.get("p_det_inn", "1回")
        
        # 1. 現在のイニングのアウト数を計算（前方一致判定）
        current_outs_total = 0
        if not today_pitching_df.empty:
            # 現在のイニングのデータのみ抽出
            p_inn_df_check = today_pitching_df[today_pitching_df["イニング"] == current_inn_val]
            
            # 1アウト系（三振、凡退など）
            out_keywords = ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打", "犠飛", "牽制死", "盗塁死", "走塁死"]
            # str(x)で文字列化してからstartswithで判定
            single_outs = len(p_inn_df_check[p_inn_df_check["結果"].apply(lambda x: any(str(x).startswith(k) for k in out_keywords))])
            
            # 2アウト系（併殺打）
            double_outs = len(p_inn_df_check[p_inn_df_check["結果"].apply(lambda x: str(x).startswith("併殺打"))]) * 2
            
            current_outs_total = single_outs + double_outs

        # 2. もし3アウト以上なら、次のイニングへ進める
        if current_outs_total >= 3:
            try:
                curr_idx = inn_options.index(current_inn_val)
                if curr_idx < len(inn_options) - 1:
                    # 次のイニングを取得
                    next_inn = inn_options[curr_idx + 1]
                    # セッションステートを更新
                    st.session_state["p_det_inn"] = next_inn
                    current_inn_val = next_inn # 表示用変数も更新
                    
                    # イニングが変わったので、この時点での表示用アウト数は0に戻す
                    current_outs_total = 0 
            except ValueError:
                pass # リストにないイニング名の場合は何もしない

        # --- フォーム描画開始 ---
        with st.form(key='score_input_form', clear_on_submit=False):
            # --- 上段：イニングとアウトカウント表示 ---
            c_top1, c_top2 = st.columns([1, 1])
            with c_top1:
                # 更新された current_inn_val を初期値として設定
                default_idx = inn_options.index(current_inn_val) if current_inn_val in inn_options else 0
                current_inn = st.selectbox("イニング", inn_options, index=default_idx)
                # 万が一手動で戻した場合のためにセッションステートと同期
                st.session_state["p_det_inn"] = current_inn
            
            with c_top2:
                # current_outs_total は上で計算済み（イニング進行時は0、継続時はその数）
                # 手動でイニングを変更した場合に対応するため、ここでも再計算するのがベストだが
                # 基本的には上のロジックで整合性が取れる。念のため表示用に再取得ロジックを入れる。
                
                disp_outs = 0
                if not today_pitching_df.empty:
                    # selectboxで選ばれているイニング（current_inn）に基づいて計算
                    p_inn_df_disp = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                    
                    out_keywords = ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打", "犠飛", "牽制死", "盗塁死", "走塁死"]
                    s_outs = len(p_inn_df_disp[p_inn_df_disp["結果"].apply(lambda x: any(str(x).startswith(k) for k in out_keywords))])
                    d_outs = len(p_inn_df_disp[p_inn_df_disp["結果"].apply(lambda x: str(x).startswith("併殺打"))]) * 2
                    
                    disp_outs = (s_outs + d_outs) % 3
                
                st.markdown(render_out_indicator_3(disp_outs), unsafe_allow_html=True)

            # --- 中段：打順と投手選択 ---
            c_mid1, c_mid2, c_mid3 = st.columns([1.2, 1.2, 2.5])
            with c_mid1: 
                st.session_state["opp_batter_count"] = st.number_input("相手打順人数", 1, 20, value=st.session_state["opp_batter_count"])
            with c_mid2: 
                st.session_state["opp_batter_index"] = st.number_input("現在の打順", 1, st.session_state["opp_batter_count"], value=st.session_state["opp_batter_index"])
            
            with c_mid3:
                    pitcher_list_opts = [""] + [local_fmt(p) for p in ALL_PLAYERS]
                    default_pitcher_idx = 0
                    
                    # ★修正: 打撃入力画面でリアルタイム保存されているオーダー(saved_lineup)から「投」を探す
                    saved_pitcher = None
                    lineup = st.session_state.get("saved_lineup", {})
                    
                    for i in range(20):
                        if lineup.get(f"pos_{i}") == "投":
                            raw_name = lineup.get(f"name_{i}", "")
                            if raw_name:
                                # 括弧などの付加情報を除去して名前のみ取得
                                saved_pitcher = raw_name.split(" (")[0]
                            break
                    
                    # 見つからなかった場合の保険
                    if not saved_pitcher:
                        saved_pitcher = st.session_state.get("shared_starting_pitcher")
                    
                    if saved_pitcher:
                        for i, p_opt in enumerate(pitcher_list_opts):
                            if saved_pitcher in p_opt:
                                default_pitcher_idx = i
                                break
                                
                    target_pitcher_disp = st.selectbox("登板投手", pitcher_list_opts, index=default_pitcher_idx)
                
                # 投手成績のクイック表示
                if "current_season_pitching" in locals() and target_pitcher_disp in current_season_pitching:
                    st.markdown(f"<div style='font-size:14px; color:#1e3a8a;'>{current_season_pitching[target_pitcher_disp]}</div>", unsafe_allow_html=True)

            # --- 下段：具体的な成績入力 ---
            st.divider()

            # カラム定義
            c_res, c_pos, c_run, c_er = st.columns(4)
            
            with c_res:
                p_res = st.selectbox("結果", ["凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打", "四球", "死球", "犠打", "犠飛", "併殺打", 
                                            "失策", "振り逃げ三振", "野選", "打撃妨害", "ボーク", "暴投", "捕逸", "牽制死", "盗塁死", "走塁死"], key="p_det_res")
            
            with c_pos:
                target_fielder_pos_list = st.multiselect(
                    "打球方向/関与野手", 
                    ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"],
                    max_selections=2,
                    key="p_det_pos_list",
                    placeholder="選択(複数可)",
                    help="通常は1つ。併殺打などは関与順に2つ選択（例: 遊→一）"
                )
                
            with c_run:
                p_run = st.number_input("失点", 0, 4, 0, key="p_det_run")
            with c_er:
                p_er = st.number_input(
                    "自責", 0, 4, 0, key="p_det_er",
                    help="""【自責点(ER)の判定ガイド】
ミスがないと仮定して、投手の責任で取られた点数か判断します。

✅ 自責点になる (YES)
・安打、四死球での出塁
・盗塁、暴投（WP）での進塁
・ミスがなければ生還していた場合

❌ 自責にならない (NO)
・エラー（失策）、パスボール（PB）
・打撃妨害での出塁
・「エラーがなければ3アウトでチェンジだった」後の失点"""
                )
            
            submit_detail = st.form_submit_button("登録実行", type="primary", use_container_width=True)

        # 4. 登録実行処理
        if submit_detail:
            input_name = target_pitcher_disp if target_pitcher_disp else (saved_pitcher if 'saved_pitcher' in locals() and saved_pitcher else "")
            
            if not input_name: 
                st.error("⚠️ 投手を選択してください")
            elif p_res == "本塁打" and p_run == 0: 
                st.error("⚠️ 本塁打は失点1以上必須")
            elif p_res in ["凡退(ゴロ)", "凡退(フライ)", "失策", "併殺打", "犠打", "野選"] and not target_fielder_pos_list: 
                st.error("⚠️ 打球方向を選択してください")
            else:
                # 投手名の整形（例: "和田 (21)" -> "和田"）
                target_pitcher_name = str(input_name).split(" (")[0].strip()
                
                # --- 【修正の核心】表示用とデータ保存用の切り分け ---
                
                # 1. 位置情報の作成（例: "遊-二"）
                target_fielder_pos_str = "-".join(target_fielder_pos_list)

                # 2. 処理野手名の作成（個人成績集計用：名前を取得）
                fielder_display = ""
                if target_fielder_pos_list:
                    lineup = st.session_state.get("saved_lineup", {})
                    name_parts = []
                    
                    for pos in target_fielder_pos_list:
                        found_name = ""
                        # オーダー情報からそのポジションを守っている選手名を探す
                        for i in range(20):
                            if lineup.get(f"pos_{i}") == pos:
                                # 名前から "(右)" などの付加情報を除いて純粋な名前のみ取得
                                found_name = lineup.get(f"name_{i}", "").split(" (")[0].strip()
                                break
                        
                        if found_name:
                            name_parts.append(found_name) # 例: "久保田剛志"
                        else:
                            name_parts.append(f"({pos})") # 見つからない場合は位置を表示
                    
                    fielder_display = "-".join(name_parts)

                # 3. 画面表示用の結果テキスト作成（例: "凡退(捕)"）
                # 履歴テーブルで見たい形式をここで作ります
                if target_fielder_pos_str:
                    display_result = f"{p_res}({target_fielder_pos_str})"
                else:
                    display_result = p_res
                
                # --- アウト数・被安打の計算 ---
                add_outs = 0
                if p_res == "併殺打":
                    add_outs = 2
                elif p_res in ["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打", "犠飛", "牽制死", "盗塁死", "走塁死"]:
                    add_outs = 1
                
                add_hits = 1 if p_res in ["単打", "二塁打", "三塁打", "本塁打"] else 0
                add_strikeouts = 1 if p_res in ["三振", "振り逃げ三振"] else 0 # ★三振と振り逃げ三振をカウント
                batter_idx_str = f"{st.session_state['opp_batter_index']}"

                # --- データの作成 ---
                rec = {
                    "日付": selected_date_str, 
                    "グラウンド": ground_name, 
                    "対戦相手": opp_team, 
                    "試合種別": match_type,
                    "イニング": current_inn, 
                    
                    "選手名": target_pitcher_name,   # 投手成績用
                    "守備位置": target_fielder_pos_str,  # ポジション（捕）
                    "打球方向": target_fielder_pos_str,  # 💡追加：データ分析用に打球方向列に保存
                    "処理野手": fielder_display,     # 個人成績用（久保田剛志）
                    
                    "結果": p_res,                   # 💡修正：計算エラーを防ぐため純粋な「単打」などを保存
                    "失点": p_run, 
                    "自責点": p_er,
                    "勝敗": "ー", 
                    "被安打": add_hits, 
                    "奪三振": add_strikeouts,        # ★辞書データに奪三振の数を追加
                    "アウト数": add_outs, 
                    "種別": f"詳細:{batter_idx_str}番打者"
                }
                
                # スプレッドシートへ保存
                conn.update(
                    spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=pd.concat([df_pitching, pd.DataFrame([rec])], 
                    ignore_index=True)
                )
                st.cache_data.clear()

                # --- 保存完了フラグを立てる ---
                st.session_state["needs_form_clear"] = True
                
                # --- 3アウトチェンジ判定 ---
                p_inn_df = today_pitching_df[today_pitching_df["イニング"] == current_inn]
                existing_single_outs = len(p_inn_df[p_inn_df["結果"].isin(["三振", "凡退(ゴロ)", "凡退(フライ)", "犠打", "犠飛"])])
                existing_double_outs = len(p_inn_df[p_inn_df["結果"] == "併殺打"]) * 2
                total_outs_after = existing_single_outs + existing_double_outs + add_outs
                
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
                
                st.success(f"✅ {target_pitcher_name}投手の記録を保存しました")
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
                            conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=df_pitching)
                            st.cache_data.clear()
                            st.success(f"✅ {target_player} 選手を「{dec_t}」で確定")
                        else: st.warning("本日の登板記録が見つかりません。")

        # 5. 履歴表示 
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
                            
                            # 画面表示用として結果と打球方向を合体させる
                            raw_res = str(row.get('結果', ''))
                            pos_str = str(row.get('打球方向', '')) or str(row.get('守備位置', ''))
                            
                            if pos_str and pos_str not in ["nan", "None", ""]:
                                raw_res = f"{raw_res}({pos_str})"
                                
                            fielder_str = str(row.get('処理野手', ''))
                            if fielder_str and fielder_str not in ["nan", "None", ""]:
                                res_text = f"{raw_res} [{fielder_str}]"
                            else:
                                res_text = raw_res
                                
                            # 🌟追加：失点がある場合はテキストに失点数を追加
                            runs = pd.to_numeric(row.get('失点', 0), errors='coerce')
                            runs = int(runs) if pd.notna(runs) else 0
                            if runs > 0:
                                res_text = f"{res_text} 💥失点{runs}"
                                
                            display_items.append({"打順": f"{b_idx}番", "投手": local_fmt(row["選手名"]), "結果": res_text})
                        
                        # 🌟修正：データフレームを作成し、失点を含むセルを赤字にする
                        df_disp = pd.DataFrame(display_items).T
                        
                        def highlight_timely(val):
                            if isinstance(val, str) and "💥失点" in val:
                                return "color: red; font-weight: bold;"
                            return ""
                        
                        # Pandasのバージョンによる記述の違いを吸収する安全な処理
                        try:
                            styled_df = df_disp.style.map(highlight_timely)
                        except AttributeError:
                            styled_df = df_disp.style.applymap(highlight_timely)
                            
                        st.dataframe(styled_df, use_container_width=True)
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
                    conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=pd.concat([df_pitching, pd.DataFrame(recs)], ignore_index=True))
                    st.cache_data.clear()
                    st.success("✅ 登録完了")
                    st.rerun()