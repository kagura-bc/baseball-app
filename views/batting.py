import streamlit as st
import pandas as pd
import datetime
from streamlit_gsheets import GSheetsConnection
from config.settings import ALL_POSITIONS, SPREADSHEET_URL
from utils.players import get_active_players
from utils.ui import render_scoreboard, render_out_indicator_3, show_homerun_effect, fmt_player_name

# --- ヘルパー関数 ---
def local_fmt(name):
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))

# ★ 打席としてカウントする（打順を進める）結果のリスト
PA_RESULTS = [
    "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", 
    "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", 
    "失策(ゴロ)", "失策(フライ)", "野選", "併殺打", "振り逃げ三振", "打撃妨害"
]

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

    # ▼▼▼ フォームクリアのフラグ処理（ウィジェット描画前にキーを完全に削除してゾンビを完全駆除） ▼▼▼
    if st.session_state.get("needs_batting_clear"):
        for i in range(20):
            for k in [f"sr{i}", f"si{i}", f"st{i}", f"row_sr{i}"]:
                st.session_state.pop(k, None)
            st.session_state.pop(f"sd{i}", None)
                
        st.session_state.pop("quick_sr", None)
        st.session_state.pop("quick_sd", None)
        st.session_state.pop("quick_si", None)
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
        target_prefixes = ["sn", "sp", "sr", "si", "st", "sd", "row_sr", "quick_", "persistent_", "batting_inning_select", "scorer_name_ui", "saved_lineup", "batter_offset", "lineup_states", "batting_error_msg"]
        for key in all_keys:
            if any(key.startswith(prefix) for prefix in target_prefixes):
                del st.session_state[key]
        
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"
        st.session_state["last_match_id"] = current_match_id

    if "persistent_inn" not in st.session_state:
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"

    if "batter_offset" not in st.session_state:
        st.session_state["batter_offset"] = 0
        
    # ▼▼▼ 打順の表示人数（デフォルト9）の初期化 ▼▼▼
    if "display_order_count" not in st.session_state:
        st.session_state["display_order_count"] = 9

    # ==========================================
    # 2. データの読み込み & 即時反映キャッシュの適用
    # ==========================================
    is_kagura_top = (kagura_order == "先攻 (表)")
    target_date_str = pd.to_datetime(selected_date_str, errors='coerce').strftime('%Y-%m-%d')

    cache_key = f"cache_batting_{selected_date_str}_{opp_team}_{match_type}"
    if cache_key in st.session_state:
        df_batting = st.session_state[cache_key]

    expected_batting_cols = ["日付", "イニング", "選手名", "位置", "結果", "打点", "得点", "グラウンド", "対戦相手", "試合種別", "打順", "打球方向", "スコアラー"]
    if df_batting.empty:
        df_batting = pd.DataFrame(columns=expected_batting_cols)
    else:
        for col in expected_batting_cols:
            if col not in df_batting.columns:
                df_batting[col] = ""

    if not df_pitching.empty:
        expected_pitching_cols = ["日付", "イニング", "選手名", "結果", "失点", "自責点", "被安打", "奪三振", "アウト数", "種別", "対戦相手", "試合種別"]
        for col in expected_pitching_cols:
            if col not in df_pitching.columns:
                df_pitching[col] = ""

    if "日付" in df_batting.columns:
        df_batting["_date_str"] = pd.to_datetime(df_batting["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        today_batting_df = df_batting[
            (df_batting["_date_str"] == target_date_str) & 
            (df_batting["対戦相手"].astype(str).str.strip() == str(opp_team).strip()) & 
            (df_batting["試合種別"].astype(str).str.strip() == str(match_type).strip())
        ]
    else:
        today_batting_df = pd.DataFrame(columns=expected_batting_cols)

    if not df_pitching.empty and "日付" in df_pitching.columns:
        df_pitching["_date_str"] = pd.to_datetime(df_pitching["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        today_pitching_df = df_pitching[
            (df_pitching["_date_str"] == target_date_str) & 
            (df_pitching["対戦相手"].astype(str).str.strip() == str(opp_team).strip()) & 
            (df_pitching["試合種別"].astype(str).str.strip() == str(match_type).strip())
        ]
    else:
        today_pitching_df = pd.DataFrame()

    # ラインナップの状態管理用セッション初期化 & 復元
    if "lineup_states" not in st.session_state:
        st.session_state["lineup_states"] = {}

    if not today_batting_df.empty:
        lineup_event_df = today_batting_df[today_batting_df["結果"].astype(str).isin(["スタメン", "守備変更", "交代", "試合前"])]
        for i in range(15):
            order_num = i + 1
            order_rows = lineup_event_df[pd.to_numeric(lineup_event_df["打順"], errors='coerce') == order_num]
            if not order_rows.empty:
                latest_row = order_rows.iloc[-1]
                latest_name = str(latest_row.get("選手名", "")).strip()
                latest_pos = str(latest_row.get("位置", "")).strip()
                if latest_name and latest_name not in ["nan", "チーム記録", ""]:
                    st.session_state["lineup_states"][i] = {
                        "name": latest_name,
                        "pos": latest_pos if latest_pos and latest_pos != "nan" else "－"
                    }

    if not match_changed and not today_batting_df.empty:
        valid_inn_df = today_batting_df[~today_batting_df["イニング"].astype(str).isin(["まとめ入力", "試合終了", "", "nan"])]
        if not valid_inn_df.empty:
            st.session_state["persistent_inn"] = valid_inn_df.iloc[-1]["イニング"]

        if "scorer_name_ui" not in st.session_state:
            valid_scorer_df = today_batting_df[
                (today_batting_df["スコアラー"].astype(str).str.strip() != "") & 
                (today_batting_df["スコアラー"].astype(str).str.strip() != "0") &
                (today_batting_df["スコアラー"].astype(str).str.strip() != "nan")
            ]
            if not valid_scorer_df.empty:
                st.session_state["scorer_name_ui"] = valid_scorer_df.iloc[-1]["スコアラー"]

        for idx in range(15):
            name_key = f"sn{idx}"
            pos_key = f"sp{idx}"
            
            if idx in st.session_state["lineup_states"]:
                latest_info = st.session_state["lineup_states"][idx]
                name_val = latest_info["name"]
                pos_val = latest_info["pos"]
                
                if name_key not in st.session_state and name_val and name_val not in ["nan", "チーム記録", ""]:
                    matched_name = next((p for p in player_options if p.split(" (")[0].strip() == name_val or p == name_val), None)
                    if matched_name:
                        st.session_state[name_key] = matched_name
                        
                if pos_key not in st.session_state and pos_val and pos_val in pos_options and pos_val not in ["nan", "－"]:
                    st.session_state[pos_key] = pos_val

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
    # 4. 高速化のための事前一括集計 (辞書化)
    # ==========================================
    player_history_dict = {}
    if not today_batting_df.empty:
        valid_history_df = today_batting_df[~today_batting_df["結果"].isin(["スタメン", "守備変更", "交代", "ベンチ"])]
        if not valid_history_df.empty:
            for clean_name, group in valid_history_df.groupby("選手名"):
                history_html = []
                count = 0
                stolen_base_count = 0
                total_runs = 0
                
                for _, row in group.iterrows():
                    res = row['結果']
                    runs_val = pd.to_numeric(row['得点'], errors='coerce')
                    rbi_val = pd.to_numeric(row['打点'], errors='coerce')
                    
                    r_val = int(runs_val) if pd.notna(runs_val) else 0
                    total_runs += r_val
                    
                    if res == "盗塁":
                        stolen_base_count += 1
                        continue
                    elif res in ["盗塁死", "走塁死", "牽制死", "走塁記録"]:
                        continue
                    
                    count += 1
                    res_short = {
                        "本塁打":"本", "三塁打":"三", "二塁打":"二", "単打":"安", 
                        "三振":"振", "凡退(ゴロ)":"ゴ", "凡退(フライ)":"飛", "四球":"球", "死球":"死", "犠打(ゴロ)":"犠", "犠打(フライ)":"犠", "犠飛":"犠飛", "失策(ゴロ)":"失", "失策(フライ)":"失", "野選":"野", "併殺打":"併", 
                        "振り逃げ三振":"逃", "打撃妨害":"妨"
                    }.get(res, res[:2])
                    
                    raw_dir = row['打球方向']
                    p_dir = str(raw_dir) if pd.notna(raw_dir) and raw_dir != "---" else ""
                    
                    rbi_num = int(rbi_val) if pd.notna(rbi_val) else 0
                    
                    if rbi_num > 0:
                        disp_text = f"{p_dir}{res_short}・{rbi_num}" if p_dir else f"{res_short}・{rbi_num}"
                    else:
                        disp_text = f"{p_dir}{res_short}" if p_dir else f"{res_short}"
                    
                    color_style = ""
                    is_hit = res in ["単打", "二塁打", "三塁打", "本塁打"]
                    
                    if is_hit and rbi_num > 0:
                        color_style = "color: red;"
                    elif is_hit:
                        color_style = "color: blue;"
                        
                    history_html.append(f"<span style='{color_style}'>{count}({disp_text})</span>")
                
                if stolen_base_count > 0:
                    history_html.append(f"<span style='color: #800080;'>盗{stolen_base_count}</span>")
                
                if total_runs > 0:
                    history_html.append(f"<span style='color: green;'>得{total_runs}</span>")
                
                player_history_dict[str(clean_name).strip()] = " ".join(history_html)

    # ==========================================
    # 5. 登録処理関数 (submit_everything) の定義
    # ==========================================
    def submit_everything(inn_val):
        rows_to_add = []
        current_date_formatted = pd.to_datetime(selected_date_str).strftime('%Y-%m-%d')
        scorer = st.session_state.get("scorer_name_ui", "")
        
        display_count = st.session_state.get("display_order_count", 9)
        
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}

        has_today_lineup = False
        if not today_batting_df.empty:
            has_today_lineup = not today_batting_df[today_batting_df["結果"].astype(str) == "スタメン"].empty

        if not has_today_lineup:
            for i in range(display_count):
                name_val = st.session_state.get(f"sn{i}")
                pos_val = st.session_state.get(f"sp{i}")
                if name_val:
                    clean_name = name_val.split(" (")[0].strip()
                    current_pos = pos_val if pos_val else "－"
                    
                    st.session_state["saved_lineup"][f"name_{i}"] = clean_name
                    st.session_state["saved_lineup"][f"pos_{i}"] = current_pos

                    rows_to_add.append({
                        "日付": current_date_formatted,
                        "対戦相手": opp_team,
                        "試合種別": match_type,
                        "イニング": "試合前",
                        "打順": i + 1,
                        "選手名": clean_name,
                        "位置": current_pos,
                        "結果": "スタメン",
                        "打球方向": "---",
                        "打点": 0,
                        "得点": 0,
                        "スコアラー": scorer,
                        "グラウンド": ground_name
                    })
                    st.session_state.setdefault("lineup_states", {})[i] = {
                        "name": clean_name,
                        "pos": current_pos
                    }
        else:
            for i in range(display_count):
                name_val = st.session_state.get(f"sn{i}")
                pos_val = st.session_state.get(f"sp{i}")
                if name_val:
                    clean_name = name_val.split(" (")[0].strip()
                    current_pos = pos_val if pos_val else "－"
                    
                    prev_state = st.session_state.get("lineup_states", {}).get(i, {})
                    prev_name = prev_state.get("name", "")
                    prev_pos = prev_state.get("pos", "")
                    
                    if prev_name and prev_name != clean_name:
                        rows_to_add.append({
                            "日付": current_date_formatted,
                            "対戦相手": opp_team,
                            "試合種別": match_type,
                            "イニング": inn_val,
                            "打順": i + 1,
                            "選手名": clean_name,
                            "位置": current_pos,
                            "結果": "交代",
                            "打球方向": "---",
                            "打点": 0,
                            "得点": 0,
                            "スコアラー": scorer,
                            "グラウンド": ground_name
                        })
                        st.session_state["lineup_states"][i] = {"name": clean_name, "pos": current_pos}
                    
                    elif prev_name == clean_name and prev_pos and prev_pos != current_pos:
                        rows_to_add.append({
                            "日付": current_date_formatted,
                            "対戦相手": opp_team,
                            "試合種別": match_type,
                            "イニング": inn_val,
                            "打順": i + 1,
                            "選手名": clean_name,
                            "位置": current_pos,
                            "結果": "守備変更",
                            "打球方向": "---",
                            "打点": 0,
                            "得点": 0,
                            "スコアラー": scorer,
                            "グラウンド": ground_name
                        })
                        st.session_state["lineup_states"][i] = {"name": clean_name, "pos": current_pos}

        selected_bench = st.session_state.get("persistent_bench", [])
        registered_bench_names = set()
        if not today_batting_df.empty:
            registered_bench_names = set(
                today_batting_df[today_batting_df["結果"].astype(str) == "ベンチ"]["選手名"]
                .astype(str).str.strip()
            )

        for b_name in selected_bench:
            clean_b_name = b_name.split(" (")[0].strip()
            if clean_b_name and clean_b_name not in registered_bench_names:
                rows_to_add.append({
                    "日付": current_date_formatted,
                    "対戦相手": opp_team,
                    "試合種別": match_type,
                    "イニング": "試合前",
                    "打順": "",
                    "選手名": clean_b_name,
                    "位置": "－",
                    "結果": "ベンチ",
                    "打球方向": "---",
                    "打点": 0,
                    "得点": 0,
                    "スコアラー": scorer,
                    "グラウンド": ground_name
                })
                registered_bench_names.add(clean_b_name)

        quick_res = st.session_state.get("quick_sr")
        quick_dirs = st.session_state.get("quick_sd", [])
        quick_rbi = st.session_state.get("quick_si")
        
        if quick_res:
            dir_str = "".join(quick_dirs) if quick_dirs else "---"
            rbi_val = int(quick_rbi) if quick_rbi is not None else 0
            
            active_orders = 9
            for idx_check in range(display_count - 1, -1, -1):
                if st.session_state.get(f"sn{idx_check}"):
                    active_orders = idx_check + 1
                    break
            
            if not today_batting_df.empty:
                pa_df = today_batting_df[today_batting_df["結果"].astype(str).isin(PA_RESULTS)]
            else:
                pa_df = pd.DataFrame()
            
            total_pa = len(pa_df)
            batter_idx = (total_pa + st.session_state.get("batter_offset", 0)) % active_orders
            target_batter_name = st.session_state.get(f"sn{batter_idx}", "")
            
            if target_batter_name:
                clean_batter_name = target_batter_name.split(" (")[0].strip()
                auto_run = 1 if quick_res == "本塁打" else 0

                rows_to_add.append({
                    "日付": current_date_formatted,
                    "対戦相手": opp_team,
                    "試合種別": match_type,
                    "イニング": inn_val,
                    "打順": batter_idx + 1,
                    "選手名": clean_batter_name,
                    "位置": st.session_state.get(f"sp{batter_idx}", "－"),
                    "結果": quick_res,
                    "打球方向": dir_str,
                    "打点": rbi_val,
                    "得点": auto_run,
                    "スコアラー": scorer,
                    "グラウンド": ground_name
                })

        # --- 各行の走塁結果ボタンの処理 ---
        for i in range(display_count):
            row_action = st.session_state.get(f"row_sr{i}")
            if row_action and row_action != "--- (選択なし)":
                name_val = st.session_state.get(f"sn{i}")
                if name_val:
                    clean_name = name_val.split(" (")[0].strip()
                    
                    is_score = (row_action == "得点1")
                    res_val = "走塁記録" if is_score else row_action
                    score_val = 1 if is_score else 0
                    
                    rows_to_add.append({
                        "日付": current_date_formatted,
                        "対戦相手": opp_team,
                        "試合種別": match_type,
                        "イニング": inn_val,
                        "打順": i + 1,
                        "選手名": clean_name,
                        "位置": st.session_state.get(f"sp{i}", "－"),
                        "結果": res_val,
                        "打球方向": "---",
                        "打点": 0,
                        "得点": score_val,
                        "スコアラー": scorer,
                        "グラウンド": ground_name
                    })

        if rows_to_add:
            new_df_to_append = pd.DataFrame(rows_to_add)
            dt_parsed = pd.to_datetime(selected_date_str, errors='coerce')
            formatted_date = dt_parsed.strftime('%Y-%m-%d') if pd.notna(dt_parsed) else current_date_formatted
            
            new_df_to_append["日付_dt"] = dt_parsed
            new_df_to_append["Year"] = dt_parsed.year if pd.notna(dt_parsed) else datetime.datetime.now().year
            new_df_to_append["_date_str"] = formatted_date

            updated_full_df = pd.concat([df_batting, new_df_to_append], ignore_index=True)
            try:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=updated_full_df)
                st.session_state[cache_key] = updated_full_df
                st.session_state["needs_batting_clear"] = True
                st.success("登録しました！")
                st.rerun()
            except Exception as e:
                st.error(f"保存に失敗しました: {e}")
        else:
            st.warning("登録する内容がありません。打席結果やスタメンを入力してください。")

    # ==========================================
    # 6. 詳細入力 (打席結果登録フォーム)
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

    col_adj1, col_adj2, col_adj3, col_adj4 = st.columns([2.5, 1.0, 1.0, 1.0])
    with col_adj1:
        st.markdown(f"<div style='font-weight:bold; font-size:16px; line-height:2.4;'>📍 打順調整 (オフセット: {st.session_state.get('batter_offset', 0)})</div>", unsafe_allow_html=True)
    with col_adj2:
        if st.button("◀ 前へ", use_container_width=True):
            st.session_state["batter_offset"] = st.session_state.get("batter_offset", 0) - 1
            st.rerun()
    with col_adj3:
        if st.button("リセット", use_container_width=True):
            st.session_state["batter_offset"] = 0
            st.rerun()
    with col_adj4:
        if st.button("次へ ▶", use_container_width=True):
            st.session_state["batter_offset"] = st.session_state.get("batter_offset", 0) + 1
            st.rerun()

    with st.container():
        submitted = st.button("登録実行 (スコアボード反映)", type="primary", use_container_width=True)

        if st.session_state.get("batting_error_msg"):
            st.error(st.session_state["batting_error_msg"])
            st.session_state["batting_error_msg"] = None

        c_inn, c_outs = st.columns([1.5, 2.5])
        
        with c_inn:
            def_inn_ix = inn_list.index(current_inn_val) if current_inn_val in inn_list else 0
            curr_inn = st.selectbox("イニング選択", inn_list, index=def_inn_ix, label_visibility="collapsed")
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

        active_orders = 9
        display_count = st.session_state.get("display_order_count", 9)
        for i in range(display_count - 1, -1, -1):
            if st.session_state.get(f"sn{i}"):
                active_orders = i + 1
                break

        if not today_batting_df.empty:
            valid_pa_df = today_batting_df[today_batting_df["結果"].astype(str).isin(PA_RESULTS)]
            total_pa_count = len(valid_pa_df)
        else:
            total_pa_count = 0

        current_batter_index = (total_pa_count + st.session_state.get("batter_offset", 0)) % active_orders
        current_order_num = current_batter_index + 1
        
        raw_batter_name = st.session_state.get(f"sn{current_batter_index}", "")
        formatted_batter_name = local_fmt(raw_batter_name) if raw_batter_name else "（未設定）"

        batting_results = ["凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", 
                           "失策(ゴロ)", "失策(フライ)", "野選", "併殺打", "振り逃げ三振", "打撃妨害"]

        q_cols = [4.0, 5.0]
        qc = st.columns(q_cols)

        with qc[0]:
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 0px 12px; border-radius: 8px; border-left: 8px solid #ff4b4b; height: 50px; display: flex; align-items: center; justify-content: flex-start; gap: 10px; box-sizing: border-box;">
                <span style="color: #555; font-weight: bold; white-space: nowrap;">📍 打順</span>
                <span style="color: #111; font-weight: bold; white-space: nowrap;">{current_order_num}番</span>
                <span style="color: #ff4b4b; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{formatted_batter_name}</span>
            </div>
            """, unsafe_allow_html=True)

        with qc[1]:
            current_res = st.session_state.get("quick_sr")
            current_dirs = st.session_state.get("quick_sd", [])
            current_rbi = st.session_state.get("quick_si")
            
            res_label = f" 🟢 {current_res}" if current_res else ""
            dir_label = f" ({''.join(current_dirs)})" if current_dirs else ""
            rbi_label = f" [打点{current_rbi}]" if current_rbi is not None else ""
            
            summary_btn_label = f"打席結果{res_label}{dir_label}{rbi_label} 🔽"
            
            with st.popover(summary_btn_label, use_container_width=True):

                st.markdown("##### ⚾ 打席結果を選択")
                st.pills("打席結果", batting_results, key="quick_sr", label_visibility="collapsed")

                st.markdown("---")
                st.markdown("##### ⚾ 打球方向を選択（複数選択可）")
                dir_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                st.pills("打球方向", dir_options, selection_mode="multi", key="quick_sd", label_visibility="collapsed")

                st.markdown("---")
                st.markdown("##### ⚾ 打点がある場合は選択 (1〜4)")
                rbi_options = [0, 1, 2, 3, 4]
                st.pills("打点", rbi_options, key="quick_si", label_visibility="collapsed")

                st.markdown("---")
                if st.button("🔄 入力をすべてクリア", use_container_width=True, key="quick_all_clear_btn"):
                    st.session_state["needs_batting_clear"] = True
                    st.rerun()

        st.divider()

        # ==========================================
        # 可変人数（デフォルト15〜最大20）のループ
        # ==========================================
        for i in range(display_count):
            pos_key = f"sp{i}"
            name_key = f"sn{i}"
            row_sr_key = f"row_sr{i}"
            
            with st.container(border=True):
                c_row = st.columns([0.7, 2.1, 3.2, 2.3, 3.7])
                
                with c_row[0]:
                    st.markdown(f"<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;'>{i+1}</div>", unsafe_allow_html=True)

                with c_row[1]:
                    cur_pos = st.session_state.get(pos_key, "")
                    pos_btn_label = f"{cur_pos} 🔽" if cur_pos and cur_pos != "－" else "守備選択 🔽"
                    with st.popover(pos_btn_label, use_container_width=True):
                        st.markdown(f"##### {i+1}番 守備位置を選択")
                        st.pills(f"守備ピル {i}", pos_options, key=pos_key, label_visibility="collapsed")
                
                with c_row[2]:
                    cur_name_raw = st.session_state.get(name_key, "")
                    formatted_cur_name = local_fmt(cur_name_raw) if cur_name_raw else "選手選択 🔽"
                    with st.popover(formatted_cur_name, use_container_width=True):
                        st.markdown(f"##### {i+1}番 選手を選択")
                        st.pills(f"選手ピル {i}", player_options, format_func=local_fmt, key=name_key, label_visibility="collapsed")
                
                with c_row[3]:
                    current_row_sr = st.session_state.get(row_sr_key)
                    if current_row_sr and current_row_sr != "--- (選択なし)":
                        sr_btn_label = f"🟢 {current_row_sr} 🔽"
                    else:
                        sr_btn_label = "走塁結果 🔽"
                        
                    with st.popover(sr_btn_label, use_container_width=True):
                        st.markdown(f"##### {i+1}番 走塁結果を選択")
                        base_options = ["--- (選択なし)", "得点1", "盗塁", "盗塁死", "走塁死", "牽制死"]
                        st.pills(f"走塁ピル {i}", base_options, key=row_sr_key, label_visibility="collapsed")
                
                with c_row[4]:
                    sel_p_name_raw = st.session_state.get(name_key)
                    history_text = ""
                    if sel_p_name_raw:
                        clean_name = sel_p_name_raw.split(" (")[0].strip()
                        if clean_name in player_history_dict:
                            history_text = player_history_dict[clean_name]
                    st.markdown(f"<div style='font-size:15px; line-height:1.4; padding-top:6px; color:#444; overflow-x:auto; white-space:nowrap;'>{history_text}</div>", unsafe_allow_html=True)

        if submitted:
            quick_res = st.session_state.get("quick_sr")
            quick_dirs = st.session_state.get("quick_sd", [])
            
            require_dir_results = [
                "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打",
                "犠打(ゴロ)", "犠打(フライ)", "犠飛", "失策(ゴロ)", "失策(フライ)",
                "野選", "併殺打"
            ]
            
            if quick_res in require_dir_results and not quick_dirs:
                st.session_state["batting_error_msg"] = f"⚠️ 「{quick_res}」を登録するには、打球方向を選択してください。"
                st.rerun()
            else:
                submit_everything(curr_inn)

    with st.expander(" 🚌 ベンチ入りメンバー", expanded=True):
        selected_bench = st.multiselect("ベンチメンバー", ALL_PLAYERS, default=st.session_state.get("persistent_bench", []), key="bench_selection_widget", format_func=local_fmt)
        st.session_state["persistent_bench"] = selected_bench

    st.divider()
    col_disp1, col_disp2, col_disp3 = st.columns([2.0, 1.0, 1.0])
    with col_disp1:
        st.markdown(f"<div style='font-weight:bold; font-size:16px; line-height:2.4;'>👥 打順の表示人数: {st.session_state.get('display_order_count', 9)}人</div>", unsafe_allow_html=True)
    with col_disp2:
        if st.button("➖ 減らす", use_container_width=True):
            if st.session_state["display_order_count"] > 9:
                st.session_state["display_order_count"] -= 1
                idx = st.session_state["display_order_count"]
                for k in [f"sn{idx}", f"sp{idx}", f"row_sr{idx}"]:
                    st.session_state.pop(k, None)
                st.rerun()
    with col_disp3:
        if st.button("➕ 追加 (最大20)", use_container_width=True):
            if st.session_state["display_order_count"] < 20:
                st.session_state["display_order_count"] += 1
                st.rerun()