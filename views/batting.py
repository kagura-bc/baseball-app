import datetime
import re
import time
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from config.settings import ALL_POSITIONS, SPREADSHEET_URL
from utils.players import get_active_players
from utils.ui import fmt_player_name, render_out_indicator_3, render_scoreboard, show_homerun_effect


# --- ヘルパー関数 ---
def local_fmt(name):
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))


# ★ 打席としてカウントする（打順を進める）結果のリスト
PA_RESULTS = [
    "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打", 
    "三振", "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", 
    "失策(ゴロ)", "失策(フライ)", "野選", "併殺打", "振り逃げ三振", "打撃妨害"
]


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

    # 守備選択肢に 代打(打)・代走(走) を追加
    pos_options = [p for p in ALL_POSITIONS if p != ""]
    for extra_pos in ["打", "走"]:
        if extra_pos not in pos_options:
            pos_options.append(extra_pos)

    player_options = [p for p in ALL_PLAYERS if p != ""]

    if "quick_clear_counter" not in st.session_state:
        st.session_state["quick_clear_counter"] = 0

    current_match_id = f"{selected_date_str}_{opp_team}_{match_type}"
    
    if "last_match_id" not in st.session_state:
        st.session_state["last_match_id"] = current_match_id
    
    match_changed = (st.session_state["last_match_id"] != current_match_id)
    
    if match_changed:
        all_keys = list(st.session_state.keys())
        target_prefixes = ["sn", "sp", "sr", "si", "st", "sd", "row_sr", "quick_", "persistent_", "batting_inning_select", "scorer_name_ui", "saved_lineup", "batter_offset", "lineup_states", "batting_error_msg", "sn_dh_pitcher"]
        for key in all_keys:
            if any(key.startswith(prefix) for prefix in target_prefixes):
                del st.session_state[key]
        
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"
        st.session_state["last_match_id"] = current_match_id

    if "persistent_inn" not in st.session_state:
        st.session_state["persistent_inn"] = f"1回{b_inning_suffix}"

    if "batter_offset" not in st.session_state:
        st.session_state["batter_offset"] = 0
        
    if "display_order_count" not in st.session_state:
        st.session_state["display_order_count"] = 9

    is_kagura_top = (kagura_order == "先攻 (表)")
    target_date_str = pd.to_datetime(selected_date_str, errors='coerce').strftime('%Y-%m-%d')

    cache_key = f"cache_batting_{selected_date_str}_{opp_team}_{match_type}"
    if cache_key in st.session_state:
        df_batting = st.session_state[cache_key]

    # カラム名を「打者名」「投手名」に変更・追加
    # 修正後
    expected_batting_cols = [
        "日付", "イニング", "打順", "打者名", "投手名", "位置", 
        "結果", "打球方向", "打点", "得点", "盗塁", "グラウンド", 
        "対戦相手", "試合種別", "スコアラー", "攻守", "球数", "ストライク", "ファールボール", "ボール"
    ]
    if df_batting.empty:
        df_batting = pd.DataFrame(columns=expected_batting_cols)
    else:
        for col in expected_batting_cols:
            if col not in df_batting.columns:
                df_batting[col] = ""

    if not df_pitching.empty:
        expected_pitching_cols = ["日付", "イニング", "投手名", "打順", "打者名", "結果", "失点", "自責点", "被安打", "奪三振", "アウト数", "種別", "対戦相手", "試合種別"]
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

    if "lineup_states" not in st.session_state:
        st.session_state["lineup_states"] = {}

    b_col_name = "打者名" if "打者名" in today_batting_df.columns else "選手名"

    if not today_batting_df.empty:
        lineup_event_df = today_batting_df[today_batting_df["結果"].astype(str).isin(["スタメン", "守備変更", "交代", "試合前"])]
        for i in range(15):
            order_num = i + 1
            order_rows = lineup_event_df[pd.to_numeric(lineup_event_df["打順"], errors='coerce') == order_num]
            if not order_rows.empty:
                latest_row = order_rows.iloc[-1]
                latest_name = str(latest_row.get(b_col_name, "")).strip()
                latest_pos = str(latest_row.get("位置", "")).strip()
                if latest_name and latest_name not in ["nan", "チーム記録", ""]:
                    st.session_state["lineup_states"][i] = {
                        "name": latest_name,
                        "pos": latest_pos if latest_pos and latest_pos != "nan" else "－"
                    }
        
        # DH投手の最新状態取得
        dh_p_rows = lineup_event_df[lineup_event_df["位置"].astype(str) == "投"]
        if not dh_p_rows.empty:
            dh_p_latest = str(dh_p_rows.iloc[-1].get(b_col_name, "")).strip()
            if dh_p_latest and dh_p_latest not in ["nan", ""]:
                st.session_state["dh_pitcher_name_state"] = dh_p_latest

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
                
                if name_val and name_val not in ["nan", "チーム記録", ""]:
                    matched_name = next((p for p in player_options if p.split(" (")[0].strip() == name_val or p == name_val), None)
                    if matched_name and (name_key not in st.session_state or not st.session_state[name_key]):
                        st.session_state[name_key] = matched_name
                        
                if pos_val and pos_val in pos_options and pos_val not in ["nan", "－"]:
                    if pos_key not in st.session_state or not st.session_state[pos_key]:
                        st.session_state[pos_key] = pos_val

        if "dh_pitcher_name_state" in st.session_state and ("sn_dh_pitcher" not in st.session_state or not st.session_state["sn_dh_pitcher"]):
            dh_p_val = st.session_state["dh_pitcher_name_state"]
            matched_dh_p = next((p for p in player_options if p.split(" (")[0].strip() == dh_p_val or p == dh_p_val), None)
            if matched_dh_p:
                st.session_state["sn_dh_pitcher"] = matched_dh_p

    if not today_batting_df.empty:
        scoreboard_df = today_batting_df[today_batting_df["イニング"] != "まとめ入力"]
    else:
        scoreboard_df = today_batting_df

    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)
    st.divider()

    player_history_dict = {}
    if not today_batting_df.empty:
        valid_history_df = today_batting_df[~today_batting_df["結果"].isin(["スタメン", "守備変更", "交代", "ベンチ"])]
        if not valid_history_df.empty and b_col_name in valid_history_df.columns:
            for clean_name, group in valid_history_df.groupby(b_col_name):
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
                    
                    # 走塁結果（盗塁・進塁・走塁記録・残塁・得点等）は打席カウントから除外
                    if res in ["盗塁", "盗塁成功"]:
                        stolen_base_count += 1
                        continue
                    elif res in ["盗塁死", "走塁死", "牽制死", "走塁記録", "残塁", "進塁1", "進塁2", "進塁", "得点"]:
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

    def submit_everything(inn_val):
        rows_to_add = []
        current_date_formatted = pd.to_datetime(selected_date_str).strftime('%Y-%m-%d')
        
        curr_counter = st.session_state.get("quick_clear_counter", 0)
        
        pitch_count_val = st.session_state.get(f"pitch_count_{curr_counter}", 0)
        strike_count_val = st.session_state.get(f"s_count_{curr_counter}", 0)
        ball_count_val = st.session_state.get(f"b_count_{curr_counter}", 0)
        
        final_ground = ground_name or st.session_state.get("ground_name", "")
        final_opp = opp_team or st.session_state.get("opp_team", "")
        final_match_type = match_type or st.session_state.get("match_type", "")
        final_order = kagura_order or st.session_state.get("kagura_order", "先攻 (表)")

        # 対戦相手の投手名を取得（セッションまたは履歴から）
        opp_pitcher_name = "不明"
        for i in range(20):
            if st.session_state.get(f"opp_sp_{i}") in ["投", "投手", "P"]:
                p_n = st.session_state.get(f"opp_sn_{i}")
                if p_n and p_n not in ["選手", "nan", "None", ""]:
                    opp_pitcher_name = p_n
                    break
        if opp_pitcher_name == "不明" and st.session_state.get("opp_sn_dh_pitcher"):
            dh_p = st.session_state.get("opp_sn_dh_pitcher")
            if dh_p and dh_p not in ["選手", "nan", "None", ""]:
                opp_pitcher_name = dh_p
        if opp_pitcher_name == "不明" and not today_batting_df.empty and "投手名" in today_batting_df.columns:
            valid_p = today_batting_df["投手名"].dropna().astype(str).str.strip()
            valid_p = valid_p[~valid_p.isin(["", "nan", "None", "不明"])]
            if not valid_p.empty:
                opp_pitcher_name = valid_p.iloc[-1]

        if not today_batting_df.empty:
            if not final_ground and "グラウンド" in today_batting_df.columns:
                valid_g = today_batting_df["グラウンド"].dropna().astype(str).str.strip()
                valid_g = valid_g[~valid_g.isin(["", "nan", "None"])]
                if not valid_g.empty: final_ground = valid_g.iloc[-1]
            if not final_opp and "対戦相手" in today_batting_df.columns:
                valid_o = today_batting_df["対戦相手"].dropna().astype(str).str.strip()
                valid_o = valid_o[~valid_o.isin(["", "nan", "None"])]
                if not valid_o.empty: final_opp = valid_o.iloc[-1]
            if not final_match_type and "試合種別" in today_batting_df.columns:
                valid_m = today_batting_df["試合種別"].dropna().astype(str).str.strip()
                valid_m = valid_m[~valid_m.isin(["", "nan", "None"])]
                if not valid_m.empty: final_match_type = valid_m.iloc[-1]

        # 既存の試合設定枠のスコアラーを使用
        raw_scorer = st.session_state.get("scorer_name_ui", "") or st.session_state.get("persistent_scorer", "")
        scorer = raw_scorer.split(" (")[0].strip() if raw_scorer else ""
        display_count = st.session_state.get("display_order_count", 9)
        
        if "saved_lineup" not in st.session_state:
            st.session_state["saved_lineup"] = {}

        has_today_lineup = False
        if not df_batting.empty and "結果" in df_batting.columns:
            df_bat_check = df_batting.copy()
            df_bat_check["_date_str"] = pd.to_datetime(df_bat_check["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
            
            match_mask = (
                (df_bat_check["_date_str"] == current_date_formatted) &
                (df_bat_check["対戦相手"].astype(str).str.strip() == str(final_opp).strip()) &
                (df_bat_check["試合種別"].astype(str).str.strip() == str(final_match_type).strip()) &
                (df_bat_check["結果"].astype(str) == "スタメン")
            )
            has_today_lineup = not df_bat_check[match_mask].empty

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
                        "対戦相手": final_opp,
                        "試合種別": final_match_type,
                        "イニング": "試合前",
                        "打順": i + 1,
                        "打者名": clean_name,
                        "投手名": opp_pitcher_name,
                        "位置": current_pos,
                        "結果": "スタメン",
                        "打球方向": "---",
                        "打点": 0,
                        "得点": 0,
                        "スコアラー": scorer,
                        "攻守": final_order,
                        "グラウンド": final_ground
                    })
                    st.session_state.setdefault("lineup_states", {})[i] = {
                        "name": clean_name,
                        "pos": current_pos
                    }
            
            # DH時投手のスタメン追加
            dh_pitcher_val = st.session_state.get("sn_dh_pitcher")
            if dh_pitcher_val:
                clean_dh_p_name = dh_pitcher_val.split(" (")[0].strip()
                rows_to_add.append({
                    "日付": current_date_formatted,
                    "対戦相手": final_opp,
                    "試合種別": final_match_type,
                    "イニング": "試合前",
                    "打順": "",
                    "打者名": clean_dh_p_name,
                    "投手名": opp_pitcher_name,
                    "位置": "投",
                    "結果": "スタメン",
                    "打球方向": "---",
                    "打点": 0,
                    "得点": 0,
                    "スコアラー": scorer,
                    "攻守": final_order,
                    "グラウンド": final_ground
                })
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
                            "対戦相手": final_opp,
                            "試合種別": final_match_type,
                            "イニング": inn_val,
                            "打順": i + 1,
                            "打者名": clean_name,
                            "投手名": opp_pitcher_name,
                            "位置": current_pos,
                            "結果": "交代",
                            "打球方向": "---",
                            "打点": 0,
                            "得点": 0,
                            "スコアラー": scorer,
                            "攻守": final_order,
                            "グラウンド": final_ground
                        })
                        st.session_state["lineup_states"][i] = {"name": clean_name, "pos": current_pos}
                    
                    elif prev_name == clean_name and prev_pos and prev_pos != current_pos:
                        rows_to_add.append({
                            "日付": current_date_formatted,
                            "対戦相手": final_opp,
                            "試合種別": final_match_type,
                            "イニング": inn_val,
                            "打順": i + 1,
                            "打者名": clean_name,
                            "投手名": opp_pitcher_name,
                            "位置": current_pos,
                            "結果": "守備変更",
                            "打球方向": "---",
                            "打点": 0,
                            "得点": 0,
                            "スコアラー": scorer,
                            "攻守": final_order,
                            "グラウンド": final_ground
                        })
                        st.session_state["lineup_states"][i] = {"name": clean_name, "pos": current_pos}

            # DH投手の交代チェック
            dh_pitcher_val = st.session_state.get("sn_dh_pitcher")
            if dh_pitcher_val:
                clean_dh_p_name = dh_pitcher_val.split(" (")[0].strip()
                prev_dh_p = st.session_state.get("dh_pitcher_name_state", "")
                if prev_dh_p and prev_dh_p != clean_dh_p_name:
                    rows_to_add.append({
                        "日付": current_date_formatted,
                        "対戦相手": final_opp,
                        "試合種別": final_match_type,
                        "イニング": inn_val,
                        "打順": "",
                        "打者名": clean_dh_p_name,
                        "投手名": opp_pitcher_name,
                        "位置": "投",
                        "結果": "交代",
                        "打球方向": "---",
                        "打点": 0,
                        "得点": 0,
                        "スコアラー": scorer,
                        "攻守": final_order,
                        "グラウンド": final_ground
                    })
                    st.session_state["dh_pitcher_name_state"] = clean_dh_p_name

        selected_bench = st.session_state.get("persistent_bench", [])
        registered_bench_names = set()
        if not today_batting_df.empty and b_col_name in today_batting_df.columns:
            registered_bench_names = set(
                today_batting_df[today_batting_df["結果"].astype(str) == "ベンチ"][b_col_name]
                .astype(str).str.strip()
            )

        for b_name in selected_bench:
            clean_b_name = b_name.split(" (")[0].strip()
            if clean_b_name and clean_b_name not in registered_bench_names:
                rows_to_add.append({
                    "日付": current_date_formatted,
                    "対戦相手": final_opp,
                    "試合種別": final_match_type,
                    "イニング": "試合前",
                    "打順": "",
                    "打者名": clean_b_name,
                    "投手名": opp_pitcher_name,
                    "位置": "－",
                    "結果": "ベンチ",
                    "打球方向": "---",
                    "打点": 0,
                    "得点": 0,
                    "スコアラー": scorer,
                    "攻守": final_order,
                    "グラウンド": final_ground
                })
                registered_bench_names.add(clean_b_name)

        curr_counter = st.session_state.get("quick_clear_counter", 0)
        quick_res = st.session_state.get(f"quick_sr_{curr_counter}")
        quick_dirs = st.session_state.get(f"quick_sd_{curr_counter}", [])
        quick_rbi = st.session_state.get(f"quick_si_{curr_counter}")
        
        target_batter_name = ""
        if quick_res:
            dir_str = "".join(quick_dirs) if quick_dirs else "---"
            rbi_val = int(quick_rbi) if quick_rbi is not None else 0

            # 入力カウントの取得
            pitch_count_val = st.session_state.get(f"pitch_count_{curr_counter}", 0)
            strike_count_val = st.session_state.get(f"s_count_{curr_counter}", 0)
            ball_count_val = st.session_state.get(f"b_count_{curr_counter}", 0)
            foul_count_val = st.session_state.get(f"f_count_{curr_counter}", 0)
            
            # ★ 打席結果に応じた最終球のカウント判定
            final_strike_count = strike_count_val + foul_count_val
            final_ball_count = ball_count_val

            if quick_res in ["四球", "死球"]:
                # 四球・死球の場合は最後の1球をボールに加算
                final_ball_count += 1
            elif quick_res:
                # フェア打球・三振等の場合は最後の1球をストライクに加算
                final_strike_count += 1
            
            # 総球数の計算
            final_pitch_count = final_ball_count + final_strike_count
            
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
                    "対戦相手": final_opp,
                    "試合種別": final_match_type,
                    "イニング": inn_val,
                    "打順": batter_idx + 1,
                    "打者名": clean_batter_name,
                    "投手名": opp_pitcher_name,
                    "位置": st.session_state.get(f"sp{batter_idx}", "－"),
                    "結果": quick_res,
                    "打球方向": dir_str,
                    "打点": rbi_val,
                    "得点": auto_run,
                    "スコアラー": scorer,
                    "攻守": final_order,
                    "グラウンド": final_ground,
                    "球数": final_pitch_count,
                    "ストライク": final_strike_count,  # ★ 修正後のストライク数
                    "ファールボール": foul_count_val,   # ★ 新規追加
                    "ボール": ball_count_val
                })

        single_out_list = [
        "凡退(ゴロ)", "凡退(フライ)", "三振", "犠打(ゴロ)", "犠打(フライ)", 
        "犠飛", "走塁死", "盗塁死", "牽制死"
        ]
        
        existing_outs = 0
        if not today_batting_df.empty:
            inn_df_check = today_batting_df[today_batting_df["イニング"] == inn_val]
            s_outs = len(inn_df_check[inn_df_check["結果"].isin(single_out_list)])
            d_outs = len(inn_df_check[inn_df_check["結果"] == "併殺打"]) * 2
            existing_outs = s_outs + d_outs

        play_outs = 0
        if quick_res in single_out_list: play_outs += 1
        elif quick_res == "併殺打": play_outs += 2
            
        for base in ["1b", "2b", "3b"]:
            if st.session_state.get(f"runner_{base}_res_{curr_counter}") in ["走塁死", "盗塁死", "牽制死"]:
                play_outs += 1

        is_change = (existing_outs + play_outs >= 3)

        for base in ["1b", "2b", "3b"]:
            r_name_raw = st.session_state.get(f"runner_{base}_{curr_counter}")
            r_res = st.session_state.get(f"runner_{base}_res_{curr_counter}")
            r_fielder = st.session_state.get(f"runner_{base}_fielder_{curr_counter}", "")
            
            if r_name_raw:
                clean_r_name = r_name_raw.split(" (")[0].strip()
                
                order_num = ""
                for i in range(display_count):
                    n = st.session_state.get(f"sn{i}")
                    if n and n.split(" (")[0].strip() == clean_r_name:
                        order_num = i + 1
                        break

                # 走塁結果の判定部分（448行目付近）
                if r_res:
                    is_score = (r_res == "得点")
                    is_stolen = (r_res == "盗塁") # ★ 盗塁判定を追加
                    res_val = "走塁記録" if is_score else r_res
                    score_val = 1 if is_score else 0
                    stolen_val = 1 if is_stolen else 0 # ★ 盗塁数をカウント
                    dir_val = r_fielder if r_fielder and r_res in ["走塁死", "盗塁死", "牽制死"] else "---"
                    
                    rows_to_add.append({
                        "日付": current_date_formatted,
                        "対戦相手": final_opp,
                        "試合種別": final_match_type,
                        "イニング": inn_val,
                        "打順": order_num,
                        "打者名": clean_r_name,
                        "投手名": opp_pitcher_name,
                        "位置": "－",
                        "結果": res_val,
                        "打球方向": dir_val,
                        "打点": 0,
                        "得点": score_val,
                        "盗塁": stolen_val, # ★ 追加
                        "スコアラー": scorer,
                        "攻守": final_order,
                        "グラウンド": final_ground
                    })
                elif is_change:
                    rows_to_add.append({
                        "日付": current_date_formatted,
                        "対戦相手": final_opp,
                        "試合種別": final_match_type,
                        "イニング": inn_val,
                        "打順": order_num,
                        "打者名": clean_r_name,
                        "投手名": opp_pitcher_name,
                        "位置": "－",
                        "結果": "残塁",
                        "打球方向": "---",
                        "打点": 0,
                        "得点": 0,
                        "スコアラー": scorer,
                        "攻守": final_order,
                        "グラウンド": final_ground
                    })

        # 走者の進塁・引き継ぎ計算
        if is_change:
            st.session_state["persistent_runners"] = {"1b": None, "2b": None, "3b": None}
        else:
            cur_1b_name = st.session_state.get(f"runner_1b_{curr_counter}")
            cur_2b_name = st.session_state.get(f"runner_2b_{curr_counter}")
            cur_3b_name = st.session_state.get(f"runner_3b_{curr_counter}")

            res_1b = st.session_state.get(f"runner_1b_res_{curr_counter}")
            res_2b = st.session_state.get(f"runner_2b_res_{curr_counter}")
            res_3b = st.session_state.get(f"runner_3b_res_{curr_counter}")

            r1_next = "1b" if cur_1b_name else None
            r2_next = "2b" if cur_2b_name else None
            r3_next = "3b" if cur_3b_name else None

            # 1塁走者の進行判定
            if cur_1b_name and res_1b:
                if res_1b in ["盗塁", "進塁1", "進塁"]:
                    r1_next = "2b"
                elif res_1b == "進塁2":
                    r1_next = "3b"
                elif res_1b in ["得点", "走塁死", "盗塁死", "牽制死"]:
                    r1_next = None

            # 2塁走者の進行判定
            if cur_2b_name and res_2b:
                if res_2b in ["盗塁", "進塁1", "進塁"]:
                    r2_next = "3b"
                elif res_2b in ["進塁2", "得点"]:
                    r2_next = None
                elif res_2b in ["走塁死", "盗塁死", "牽制死"]:
                    r2_next = None

            # 3塁走者の進行判定
            if cur_3b_name and res_3b:
                if res_3b in ["得点", "走塁死", "盗塁死", "牽制死", "盗塁", "進塁1", "進塁2", "進塁"]:
                    r3_next = None

            # 四球・死球（押し出し）
            if quick_res in ["四球", "死球"]:
                r1_next = "2b" if cur_1b_name else None
                r2_next = "3b" if (cur_2b_name and cur_1b_name) else ("2b" if cur_2b_name else None)
                r3_next = None if (cur_3b_name and cur_2b_name and cur_1b_name) else ("3b" if cur_3b_name else None)

            # 打者自身の出塁による占有位置
            b_next = None
            if quick_res in ["単打", "四球", "死球", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]:
                b_next = "1b"
            elif quick_res == "二塁打":
                b_next = "2b"
            elif quick_res == "三塁打":
                b_next = "3b"

            next_runners = {"1b": None, "2b": None, "3b": None}

            def clean_and_match(name_str):
                if not name_str: return None
                return next((p for p in player_options if p == name_str or p.split(" (")[0].strip() == name_str.split(" (")[0].strip()), name_str)

            if r1_next in next_runners: next_runners[r1_next] = clean_and_match(cur_1b_name)
            if r2_next in next_runners: next_runners[r2_next] = clean_and_match(cur_2b_name)
            if r3_next in next_runners: next_runners[r3_next] = clean_and_match(cur_3b_name)
            if b_next in next_runners and target_batter_name:
                next_runners[b_next] = clean_and_match(target_batter_name)

            st.session_state["persistent_runners"] = next_runners

        if rows_to_add:
            new_df_to_append = pd.DataFrame(rows_to_add)

            updated_full_df = pd.concat([df_batting, new_df_to_append], ignore_index=True)
            
            save_cols = [c for c in expected_batting_cols if c not in ["日付_dt", "Year", "_date_str"] and c in updated_full_df.columns]
            df_to_save = updated_full_df[save_cols].copy()

            try:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_batting, data=df_to_save)
                st.session_state[cache_key] = updated_full_df
                
                next_counter = curr_counter + 1
                st.session_state["quick_clear_counter"] = next_counter

                is_pa_completed = bool(quick_res and quick_res in PA_RESULTS)
                if not is_pa_completed:
                    st.session_state[f"b_count_{next_counter}"] = ball_count_val
                    st.session_state[f"s_count_{next_counter}"] = strike_count_val
                    st.session_state[f"f_count_{next_counter}"] = foul_count_val
                    st.session_state[f"pitch_count_{next_counter}"] = pitch_count_val

                st.success("登録しました！")
                st.rerun()
            except Exception as e:
                st.error(f"保存に失敗しました: {e}")
        else:
            st.warning("登録する内容がありません。打席結果やスタメンを入力してください。")

    this_year = datetime.datetime.now().year
    if not df_batting.empty:
        df_batting["日付_dt"] = pd.to_datetime(df_batting["日付"], errors='coerce')
        df_this_season = df_batting[df_batting["日付_dt"].dt.year == this_year].copy()
    else:
        df_this_season = pd.DataFrame()

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

    @st.fragment
    def batting_input_fragment():
        curr_counter = st.session_state.get("quick_clear_counter", 0)
        submitted = st.button("登録実行 (スコアボード反映)", type="primary", use_container_width=True)

        if st.session_state.get("batting_error_msg"):
            st.error(st.session_state["batting_error_msg"])
            st.session_state["batting_error_msg"] = None

        # イニング選択・BSO表示
        c_inn, c_outs = st.columns([1.2, 3.8])
        
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

            b_cnt = st.session_state.get(f"b_count_{curr_counter}", 0)
            s_cnt = st.session_state.get(f"s_count_{curr_counter}", 0)
            p_cnt = st.session_state.get(f"pitch_count_{curr_counter}", 0)

            st.markdown(render_bso_indicator(disp_outs, b_cnt, s_cnt, p_cnt), unsafe_allow_html=True)

            b_col1, b_col2, b_col3, b_col4 = st.columns([1.1, 1.1, 1.1, 0.8])

            with b_col1:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#22c55e;'>🟢 ボール</div>", unsafe_allow_html=True)
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("➖", key=f"btn_b_sub_{curr_counter}", use_container_width=True, disabled=(b_cnt <= 0)):
                        st.session_state[f"pitch_count_{curr_counter}"] = max(0, p_cnt - 1)
                        st.session_state[f"b_count_{curr_counter}"] = max(0, b_cnt - 1)
                        st.rerun()
                with bc2:
                    if st.button("➕", key=f"btn_b_add_{curr_counter}", use_container_width=True, disabled=(b_cnt >= 3)):
                        if b_cnt < 3:
                            st.session_state[f"pitch_count_{curr_counter}"] = p_cnt + 1
                            st.session_state[f"b_count_{curr_counter}"] = b_cnt + 1
                        st.rerun()

            with b_col2:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#eab308;'>🟡 ストライク</div>", unsafe_allow_html=True)
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button("➖", key=f"btn_s_sub_{curr_counter}", use_container_width=True, disabled=(s_cnt <= 0)):
                        st.session_state[f"pitch_count_{curr_counter}"] = max(0, p_cnt - 1)
                        st.session_state[f"s_count_{curr_counter}"] = max(0, s_cnt - 1)
                        st.rerun()
                with sc2:
                    if st.button("➕", key=f"btn_s_add_{curr_counter}", use_container_width=True, disabled=(s_cnt >= 2)):
                        if s_cnt < 2:
                            st.session_state[f"pitch_count_{curr_counter}"] = p_cnt + 1
                            st.session_state[f"s_count_{curr_counter}"] = s_cnt + 1
                        st.rerun()

            f_cnt = st.session_state.get(f"f_count_{curr_counter}", 0)

            with b_col3:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#6b7280;'>⚪ ファール</div>", unsafe_allow_html=True)
                fc1, fc2 = st.columns(2)
                with fc1:
                    if st.button("➖", key=f"btn_f_sub_{curr_counter}", use_container_width=True, disabled=(f_cnt <= 0)):
                        st.session_state[f"pitch_count_{curr_counter}"] = max(0, p_cnt - 1)
                        st.session_state[f"f_count_{curr_counter}"] = max(0, f_cnt - 1)
                        st.rerun()
                with fc2:
                    if st.button("➕", key=f"btn_f_add_{curr_counter}", use_container_width=True):
                        st.session_state[f"pitch_count_{curr_counter}"] = p_cnt + 1
                        st.session_state[f"f_count_{curr_counter}"] = f_cnt + 1
                        if s_cnt < 2:
                            st.session_state[f"s_count_{curr_counter}"] = s_cnt + 1
                        st.rerun()

            with b_col4:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#374151;'>リセット</div>", unsafe_allow_html=True)
                if st.button("🔄", key=f"btn_reset_bso_{curr_counter}", use_container_width=True):
                    st.session_state[f"b_count_{curr_counter}"] = 0
                    st.session_state[f"s_count_{curr_counter}"] = 0
                    st.session_state[f"f_count_{curr_counter}"] = 0
                    st.session_state[f"pitch_count_{curr_counter}"] = 0
                    st.rerun()

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
            curr_counter = st.session_state.get("quick_clear_counter", 0)
            current_res = st.session_state.get(f"quick_sr_{curr_counter}")
            current_dirs = st.session_state.get(f"quick_sd_{curr_counter}", [])
            current_rbi = st.session_state.get(f"quick_si_{curr_counter}")
            
            res_label = f" 🟢 {current_res}" if current_res else ""
            dir_label = f" ({''.join(current_dirs)})" if current_dirs else ""
            rbi_label = f" [打点{current_rbi}]" if current_rbi is not None else ""
            
            summary_btn_label = f"打席結果{res_label}{dir_label}{rbi_label} 🔽"
            
            with st.popover(summary_btn_label, use_container_width=True):

                st.markdown("##### ⚾ 打席結果を選択")
                st.pills("打席結果", batting_results, key=f"quick_sr_{curr_counter}", label_visibility="collapsed")

                st.markdown("---")
                st.markdown("##### ⚾ 打球方向を選択（複数選択可）")
                dir_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
                st.pills("打球方向", dir_options, selection_mode="multi", key=f"quick_sd_{curr_counter}", label_visibility="collapsed")

                st.markdown("---")
                st.markdown("##### ⚾ 打点がある場合は選択 (1〜4)")
                rbi_options = [0, 1, 2, 3, 4]
                st.pills("打点", rbi_options, key=f"quick_si_{curr_counter}", label_visibility="collapsed")

                st.markdown("---")
                if st.button("🔄 入力をすべてクリア", use_container_width=True, key=f"clear_btn_{curr_counter}"):
                    st.session_state["quick_clear_counter"] = st.session_state.get("quick_clear_counter", 0) + 1
                    st.rerun()

        st.divider()

        # ==========================================
        # 走者状況
        # ==========================================
        p_runners = st.session_state.get("persistent_runners", {"1b": None, "2b": None, "3b": None})
        
        for b_key in ["1b", "2b", "3b"]:
            curr_r_key = f"runner_{b_key}_{curr_counter}"
            if curr_r_key not in st.session_state or st.session_state[curr_r_key] is None:
                st.session_state[curr_r_key] = p_runners.get(b_key)

        st.markdown("##### 🏃 走者状況")
        
        runner_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死", "進塁1", "進塁2"]
        out_fielder_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
        
        r_cols = st.columns(3)
        
        # --- 3塁タブ (左側) ---
        with r_cols[0]:
            st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>3塁</div>", unsafe_allow_html=True)
            
            r3_name_raw = st.session_state.get(f"runner_3b_{curr_counter}", "")
            r3_label = f"🟢 {local_fmt(r3_name_raw)} 🔽" if r3_name_raw else "選手選択 🔽"
            with st.popover(r3_label, use_container_width=True):
                st.markdown("##### 3塁走者を選択")
                st.pills("3塁選手", player_options, format_func=local_fmt, key=f"runner_3b_{curr_counter}", label_visibility="collapsed")
                
            r3_res = st.session_state.get(f"runner_3b_res_{curr_counter}")
            r3_f = st.session_state.get(f"runner_3b_fielder_{curr_counter}")
            r3_btn = f"🟢 {r3_res}({r3_f}) 🔽" if (r3_res in ["走塁死", "盗塁死", "牽制死"] and r3_f) else (f"🟢 {r3_res} 🔽" if r3_res else "走塁結果 🔽")
            
            with st.popover(r3_btn, use_container_width=True):
                st.markdown("##### 3塁 走塁結果を選択")
                cur_r3_res = st.pills("3塁結果ピル", runner_res_options, key=f"runner_3b_res_{curr_counter}", label_visibility="collapsed")
                if cur_r3_res in ["走塁死", "盗塁死", "牽制死"]:
                    st.markdown("---")
                    st.markdown("##### 🎯 処理野手（補殺）を選択")
                    st.pills("3塁処理野手ピル", out_fielder_options, key=f"runner_3b_fielder_{curr_counter}", label_visibility="collapsed")

        # --- 2塁タブ (中央) ---
        with r_cols[1]:
            st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>2塁</div>", unsafe_allow_html=True)
            
            r2_name_raw = st.session_state.get(f"runner_2b_{curr_counter}", "")
            r2_label = f"🟢 {local_fmt(r2_name_raw)} 🔽" if r2_name_raw else "選手選択 🔽"
            with st.popover(r2_label, use_container_width=True):
                st.markdown("##### 2塁走者を選択")
                st.pills("2塁選手", player_options, format_func=local_fmt, key=f"runner_2b_{curr_counter}", label_visibility="collapsed")
                
            r2_res = st.session_state.get(f"runner_2b_res_{curr_counter}")
            r2_f = st.session_state.get(f"runner_2b_fielder_{curr_counter}")
            r2_btn = f"🟢 {r2_res}({r2_f}) 🔽" if (r2_res in ["走塁死", "盗塁死", "牽制死"] and r2_f) else (f"🟢 {r2_res} 🔽" if r2_res else "走塁結果 🔽")
            
            with st.popover(r2_btn, use_container_width=True):
                st.markdown("##### 2塁 走塁結果を選択")
                cur_r2_res = st.pills("2塁結果ピル", runner_res_options, key=f"runner_2b_res_{curr_counter}", label_visibility="collapsed")
                if cur_r2_res in ["走塁死", "盗塁死", "牽制死"]:
                    st.markdown("---")
                    st.markdown("##### 🎯 処理野手（補殺）を選択")
                    st.pills("2塁処理野手ピル", out_fielder_options, key=f"runner_2b_fielder_{curr_counter}", label_visibility="collapsed")

        # --- 1塁タブ (右側) ---
        with r_cols[2]:
            st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>1塁</div>", unsafe_allow_html=True)
            
            r1_name_raw = st.session_state.get(f"runner_1b_{curr_counter}", "")
            r1_label = f"🟢 {local_fmt(r1_name_raw)} 🔽" if r1_name_raw else "選手選択 🔽"
            with st.popover(r1_label, use_container_width=True):
                st.markdown("##### 1塁走者を選択")
                st.pills("1塁選手", player_options, format_func=local_fmt, key=f"runner_1b_{curr_counter}", label_visibility="collapsed")
                
            r1_res = st.session_state.get(f"runner_1b_res_{curr_counter}")
            r1_f = st.session_state.get(f"runner_1b_fielder_{curr_counter}")
            r1_btn = f"🟢 {r1_res}({r1_f}) 🔽" if (r1_res in ["走塁死", "盗塁死", "牽制死"] and r1_f) else (f"🟢 {r1_res} 🔽" if r1_res else "走塁結果 🔽")
            
            with st.popover(r1_btn, use_container_width=True):
                st.markdown("##### 1塁 走塁結果を選択")
                cur_r1_res = st.pills("1塁結果ピル", runner_res_options, key=f"runner_1b_res_{curr_counter}", label_visibility="collapsed")
                if cur_r1_res in ["走塁死", "盗塁死", "牽制死"]:
                    st.markdown("---")
                    st.markdown("##### 🎯 処理野手（補殺）を選択")
                    st.pills("1塁処理野手ピル", out_fielder_options, key=f"runner_1b_fielder_{curr_counter}", label_visibility="collapsed")

        st.divider()

        # ==========================================
        # オーダー一覧
        # ==========================================
        for i in range(display_count):
            pos_key = f"sp{i}"
            name_key = f"sn{i}"
            
            with st.container(border=True):
                c_row = st.columns([0.8, 2.5, 3.5, 5.2])
                
                with c_row[0]:
                    st.markdown(f"<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;'>{i+1}</div>", unsafe_allow_html=True)

                with c_row[1]:
                    cur_pos = st.session_state.get(pos_key, "")
                    pos_btn_label = f"🟢 {cur_pos} 🔽" if cur_pos and cur_pos != "－" else "守備選択 🔽"
                    with st.popover(pos_btn_label, use_container_width=True):
                        st.markdown(f"##### {i+1}番 守備位置を選択")
                        st.pills(f"守備ピル {i}", pos_options, key=pos_key, label_visibility="collapsed")
                
                with c_row[2]:
                    cur_name_raw = st.session_state.get(name_key, "")
                    formatted_cur_name = f"🟢 {local_fmt(cur_name_raw)} 🔽" if cur_name_raw else "選手選択 🔽"
                    with st.popover(formatted_cur_name, use_container_width=True):
                        st.markdown(f"##### {i+1}番 選手を選択")
                        st.pills(f"選手ピル {i}", player_options, format_func=local_fmt, key=name_key, label_visibility="collapsed")
                
                with c_row[3]:
                    sel_p_name_raw = st.session_state.get(name_key)
                    history_text = ""
                    if sel_p_name_raw:
                        clean_name = sel_p_name_raw.split(" (")[0].strip()
                        if clean_name in player_history_dict:
                            history_text = player_history_dict[clean_name]
                    st.markdown(f"<div style='font-size:15px; line-height:1.4; padding-top:6px; color:#444; overflow-x:auto; white-space:nowrap;'>{history_text}</div>", unsafe_allow_html=True)

        # ------------------------------------------
        # ⚾ 投手専用枠 (DH制使用時)
        # ------------------------------------------
        with st.container(border=True):
            c_dh_row = st.columns([0.8, 2.5, 3.5, 5.2])
            with c_dh_row[0]:
                st.markdown("<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;'>投</div>", unsafe_allow_html=True)
            with c_dh_row[1]:
                st.markdown("<div style='text-align:center; font-size:14px; font-weight:bold; padding-top:10px; color:#4f46e5;'>🟢 投 (DH時)</div>", unsafe_allow_html=True)
            with c_dh_row[2]:
                cur_dh_p_raw = st.session_state.get("sn_dh_pitcher", "")
                formatted_dh_p = f"🟢 {local_fmt(cur_dh_p_raw)} 🔽" if cur_dh_p_raw else "投手選択 (DH時) 🔽"
                with st.popover(formatted_dh_p, use_container_width=True):
                    st.markdown("##### ⚾ DH時の投手を選択")
                    st.pills("DH投手ピル", player_options, format_func=local_fmt, key="sn_dh_pitcher", label_visibility="collapsed")
            with c_dh_row[3]:
                st.markdown("<div style='font-size:13px; color:#6b7280; padding-top:10px;'>※ DH制で打順に入らない投手を設定（打席は回りません）</div>", unsafe_allow_html=True)

        if submitted:
            quick_res = st.session_state.get(f"quick_sr_{curr_counter}")
            quick_dirs = st.session_state.get(f"quick_sd_{curr_counter}", [])
            
            cur_1b_runner = st.session_state.get(f"runner_1b_{curr_counter}")
            cur_2b_runner = st.session_state.get(f"runner_2b_{curr_counter}")
            cur_3b_runner = st.session_state.get(f"runner_3b_{curr_counter}")

            res_1b = st.session_state.get(f"runner_1b_res_{curr_counter}")
            res_2b = st.session_state.get(f"runner_2b_res_{curr_counter}")
            res_3b = st.session_state.get(f"runner_3b_res_{curr_counter}")

            require_dir_results = [
                "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打",
                "犠打(ゴロ)", "犠打(フライ)", "犠飛", "失策(ゴロ)", "失策(フライ)",
                "野選", "併殺打"
            ]

            b_to_1b_results = ["単打", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]
            b_to_2b_results = ["二塁打"]
            b_to_3b_results = ["三塁打"]

            if quick_res in require_dir_results and not quick_dirs:
                st.session_state["batting_error_msg"] = f"⚠️ 「{quick_res}」を登録するには、打球方向を選択してください。"
                st.rerun()
            elif cur_1b_runner and quick_res in b_to_1b_results and not res_1b:
                st.session_state["batting_error_msg"] = "⚠️ 1塁走者がいます。走塁結果を選択してください。"
                st.rerun()
            elif cur_2b_runner and quick_res in b_to_2b_results and not res_2b:
                st.session_state["batting_error_msg"] = "⚠️ 2塁走者がいます。走塁結果を選択してください。"
                st.rerun()
            elif cur_3b_runner and quick_res in b_to_3b_results and not res_3b:
                st.session_state["batting_error_msg"] = "⚠️ 3塁走者がいます。走塁結果を選択してください。"
                st.rerun()
            else:
                submit_everything(curr_inn)

    batting_input_fragment()

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