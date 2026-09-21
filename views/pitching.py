import re
import time
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from config.settings import ALL_POSITIONS, SPREADSHEET_URL
from utils.players import get_active_players
from utils.ui import fmt_player_name, render_scoreboard


# --- 🛠️ ヘルパー関数 ---

def local_fmt(name: str) -> str:
    """選手名に背番号等を付与した表示用文字列を返す"""
    return fmt_player_name(name, st.session_state.get("shared_player_numbers", {}))


def clean_player_name(name) -> str:
    """背番号などのカッコ表記を取り除き、純粋な選手名のみを取得"""
    if not name or pd.isna(name):
        return ""
    return str(name).split(" (")[0].strip()


def filter_today_df(df: pd.DataFrame, selected_date_str: str, opp_team: str = None) -> pd.DataFrame:
    """指定された日付（および対戦相手）でデータを絞り込む"""
    if df.empty or "日付" not in df.columns:
        return pd.DataFrame()
    mask = df["日付"].astype(str) == str(selected_date_str)
    if opp_team and "対戦相手" in df.columns:
        mask = mask & (df["対戦相手"].astype(str).str.strip() == str(opp_team).strip())
    return df[mask].copy()


def calculate_outs(df: pd.DataFrame) -> int:
    """データフレームから累積アウト数を計算"""
    if df.empty or "結果" not in df.columns:
        return 0
    single_out_list = [
        "三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)",
        "犠飛", "牽制死", "盗塁死", "走塁死", "野選", "振り逃げ三振"
    ]
    s_outs = len(df[df["結果"].isin(single_out_list)])
    d_outs = len(df[df["結果"] == "併殺打"]) * 2
    return s_outs + d_outs


def apply_dataframe_style(df: pd.DataFrame, highlight_func):
    """Pandasのバージョン差異(map / applymap)を吸収してスタイルを適用"""
    try:
        return df.style.map(highlight_func)
    except AttributeError:
        return df.style.applymap(highlight_func)


def highlight_batting(val):
    if isinstance(val, str):
        if "打点" in val:
            return "color: red; font-weight: bold;"
        elif any(hit in val for hit in ["単打", "二塁打", "三塁打", "本塁打"]):
            return "color: blue; font-weight: bold;"
    return ""


def highlight_pitching(val):
    if isinstance(val, str):
        if "💥失点" in val:
            return "color: red; font-weight: bold;"
        elif any(hit in val for hit in ["単打", "二塁打", "三塁打", "本塁打"]):
            return "color: blue; font-weight: bold;"
    return ""


def render_bso_indicator(outs: int, balls: int, strikes: int, pitch_count: int) -> str:
    """BSO（ボール・ストライク・アウト）および球数インジケーターのHTML生成"""
    out_circles = "".join([
        f'<span style="display:inline-block; width:22px; height:22px; border-radius:50%;'
        f' background-color:{"#ef4444" if i < outs else "#d1d5db"}; margin-right:5px;"></span>'
        for i in range(2)
    ])
    ball_circles = "".join([
        f'<span style="display:inline-block; width:22px; height:22px; border-radius:50%;'
        f' background-color:{"#22c55e" if i < balls else "#d1d5db"}; margin-right:5px;"></span>'
        for i in range(3)
    ])
    strike_circles = "".join([
        f'<span style="display:inline-block; width:22px; height:22px; border-radius:50%;'
        f' background-color:{"#eab308" if i < strikes else "#d1d5db"}; margin-right:5px;"></span>'
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


# --- 🏆 責任投手設定コンポーネント ---

def render_game_result_popover(
    df_pitching: pd.DataFrame,
    selected_date_str: str,
    match_type: str,
    ground_name: str,
    opp_team: str,
    ALL_PLAYERS: list,
    conn,
    ws_pitching: str,
    SPREADSHEET_URL: str,
    key_prefix: str = "pitching"
):
    """勝利・敗戦・セーブ・ホールド投手の一括設定ポップオーバーを描画"""
    opp_pitcher_options = []
    for i in range(20):
        pos = st.session_state.get(f"opp_sp_{i}")
        name = st.session_state.get(f"opp_sn_{i}")
        if pos in ["投", "投手", "P"] and name and name not in ["選手", "nan", "None", "", "未選択"]:
            opp_pitcher_options.append(name)
            
    dh_p = st.session_state.get("opp_sn_dh_pitcher")
    if dh_p and dh_p not in ["相手投手", "nan", "None", ""]:
        opp_pitcher_options.append(dh_p)

    today_p = filter_today_df(df_pitching, selected_date_str, opp_team)
    p_col = "投手名" if "投手名" in df_pitching.columns else "選手名"

    if not today_p.empty and p_col in today_p.columns:
        existing_p = today_p[p_col].dropna().astype(str).str.strip().tolist()
        opp_pitcher_options.extend([p for p in existing_p if p not in ALL_PLAYERS])

    default_opps = [f"相手投手{i}" for i in range(1, 10)]
    opp_pitcher_options = list(dict.fromkeys([p for p in opp_pitcher_options + default_opps if p and p not in ["nan", "None", ""]]))

    init_win, init_lose, init_save = "なし", "なし", "なし"
    init_holds = []
    init_opp_win, init_opp_lose, init_opp_save = "なし", "なし", "なし"
    init_opp_holds = []

    if not today_p.empty and "勝敗" in today_p.columns:
        for _, r in today_p.iterrows():
            p_name = str(r.get(p_col, "")).strip()
            dec = str(r.get("勝敗", "")).strip()
            if not p_name or dec in ["", "ー", "nan", "None"]:
                continue

            is_my_team = any(clean_player_name(p) == p_name or p == p_name for p in ALL_PLAYERS)

            if is_my_team:
                matched_p = next((p for p in ALL_PLAYERS if clean_player_name(p) == p_name or p == p_name), p_name)
                if dec in ["勝利", "勝", "○"]:
                    init_win = matched_p
                elif dec in ["敗戦", "敗", "●"]:
                    init_lose = matched_p
                elif dec in ["セーブ", "S"]:
                    init_save = matched_p
                elif dec in ["ホールド", "H"]:
                    if matched_p not in init_holds:
                        init_holds.append(matched_p)
            else:
                if dec in ["勝利", "勝", "○"]:
                    init_opp_win = p_name
                elif dec in ["敗戦", "敗", "●"]:
                    init_opp_lose = p_name
                elif dec in ["セーブ", "S"]:
                    init_opp_save = p_name
                elif dec in ["ホールド", "H"]:
                    if p_name not in init_opp_holds:
                        init_opp_holds.append(p_name)

    summary_parts = []
    if init_win != "なし":
        summary_parts.append(f"勝:{clean_player_name(init_win)}")
    if init_lose != "なし":
        summary_parts.append(f"敗:{clean_player_name(init_lose)}")
    if init_opp_win != "なし":
        summary_parts.append(f"相手勝:{init_opp_win}")
    if init_opp_lose != "なし":
        summary_parts.append(f"相手敗:{init_opp_lose}")

    summary_str = f" ({' / '.join(summary_parts)})" if summary_parts else ""

    k_win = f"{key_prefix}_dec_my_win"
    k_lose = f"{key_prefix}_dec_my_lose"
    k_save = f"{key_prefix}_dec_my_save"
    k_holds = f"{key_prefix}_dec_my_holds"

    k_opp_win = f"{key_prefix}_dec_opp_win"
    k_opp_lose = f"{key_prefix}_dec_opp_lose"
    k_opp_save = f"{key_prefix}_dec_opp_save"
    k_opp_holds = f"{key_prefix}_dec_opp_holds"
    k_btn_save = f"{key_prefix}_btn_save_dec_pills"

    with st.expander(f"🏆 責任投手（勝・敗・S・H）を一括設定{summary_str} 🔽", expanded=False):
        t_my, t_opp = st.tabs(["🏠 自チーム", f"⚾ 相手チーム ({opp_team})"])

        w_opts = ["なし"] + ALL_PLAYERS
        ow_opts = ["なし"] + opp_pitcher_options

        with t_my:
            st.markdown("##### 🏠 自チーム責任投手")
            c1, c2 = st.columns(2)
            
            with c1:
                cur_win = st.session_state.get(k_win, init_win if init_win in w_opts else "なし")
                lbl_win = f"🟢 勝: {clean_player_name(cur_win)} 🔽" if cur_win != "なし" else "勝利投手 (W) 選択 🔽"
                with st.popover(lbl_win, use_container_width=True):
                    st.markdown("##### 勝利投手 (W) を選択")
                    st.pills("勝利投手", w_opts, default=init_win if init_win in w_opts else "なし", format_func=local_fmt, key=k_win, label_visibility="collapsed")

                cur_save = st.session_state.get(k_save, init_save if init_save in w_opts else "なし")
                lbl_save = f"🟢 S: {clean_player_name(cur_save)} 🔽" if cur_save != "なし" else "セーブ投手 (S) 選択 🔽"
                with st.popover(lbl_save, use_container_width=True):
                    st.markdown("##### セーブ投手 (S) を選択")
                    st.pills("セーブ投手", w_opts, default=init_save if init_save in w_opts else "なし", format_func=local_fmt, key=k_save, label_visibility="collapsed")

            with c2:
                cur_lose = st.session_state.get(k_lose, init_lose if init_lose in w_opts else "なし")
                lbl_lose = f"🟢 敗: {clean_player_name(cur_lose)} 🔽" if cur_lose != "なし" else "敗戦投手 (L) 選択 🔽"
                with st.popover(lbl_lose, use_container_width=True):
                    st.markdown("##### 敗戦投手 (L) を選択")
                    st.pills("敗戦投手", w_opts, default=init_lose if init_lose in w_opts else "なし", format_func=local_fmt, key=k_lose, label_visibility="collapsed")

                cur_holds = st.session_state.get(k_holds, [h for h in init_holds if h in ALL_PLAYERS])
                holds_str = ", ".join([clean_player_name(h) for h in cur_holds]) if cur_holds else ""
                lbl_holds = f"🟢 H: {holds_str} 🔽" if cur_holds else "ホールド投手 (H) 選択 🔽"
                with st.popover(lbl_holds, use_container_width=True):
                    st.markdown("##### ホールド投手 (H) を選択（複数可）")
                    st.pills("ホールド投手", ALL_PLAYERS, selection_mode="multi", default=[h for h in init_holds if h in ALL_PLAYERS], format_func=local_fmt, key=k_holds, label_visibility="collapsed")

        with t_opp:
            st.markdown(f"##### ⚾ 相手チーム ({opp_team}) 責任投手")
            c1, c2 = st.columns(2)
            
            with c1:
                cur_opp_win = st.session_state.get(k_opp_win, init_opp_win if init_opp_win in ow_opts else "なし")
                lbl_opp_win = f"🟢 勝: {cur_opp_win} 🔽" if cur_opp_win != "なし" else "相手勝利投手 (W) 選択 🔽"
                with st.popover(lbl_opp_win, use_container_width=True):
                    st.markdown("##### 相手 勝利投手 (W) を選択")
                    st.pills("相手 勝利投手", ow_opts, default=init_opp_win if init_opp_win in ow_opts else "なし", key=k_opp_win, label_visibility="collapsed")

                cur_opp_save = st.session_state.get(k_opp_save, init_opp_save if init_opp_save in ow_opts else "なし")
                lbl_opp_save = f"🟢 S: {cur_opp_save} 🔽" if cur_opp_save != "なし" else "相手セーブ投手 (S) 選択 🔽"
                with st.popover(lbl_opp_save, use_container_width=True):
                    st.markdown("##### 相手 セーブ投手 (S) を選択")
                    st.pills("相手 セーブ投手", ow_opts, default=init_opp_save if init_opp_save in ow_opts else "なし", key=k_opp_save, label_visibility="collapsed")

            with c2:
                cur_opp_lose = st.session_state.get(k_opp_lose, init_opp_lose if init_opp_lose in ow_opts else "なし")
                lbl_opp_lose = f"🟢 敗: {cur_opp_lose} 🔽" if cur_opp_lose != "なし" else "相手敗戦投手 (L) 選択 🔽"
                with st.popover(lbl_opp_lose, use_container_width=True):
                    st.markdown("##### 相手 敗戦投手 (L) を選択")
                    st.pills("相手 敗戦投手", ow_opts, default=init_opp_lose if init_opp_lose in ow_opts else "なし", key=k_opp_lose, label_visibility="collapsed")

                cur_opp_holds = st.session_state.get(k_opp_holds, [h for h in init_opp_holds if h in opp_pitcher_options])
                opp_holds_str = ", ".join(cur_opp_holds) if cur_opp_holds else ""
                lbl_opp_holds = f"🟢 H: {opp_holds_str} 🔽" if cur_opp_holds else "相手ホールド投手 (H) 選択 🔽"
                with st.popover(lbl_opp_holds, use_container_width=True):
                    st.markdown("##### 相手 ホールド投手 (H) を選択（複数可）")
                    st.pills("相手 ホールド投手", opp_pitcher_options, selection_mode="multi", default=[h for h in init_opp_holds if h in opp_pitcher_options], key=k_opp_holds, label_visibility="collapsed")

        st.markdown("---")
        if st.button("💾 責任投手を一括保存", type="primary", use_container_width=True, key=k_btn_save):
            sel_win_val = st.session_state.get(k_win, "なし")
            sel_lose_val = st.session_state.get(k_lose, "なし")
            sel_save_val = st.session_state.get(k_save, "なし")
            sel_holds_val = st.session_state.get(k_holds, [])

            sel_opp_win_val = st.session_state.get(k_opp_win, "なし")
            sel_opp_lose_val = st.session_state.get(k_opp_lose, "なし")
            sel_opp_save_val = st.session_state.get(k_opp_save, "なし")
            sel_opp_holds_val = st.session_state.get(k_opp_holds, [])

            dec_map = {}
            if sel_win_val and sel_win_val != "なし":
                dec_map[clean_player_name(sel_win_val)] = "勝利"
            if sel_lose_val and sel_lose_val != "なし":
                dec_map[clean_player_name(sel_lose_val)] = "敗戦"
            if sel_save_val and sel_save_val != "なし":
                dec_map[clean_player_name(sel_save_val)] = "セーブ"
            for h in sel_holds_val:
                dec_map[clean_player_name(h)] = "ホールド"

            if sel_opp_win_val and sel_opp_win_val != "なし":
                dec_map[sel_opp_win_val.strip()] = "勝利"
            if sel_opp_lose_val and sel_opp_lose_val != "なし":
                dec_map[sel_opp_lose_val.strip()] = "敗戦"
            if sel_opp_save_val and sel_opp_save_val != "なし":
                dec_map[sel_opp_save_val.strip()] = "セーブ"
            for h in sel_opp_holds_val:
                dec_map[h.strip()] = "ホールド"

            updated_df = df_pitching.copy() if not df_pitching.empty else pd.DataFrame(columns=[
                "日付", "グラウンド", "対戦相手", "試合種別", "イニング", p_col, "結果", "失点", "自責点", "勝敗"
            ])

            if "日付" in updated_df.columns and "対戦相手" in updated_df.columns:
                today_mask = (
                    (updated_df["日付"].astype(str) == selected_date_str) &
                    (updated_df["対戦相手"].astype(str).str.strip() == str(opp_team).strip())
                )
                updated_df.loc[today_mask, "勝敗"] = "ー"

                for p_name, dec_val in dec_map.items():
                    p_mask = today_mask & (updated_df[p_col].astype(str).str.strip() == p_name)
                    if p_mask.any():
                        updated_df.loc[p_mask, "勝敗"] = dec_val
                    else:
                        new_row = {
                            "日付": selected_date_str,
                            "グラウンド": ground_name,
                            "対戦相手": opp_team,
                            "試合種別": match_type,
                            "イニング": "試合終了",
                            p_col: p_name,
                            "結果": "ー",
                            "失点": 0,
                            "自責点": 0,
                            "勝敗": dec_val
                        }
                        updated_df = pd.concat([updated_df, pd.DataFrame([new_row])], ignore_index=True)

            save_cols = [c for c in updated_df.columns if c not in ["_date_str", "Year", "スコアラー"]]
            try:
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=updated_df[save_cols])
                st.cache_data.clear()
                st.success("✅ 責任投手情報を保存しました！")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"保存失敗: {e}")


# --- メインページ表示関数 ---

def show_pitching_page(df_batting: pd.DataFrame, df_pitching: pd.DataFrame, selected_date_str: str, match_type: str, ground_name: str, opp_team: str, kagura_order: str):
    ALL_PLAYERS, PLAYER_NUMBERS = get_active_players()
    st.session_state["shared_player_numbers"] = PLAYER_NUMBERS

    ws_pitching = "投手成績"
    is_kagura_top = (kagura_order == "先攻 (表)")
    pos_options = [p for p in ALL_POSITIONS if p != ""] + ["未選択"]

    conn = st.connection("gsheets", type=GSheetsConnection)

    today_batting_df = filter_today_df(df_batting, selected_date_str)
    today_pitching_df = filter_today_df(df_pitching, selected_date_str)

    scoreboard_df = (
        today_batting_df[today_batting_df["イニング"] != "まとめ入力"]
        if not today_batting_df.empty and "イニング" in today_batting_df.columns
        else df_batting
    )
    render_scoreboard(scoreboard_df, today_pitching_df, selected_date_str, match_type, ground_name, opp_team, is_kagura_top)

    render_game_result_popover(df_pitching, selected_date_str, match_type, ground_name, opp_team, ALL_PLAYERS, conn, ws_pitching, SPREADSHEET_URL)

    # 試合変更時の状態リセット
    current_match_id = f"{selected_date_str}_{opp_team}_{match_type}"
    if st.session_state.get("last_p_match_id") != current_match_id:
        keys_to_reset = [
            "p_det_inn", "opp_batter_index", "pitching_quick_sr", "pitching_quick_sd",
            "pitching_quick_run", "pitching_quick_er", "p_b_count", "p_s_count", "p_f_count",
            "p_pitch_count", "p_persistent_runners", "p_runner_1b", "p_runner_2b",
            "p_runner_3b", "p_runner_1b_res", "p_runner_2b_res", "p_runner_3b_res",
            "p_runner_1b_fielder", "p_runner_2b_fielder", "p_runner_3b_fielder", "opp_sn_dh_pitcher"
        ]
        for k in list(st.session_state.keys()):
            if k in keys_to_reset or k.startswith("sync_") or k.startswith("opp_sp_") or k.startswith("opp_sn_") or k.startswith("pill_opp_"):
                del st.session_state[k]
        st.session_state["last_p_match_id"] = current_match_id

    if "p_persistent_runners" not in st.session_state:
        st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}

    p_inning_suffix = "裏" if is_kagura_top else "表"

    if "opp_batter_index" not in st.session_state:
        st.session_state["opp_batter_index"] = 1
    if "opp_batter_count" not in st.session_state:
        st.session_state["opp_batter_count"] = 9
    if "p_det_inn" not in st.session_state:
        st.session_state["p_det_inn"] = f"1回{p_inning_suffix}"

    for i in range(20):
        sn_k = f"opp_sn_{i}"
        pill_k = f"pill_{sn_k}"
        default_val = f"選手{i + 1}"

        if st.session_state.get(sn_k) in [None, "", "選手", "未選択", "nan", "None"]:
            st.session_state[sn_k] = default_val
        if st.session_state.get(pill_k) in [None, "", "選手", "未選択", "nan", "None"]:
            st.session_state[pill_k] = default_val

    sync_key = f"sync_{selected_date_str}"
    if sync_key not in st.session_state:
        if not today_pitching_df.empty:
            if "種別" in today_pitching_df.columns:
                history_details = today_pitching_df[
                    today_pitching_df["種別"].astype(str).str.contains("詳細", na=False) |
                    (~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"]) & today_pitching_df["打順"].notna())
                ]
            else:
                history_details = today_pitching_df[
                    ~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"]) & today_pitching_df["打順"].notna()
                ]
        else:
            history_details = pd.DataFrame()

        if not history_details.empty:
            last_rec = history_details.iloc[-1]
            st.session_state["p_det_inn"] = last_rec.get("イニング", f"1回{p_inning_suffix}")
            try:
                last_order = last_rec.get("打順")
                if pd.notna(last_order) and str(last_order).strip() not in ["", "nan"]:
                    last_idx = int(float(last_order))
                elif "種別" in last_rec and ":" in str(last_rec.get("種別", "")):
                    last_idx = int(str(last_rec.get("種別", "")).split(":")[1].replace("番打者", ""))
                else:
                    last_idx = 1
                st.session_state["opp_batter_index"] = (last_idx % st.session_state.get("opp_batter_count", 9)) + 1
            except (IndexError, ValueError):
                pass

            if not st.session_state.get("scorer_name"):
                valid_scorer_df = (
                    today_pitching_df[
                        (today_pitching_df["スコアラー"].astype(str).str.strip() != "") &
                        (today_pitching_df["スコアラー"].astype(str).str.strip() != "0") &
                        (today_pitching_df["スコアラー"].astype(str).str.strip() != "nan")
                    ]
                    if not today_pitching_df.empty and "スコアラー" in today_pitching_df.columns
                    else pd.DataFrame()
                )
                if not valid_scorer_df.empty:
                    st.session_state["scorer_name"] = valid_scorer_df.iloc[-1]["スコアラー"]

            st.session_state[sync_key] = True
        else:
            st.session_state["p_det_inn"] = f"1回{p_inning_suffix}"
            st.session_state["opp_batter_index"] = 1
            st.session_state[sync_key] = True

    # フォームクリア処理
    if st.session_state.get("needs_pitching_form_clear"):
        st.session_state["pitching_quick_sr"] = None
        st.session_state["pitching_quick_sd"] = []
        st.session_state["pitching_quick_run"] = 0
        st.session_state["pitching_quick_er"] = 0
        st.session_state["p_b_count"] = 0
        st.session_state["p_s_count"] = 0
        st.session_state["p_f_count"] = 0
        st.session_state["p_pitch_count"] = 0
        for b_key in ["1b", "2b", "3b"]:
            st.session_state[f"p_runner_{b_key}_res"] = None
            st.session_state[f"p_runner_{b_key}_fielder"] = None
            st.session_state[f"p_runner_{b_key}"] = None
        st.session_state["needs_pitching_form_clear"] = False

    inn_options = [f"{i}回{p_inning_suffix}" for i in range(1, 10)] + [f"延長{p_inning_suffix}"]
    current_inn_val = st.session_state.get("p_det_inn", f"1回{p_inning_suffix}")

    p_inn_df_check = (
        today_pitching_df[today_pitching_df["イニング"] == current_inn_val]
        if not today_pitching_df.empty and "イニング" in today_pitching_df.columns
        else pd.DataFrame()
    )
    current_outs_total = calculate_outs(p_inn_df_check)

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
                    st.session_state[f"p_runner_{b_key}"] = None
        except ValueError:
            pass

    # --- 投球入力ヘッダー・カウント入力 ---
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
            p_inn_df_disp = (
                today_pitching_df[today_pitching_df["イニング"] == current_inn]
                if not today_pitching_df.empty and "イニング" in today_pitching_df.columns
                else pd.DataFrame()
            )
            disp_outs = calculate_outs(p_inn_df_disp) % 3

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

            f_cnt = st.session_state.get("p_f_count", 0)

            with b_col3:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#6b7280;'>⚪ ファール</div>", unsafe_allow_html=True)
                fc1, fc2 = st.columns(2)
                with fc1:
                    if st.button("➖", key="btn_p_f_sub", use_container_width=True, disabled=(f_cnt <= 0)):
                        st.session_state["p_pitch_count"] = max(0, p_cnt - 1)
                        st.session_state["p_f_count"] = max(0, f_cnt - 1)
                        st.rerun()
                with fc2:
                    if st.button("➕", key="btn_p_f_add", use_container_width=True):
                        st.session_state["p_pitch_count"] = p_cnt + 1
                        st.session_state["p_f_count"] = f_cnt + 1
                        if s_cnt < 2:
                            st.session_state["p_s_count"] = s_cnt + 1
                        st.rerun()

            with b_col4:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#374151;'>リセット</div>", unsafe_allow_html=True)
                if st.button("🔄", key="btn_p_reset_bso", use_container_width=True):
                    st.session_state["p_b_count"] = 0
                    st.session_state["p_s_count"] = 0
                    st.session_state["p_f_count"] = 0
                    st.session_state["p_pitch_count"] = 0
                    st.rerun()

    st.divider()

    # --- 打順・結果選択 ---
    c_mid1, c_mid2, c_mid3 = st.columns([1.0, 1.0, 3.5])
    with c_mid1:
        st.session_state["opp_batter_count"] = st.number_input(
            "相手打順人数", 1, 20, value=st.session_state["opp_batter_count"]
        )
    with c_mid2:
        st.session_state["opp_batter_index"] = st.number_input(
            "現在の打順", 1, st.session_state["opp_batter_count"], value=st.session_state["opp_batter_index"]
        )

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
            res_options = [
                "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打",
                "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "振り逃げ三振",
                "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "ボーク", "暴投", "捕逸",
                "牽制死", "盗塁死", "盗塁", "走塁死"
            ]
            st.pills("投球結果", res_options, key="pitching_quick_sr", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚾ 打球方向を選択（複数選択可・最大2つ）")
            dir_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
            st.pills("打球方向", dir_options, selection_mode="multi", key="pitching_quick_sd", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚾ 失点を選択 (0〜4)")
            run_options = [0, 1, 2, 3, 4]
            st.pills("失点", run_options, key="pitching_quick_run", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚾ 自責点を選択 (0〜4)")
            er_options = [0, 1, 2, 3, 4]
            st.pills("自責点", er_options, key="pitching_quick_er", label_visibility="collapsed")

            st.markdown("---")
            if st.button("🔄 入力をすべてクリア", use_container_width=True, key="pitching_all_clear_btn"):
                st.session_state["needs_pitching_form_clear"] = True
                st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
                st.rerun()

    st.divider()

    # --- 走者状況設定 ---
    opp_count = st.session_state.get("opp_batter_count", 9)
    curr_opp_idx = st.session_state.get("opp_batter_index", 1)

    default_opp_players = [f"選手{i}" for i in range(1, 21)]
    opp_player_options = list(default_opp_players)

    if "fetched_opp_players" in st.session_state:
        df_opp_p = st.session_state["fetched_opp_players"]
        p_col_opp = "打者名" if "打者名" in df_opp_p.columns else "選手名"
        if isinstance(df_opp_p, pd.DataFrame) and not df_opp_p.empty and p_col_opp in df_opp_p.columns:
            opp_player_options.extend(df_opp_p[p_col_opp].dropna().astype(str).str.strip().tolist())

    if "fetched_opp_order" in st.session_state:
        df_opp_o = st.session_state["fetched_opp_order"]
        o_col_opp = "打者名" if "打者名" in df_opp_o.columns else "選手名"
        if isinstance(df_opp_o, pd.DataFrame) and not df_opp_o.empty and o_col_opp in df_opp_o.columns:
            opp_player_options.extend(df_opp_o[o_col_opp].dropna().astype(str).str.strip().tolist())

    for k, v in list(st.session_state.items()):
        if k.startswith("opp_sn_") and v and str(v) not in ["None", "nan", "選手"]:
            opp_player_options.append(str(v))

    opp_player_options = list(dict.fromkeys([p for p in opp_player_options if p and p not in ["nan", "選手"]]))
    runner_options = ["なし"] + opp_player_options

    st.markdown("##### 🏃 走者状況")

    p_runners = st.session_state.get("p_persistent_runners", {"1b": None, "2b": None, "3b": None})

    for b_key in ["1b", "2b", "3b"]:
        sel_key = f"p_runner_{b_key}"
        if sel_key not in st.session_state or st.session_state[sel_key] is None:
            val = p_runners.get(b_key)
            st.session_state[sel_key] = val if val else "なし"

    r3_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死"]
    r2_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死", "進塁1"]
    r1_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死", "進塁1", "進塁2"]
    out_fielder_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

    r_cols = st.columns(3)

    with r_cols[0]:
        st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>3塁</div>", unsafe_allow_html=True)

        r3_val = st.session_state.get("p_runner_3b", "なし")
        r3_label = f"🟢 {r3_val} 🔽" if r3_val and r3_val != "なし" else "走者選択 🔽"
        with st.popover(r3_label, use_container_width=True):
            st.markdown("##### 3塁走者を選択")
            st.pills("3塁走者", runner_options, key="p_runner_3b", label_visibility="collapsed")

        r3_res = st.session_state.get("p_runner_3b_res")
        r3_f = st.session_state.get("p_runner_3b_fielder")
        r3_btn = (
            f"🟢 {r3_res}({r3_f}) 🔽" if (r3_res in ["走塁死", "盗塁死", "牽制死"] and r3_f)
            else (f"🟢 {r3_res} 🔽" if r3_res else "走塁結果 🔽")
        )
        with st.popover(r3_btn, use_container_width=True):
            st.markdown("##### 3塁 走塁結果を選択")
            cur_r3_res = st.pills("3塁結果ピル", r3_res_options, key="p_runner_3b_res", label_visibility="collapsed")
            if cur_r3_res in ["走塁死", "盗塁死", "牽制死"]:
                st.markdown("---")
                st.markdown("##### 🎯 処理野手（補殺）を選択")
                st.pills("3塁処理野手ピル", out_fielder_options, key="p_runner_3b_fielder", label_visibility="collapsed")

    with r_cols[1]:
        st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>2塁</div>", unsafe_allow_html=True)

        r2_val = st.session_state.get("p_runner_2b", "なし")
        r2_label = f"🟢 {r2_val} 🔽" if r2_val and r2_val != "なし" else "走者選択 🔽"
        with st.popover(r2_label, use_container_width=True):
            st.markdown("##### 2塁走者を選択")
            st.pills("2塁走者", runner_options, key="p_runner_2b", label_visibility="collapsed")

        r2_res = st.session_state.get("p_runner_2b_res")
        r2_f = st.session_state.get("p_runner_2b_fielder")
        r2_btn = (
            f"🟢 {r2_res}({r2_f}) 🔽" if (r2_res in ["走塁死", "盗塁死", "牽制死"] and r2_f)
            else (f"🟢 {r2_res} 🔽" if r2_res else "走塁結果 🔽")
        )
        with st.popover(r2_btn, use_container_width=True):
            st.markdown("##### 2塁 走塁結果を選択")
            cur_r2_res = st.pills("2塁結果ピル", r2_res_options, key="p_runner_2b_res", label_visibility="collapsed")
            if cur_r2_res in ["走塁死", "盗塁死", "牽制死"]:
                st.markdown("---")
                st.markdown("##### 🎯 処理野手（補殺）を選択")
                st.pills("2塁処理野手ピル", out_fielder_options, key="p_runner_2b_fielder", label_visibility="collapsed")

    with r_cols[2]:
        st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>1塁</div>", unsafe_allow_html=True)

        r1_val = st.session_state.get("p_runner_1b", "なし")
        r1_label = f"🟢 {r1_val} 🔽" if r1_val and r1_val != "なし" else "走者選択 🔽"
        with st.popover(r1_label, use_container_width=True):
            st.markdown("##### 1塁走者を選択")
            st.pills("1塁走者", runner_options, key="p_runner_1b", label_visibility="collapsed")

        r1_res = st.session_state.get("p_runner_1b_res")
        r1_f = st.session_state.get("p_runner_1b_fielder")
        r1_btn = (
            f"🟢 {r1_res}({r1_f}) 🔽" if (r1_res in ["走塁死", "盗塁死", "牽制死"] and r1_f)
            else (f"🟢 {r1_res} 🔽" if r1_res else "走塁結果 🔽")
        )
        with st.popover(r1_btn, use_container_width=True):
            st.markdown("##### 1塁 走塁結果を選択")
            cur_r1_res = st.pills("1塁結果ピル", r1_res_options, key="p_runner_1b_res", label_visibility="collapsed")
            if cur_r1_res in ["走塁死", "盗塁死", "牽制死"]:
                st.markdown("---")
                st.markdown("##### 🎯 処理野手（補殺）を選択")
                st.pills("1塁処理野手ピル", out_fielder_options, key="p_runner_1b_fielder", label_visibility="collapsed")

    st.session_state["p_persistent_runners"] = {
        "1b": st.session_state.get("p_runner_1b") if st.session_state.get("p_runner_1b") not in [None, "なし", ""] else None,
        "2b": st.session_state.get("p_runner_2b") if st.session_state.get("p_runner_2b") not in [None, "なし", ""] else None,
        "3b": st.session_state.get("p_runner_3b") if st.session_state.get("p_runner_3b") not in [None, "なし", ""] else None,
    }

    st.divider()

    # --- 相手打順リスト＆履歴表示 ---
    if "fetched_opp_order" in st.session_state:
        df_opp_o = st.session_state["fetched_opp_order"]
        if isinstance(df_opp_o, pd.DataFrame) and not df_opp_o.empty:
            if len(df_opp_o) >= 9:
                st.session_state["opp_batter_count"] = max(st.session_state.get("opp_batter_count", 9), len(df_opp_o))
            for idx, row in df_opp_o.iterrows():
                sn_k = f"opp_sn_{idx}"
                sp_k = f"opp_sp_{idx}"
                s_name = str(row.get("打者名", row.get("選手名", ""))).strip()
                s_pos = str(row.get("守備位置", row.get("位置", ""))).strip()

                if s_name and s_name not in ["nan", "None", "", "選手"]:
                    cur_val = st.session_state.get(sn_k)
                    if not cur_val or cur_val in ["選手", ""] or (isinstance(cur_val, str) and cur_val.startswith("選手")):
                        st.session_state[sn_k] = s_name
                if s_pos and s_pos not in ["nan", "None", ""]:
                    if st.session_state.get(sp_k) in [None, "未選択", ""]:
                        st.session_state[sp_k] = s_pos

    RES_SHORT_MAP = {
        "本塁打": "本", "三塁打": "三", "二塁打": "二", "単打": "安", "三振": "振",
        "凡退(ゴロ)": "ゴ", "凡退(フライ)": "飛", "四球": "球", "死球": "死", "犠打(ゴロ)": "犠",
        "犠打(フライ)": "犠", "犠飛": "犠飛", "失策(ゴロ)": "失", "失策(フライ)": "失",
        "野選": "野", "併殺打": "併", "振り逃げ三振": "逃", "打撃妨害": "妨",
    }

    opp_history_dict = {}
    if not today_pitching_df.empty:
        detail_df = today_pitching_df[
            ~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"])
        ].copy()

        for b_num in range(1, opp_count + 1):
            if "打順" in detail_df.columns:
                rows = detail_df[pd.to_numeric(detail_df["打順"], errors="coerce") == b_num]
            elif "種別" in detail_df.columns:
                rows = detail_df[detail_df["種別"] == f"詳細:{b_num}番打者"]
            else:
                rows = pd.DataFrame()

            if rows.empty:
                continue

            history_html = []
            count = 0
            stolen_base_count = 0
            total_runs = 0

            for _, row in rows.iterrows():
                res = str(row.get("結果", ""))
                runs_val = pd.to_numeric(row.get("失点", 0), errors="coerce")
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

                disp_text = f"{p_dir}{res_short}・{r_val}" if r_val > 0 else f"{p_dir}{res_short}"

                color_style = ""
                is_hit = res in ["単打", "二塁打", "三塁打", "本塁打"]

                if is_hit or r_val > 0:
                    color_style = "color: red;" if r_val > 0 else "color: blue;"

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
        pill_name_key = f"pill_{name_key}"

        cur_pos = st.session_state.get(pos_key)
        if not cur_pos or cur_pos not in pos_options:
            cur_pos = "未選択"
            st.session_state[pos_key] = "未選択"

        default_name = f"選手{order_num}"
        cur_name = st.session_state.get(name_key)

        if not cur_name or cur_name in ["選手", "未選択", "nan", "None", ""] or cur_name not in opp_player_options:
            cur_name = default_name
            st.session_state[name_key] = default_name
            st.session_state[pill_name_key] = default_name

        is_current = (order_num == curr_opp_idx)

        with st.container(border=True):
            c_row = st.columns([0.8, 2.5, 3.5, 5.2])

            with c_row[0]:
                prefix = "📍 " if is_current else ""
                st.markdown(
                    f"<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;"
                    f" color:{'#22c55e' if is_current else '#333'};'>{prefix}{order_num}</div>",
                    unsafe_allow_html=True,
                )

            with c_row[1]:
                pos_btn_label = f"🟢 {cur_pos} 🔽" if cur_pos != "未選択" else "未選択 🔽"
                with st.popover(pos_btn_label, use_container_width=True):
                    st.markdown(f"##### {order_num}番 守備位置を選択")
                    selected_pos = st.pills(
                        f"相手守備 {i}",
                        pos_options,
                        default=cur_pos,
                        key=f"pill_{pos_key}",
                        label_visibility="collapsed",
                    )
                    if selected_pos and selected_pos != cur_pos:
                        st.session_state[pos_key] = selected_pos

            with c_row[2]:
                name_btn_label = f"🟢 {cur_name} 🔽" if cur_name != default_name else f"{default_name} 🔽"
                with st.popover(name_btn_label, use_container_width=True):
                    st.markdown(f"##### {order_num}番 選手を選択")
                    selected_name = st.pills(
                        f"相手選手 {i}",
                        opp_player_options,
                        default=cur_name,
                        key=pill_name_key,
                        label_visibility="collapsed",
                    )
                    if selected_name and selected_name != cur_name:
                        st.session_state[name_key] = selected_name

            with c_row[3]:
                history_text = opp_history_dict.get(order_num, "")
                st.markdown(
                    f"<div style='font-size:15px; line-height:1.4; padding-top:6px; color:#444; overflow-x:auto; white-space:nowrap;'>{history_text}</div>",
                    unsafe_allow_html=True,
                )

    dh_player_options = list(dict.fromkeys(["相手投手"] + opp_player_options))
    cur_opp_dh_p = st.session_state.get("opp_sn_dh_pitcher")
    if not cur_opp_dh_p or cur_opp_dh_p not in dh_player_options:
        cur_opp_dh_p = "相手投手"
        st.session_state["opp_sn_dh_pitcher"] = "相手投手"

    with st.container(border=True):
        c_dh_row = st.columns([0.8, 2.5, 3.5, 5.2])
        with c_dh_row[0]:
            st.markdown("<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;'>投</div>", unsafe_allow_html=True)
        with c_dh_row[1]:
            st.markdown("<div style='text-align:center; font-size:14px; font-weight:bold; padding-top:10px; color:#4f46e5;'>🟢 投 (DH時)</div>", unsafe_allow_html=True)
        with c_dh_row[2]:
            name_btn_label = f"🟢 {cur_opp_dh_p} 🔽" if cur_opp_dh_p != "相手投手" else "相手投手 (DH時) 🔽"
            with st.popover(name_btn_label, use_container_width=True):
                st.markdown("##### ⚾ 相手投手を選択")
                selected_dh_p = st.pills(
                    "相手DH投手ピル",
                    dh_player_options,
                    default=cur_opp_dh_p,
                    key="pill_opp_sn_dh_pitcher",
                    label_visibility="collapsed",
                )
                if selected_dh_p and selected_dh_p != cur_opp_dh_p:
                    st.session_state["opp_sn_dh_pitcher"] = selected_dh_p
        with c_dh_row[3]:
            st.markdown("<div style='font-size:13px; color:#6b7280; padding-top:10px;'>※ DH制で打順に入らない相手投手を設定</div>", unsafe_allow_html=True)

    st.divider()
    col_disp1, col_disp2, col_disp3 = st.columns([2.0, 1.0, 1.0])
    with col_disp1:
        st.markdown(
            f"<div style='font-weight:bold; font-size:16px; line-height:2.4;'>👥 相手打順の表示人数: {st.session_state.get('opp_batter_count', 9)}人</div>",
            unsafe_allow_html=True,
        )
    with col_disp2:
        if st.button("➖ 減らす", key="btn_opp_dec", use_container_width=True):
            if st.session_state["opp_batter_count"] > 9:
                st.session_state["opp_batter_count"] -= 1
                idx = st.session_state["opp_batter_count"]
                for k in [f"opp_sn_{idx}", f"opp_sp_{idx}", f"pill_opp_sn_{idx}", f"pill_opp_sp_{idx}"]:
                    st.session_state.pop(k, None)
                st.rerun()
    with col_disp3:
        if st.button("➕ 追加 (最大20)", key="btn_opp_inc", use_container_width=True):
            if st.session_state["opp_batter_count"] < 20:
                st.session_state["opp_batter_count"] += 1
                st.rerun()

    st.divider()

    # --- 登録保存処理 ---
    if submit_detail:
        final_ground = ground_name or st.session_state.get("ground_name", "")
        final_opp = opp_team or st.session_state.get("opp_team", "")
        final_match_type = match_type or st.session_state.get("match_type", "")

        if not today_pitching_df.empty:
            if not final_ground and "グラウンド" in today_pitching_df.columns:
                valid_g = today_pitching_df["グラウンド"].dropna().astype(str).str.strip()
                valid_g = valid_g[~valid_g.isin(["", "nan", "None"])]
                if not valid_g.empty:
                    final_ground = valid_g.iloc[-1]
            if not final_opp and "対戦相手" in today_pitching_df.columns:
                valid_o = today_pitching_df["対戦相手"].dropna().astype(str).str.strip()
                valid_o = valid_o[~valid_o.isin(["", "nan", "None"])]
                if not valid_o.empty:
                    final_opp = valid_o.iloc[-1]
            if not final_match_type and "試合種別" in today_pitching_df.columns:
                valid_m = today_pitching_df["試合種別"].dropna().astype(str).str.strip()
                valid_m = valid_m[~valid_m.isin(["", "nan", "None"])]
                if not valid_m.empty:
                    final_match_type = valid_m.iloc[-1]

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
            if not s1 or not s2:
                return False
            if s1 == s2:
                return True
            for aliases in POS_ALIASES.values():
                if s1 in aliases and s2 in aliases:
                    return True
            return False

        def get_player_by_position(target_pos):
            if not target_pos:
                return ""

            for dict_key in ["shared_lineup", "lineup_states", "saved_lineup"]:
                data = st.session_state.get(dict_key, {})
                if isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, dict):
                            p_pos = v.get("pos", "")
                            p_name = v.get("name", "")
                            if p_pos and p_name and is_same_pos(p_pos, target_pos):
                                clean_n = clean_player_name(p_name)
                                if clean_n and clean_n not in ["nan", "None", "", "－"]:
                                    return clean_n
                    for i in range(20):
                        p_pos = data.get(f"pos_{i}", "")
                        p_name = data.get(f"name_{i}", "")
                        if p_pos and p_name and is_same_pos(p_pos, target_pos):
                            clean_n = clean_player_name(p_name)
                            if clean_n and clean_n not in ["nan", "None", "", "－"]:
                                return clean_n

            display_count = st.session_state.get("display_order_count", 20)
            for i in range(display_count):
                p_pos = st.session_state.get(f"sp{i}", "")
                p_name = st.session_state.get(f"sn{i}", "")
                if p_pos and p_name and is_same_pos(p_pos, target_pos):
                    clean_n = clean_player_name(p_name)
                    if clean_n and clean_n not in ["nan", "None", "", "－"]:
                        return clean_n

            if not today_batting_df.empty:
                b_col_p = "打者名" if "打者名" in today_batting_df.columns else "選手名"
                for col in ["守備位置", "位置"]:
                    if col in today_batting_df.columns and b_col_p in today_batting_df.columns:
                        matched = today_batting_df[
                            today_batting_df[col].astype(str).apply(lambda x: is_same_pos(x, target_pos))
                        ]
                        if not matched.empty:
                            for name_val in reversed(matched[b_col_p].dropna().tolist()):
                                clean_n = clean_player_name(name_val)
                                if clean_n and clean_n not in ["nan", "None", "", "－"]:
                                    return clean_n

            if is_same_pos(target_pos, "投"):
                dh_p = st.session_state.get("sn_dh_pitcher", "")
                if dh_p:
                    clean_n = clean_player_name(dh_p)
                    if clean_n and clean_n not in ["nan", "None", "", "－"]:
                        return clean_n

            return ""

        def_pitcher = get_player_by_position("投")
        if not def_pitcher:
            def_pitcher = str(st.session_state.get("shared_starting_pitcher", ""))

        matched_p = next(
            (p for p in ALL_PLAYERS if clean_player_name(p) == def_pitcher.strip() or p == def_pitcher),
            None,
        )
        input_name = matched_p if matched_p else (def_pitcher if def_pitcher else "不明")

        def_catcher = get_player_by_position("捕")
        matched_c = next(
            (p for p in ALL_PLAYERS if clean_player_name(p) == def_catcher.strip() or p == def_catcher),
            None,
        )
        target_catcher_disp = matched_c if matched_c else (def_catcher if def_catcher else "不明")

        p_res = st.session_state.get("pitching_quick_sr")
        target_fielder_pos_list = st.session_state.get("pitching_quick_sd", [])

        p_run = st.session_state.get("pitching_quick_run", 0) or 0
        p_er = st.session_state.get("pitching_quick_er", 0) or 0

        require_dir_results = [
            "凡退(ゴロ)", "凡退(フライ)", "失策(ゴロ)", "失策(フライ)",
            "併殺打", "犠打(ゴロ)", "犠打(フライ)", "野選"
        ]

        cur_1b_runner_name = st.session_state.get("p_runner_1b")
        cur_2b_runner_name = st.session_state.get("p_runner_2b")
        cur_3b_runner_name = st.session_state.get("p_runner_3b")

        cur_1b = cur_1b_runner_name not in [None, "なし", ""]
        cur_2b = cur_2b_runner_name not in [None, "なし", ""]
        cur_3b = cur_3b_runner_name not in [None, "なし", ""]

        res_1b = st.session_state.get("p_runner_1b_res")
        res_2b = st.session_state.get("p_runner_2b_res")
        res_3b = st.session_state.get("p_runner_3b_res")

        b_to_1b_results = ["単打", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]
        b_to_2b_results = ["二塁打"]
        b_to_3b_results = ["三塁打"]

        if not p_res and not (res_1b or res_2b or res_3b):
            st.session_state["pitching_error_msg"] = "⚠️ 投球結果または走塁結果を選択してください。"
            st.rerun()
        elif p_res and p_res in require_dir_results and not target_fielder_pos_list:
            st.session_state["pitching_error_msg"] = f"⚠️ 「{p_res}」を登録するには、打球方向を選択してください。"
            st.rerun()
        elif p_res == "本塁打" and p_run == 0:
            st.session_state["pitching_error_msg"] = "⚠️ 本塁打は失点1以上必須です。"
            st.rerun()
        elif cur_1b and p_res in b_to_1b_results and not res_1b:
            st.session_state["pitching_error_msg"] = "⚠️ 1塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        elif cur_2b and p_res in b_to_2b_results and not res_2b:
            st.session_state["pitching_error_msg"] = "⚠️ 2塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        elif cur_3b and p_res in b_to_3b_results and not res_3b:
            st.session_state["pitching_error_msg"] = "⚠️ 3塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        else:
            target_pitcher_name = clean_player_name(input_name)
            batter_idx_int = st.session_state.get("opp_batter_index", 1)

            default_b_name = f"選手{batter_idx_int}"
            raw_batter_name = st.session_state.get(f"opp_sn_{batter_idx_int - 1}", default_b_name)
            current_batter_name = raw_batter_name if raw_batter_name not in ["None", "nan", ""] else default_b_name

            # 🏃‍♂️ 投球開始時点での走者状況判定
            if cur_1b and cur_2b and cur_3b:
                runner_status = "満塁"
            elif cur_2b or cur_3b:
                runner_status = "得点圏"
            elif cur_1b:
                runner_status = "ランナー1塁"
            else:
                runner_status = "ランナーなし"

            records_to_save = []
            add_outs_total = 0

            if p_res:
                target_fielder_pos_str = "-".join(target_fielder_pos_list)

                fielder_display = ""
                if target_fielder_pos_list:
                    name_parts = [get_player_by_position(pos) or f"({pos})" for pos in target_fielder_pos_list]
                    fielder_display = "-".join(name_parts)

                add_outs = 0
                if p_res == "併殺打":
                    add_outs = 2
                elif p_res in [
                    "三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)",
                    "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"
                ]:
                    add_outs = 1

                if p_res in ["盗塁", "盗塁死"]:
                    target_fielder_pos_str = "捕"
                    fielder_display = clean_player_name(target_catcher_disp) if target_catcher_disp else ""

                s_cnt_val = st.session_state.get("p_s_count", 0)
                f_cnt_val = st.session_state.get("p_f_count", 0)
                b_cnt_val = st.session_state.get("p_b_count", 0)

                final_strike_count = s_cnt_val + f_cnt_val
                final_ball_count = b_cnt_val

                if p_res in ["四球", "死球"]:
                    final_ball_count += 1
                elif p_res:
                    final_strike_count += 1

                final_pitch_count = final_ball_count + final_strike_count

                rec = {
                    "日付": selected_date_str,
                    "グラウンド": final_ground,
                    "対戦相手": final_opp,
                    "試合種別": final_match_type,
                    "イニング": current_inn,
                    "投手名": target_pitcher_name,
                    "打順": batter_idx_int,
                    "打者名": current_batter_name,
                    "守備位置": target_fielder_pos_str,
                    "打球方向": target_fielder_pos_str,
                    "処理野手": fielder_display,
                    "結果": p_res,
                    "失点": p_run,
                    "自責点": p_er,
                    "勝敗": "ー",
                    "球数": final_pitch_count,
                    "ストライク": final_strike_count,
                    "ファールボール": f_cnt_val,
                    "ボール": b_cnt_val,
                    "ランナー状況": runner_status
                }
                records_to_save.append(rec)
                add_outs_total += add_outs

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
                        "投手名": target_pitcher_name,
                        "打順": batter_idx_int,
                        "打者名": current_batter_name,
                        "守備位置": r_f if r_f else "ー",
                        "打球方向": r_f if r_f else "ー",
                        "処理野手": fielder_disp,
                        "結果": r_res,
                        "失点": r_run if not p_res else 0,
                        "自責点": r_run if not p_res else 0,
                        "勝敗": "ー",
                        "ストライク": 0,
                        "ボール": 0,
                    }
                    records_to_save.append(runner_rec)
                    add_outs_total += r_outs

            if records_to_save:
                updated_p_df = pd.concat([df_pitching, pd.DataFrame(records_to_save)], ignore_index=True)
                save_cols = [c for c in updated_p_df.columns if c not in ["_date_str", "Year", "スコアラー"]]
                conn.update(spreadsheet=SPREADSHEET_URL, worksheet=ws_pitching, data=updated_p_df[save_cols])
                st.cache_data.clear()

            non_batter_events = ["盗塁", "盗塁死", "牽制死", "暴投", "捕逸", "ボーク", "走塁死"]
            if p_res and p_res not in non_batter_events:
                st.session_state["opp_batter_index"] = (
                    st.session_state["opp_batter_index"] % st.session_state["opp_batter_count"]
                ) + 1

            p_inn_df = (
                today_pitching_df[today_pitching_df["イニング"] == current_inn]
                if not today_pitching_df.empty and "イニング" in today_pitching_df.columns
                else pd.DataFrame()
            )
            existing_outs = calculate_outs(p_inn_df)
            total_outs_after = existing_outs + add_outs_total

            if total_outs_after >= 3:
                try:
                    curr_idx = inn_options.index(current_inn)
                    if curr_idx < len(inn_options) - 1:
                        st.session_state["p_det_inn"] = inn_options[curr_idx + 1]
                        st.toast(f"⚾️ 3アウトチェンジ！ {st.session_state['p_det_inn']}へ進みます")
                    else:
                        st.session_state["p_det_inn"] = current_inn
                except ValueError:
                    st.session_state["p_det_inn"] = current_inn

            # 進塁後のランナー維持ロジック
            if total_outs_after >= 3:
                st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
            else:
                next_1b = None
                next_2b = None
                next_3b = None

                if cur_1b:
                    if not res_1b:
                        next_1b = cur_1b_runner_name
                    elif res_1b in ["盗塁", "進塁1", "進塁"]:
                        next_2b = cur_1b_runner_name
                    elif res_1b == "進塁2":
                        next_3b = cur_1b_runner_name

                if cur_2b:
                    if not res_2b:
                        if not next_2b:
                            next_2b = cur_2b_runner_name
                    elif res_2b in ["盗塁", "進塁1", "進塁"]:
                        next_3b = cur_2b_runner_name

                if cur_3b:
                    if not res_3b:
                        if not next_3b:
                            next_3b = cur_3b_runner_name

                if p_res in ["四球", "死球"]:
                    if next_2b and next_1b:
                        next_3b = next_2b
                        next_2b = next_1b
                    elif next_1b:
                        next_2b = next_1b
                    next_1b = current_batter_name

                if p_res in ["単打", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]:
                    if not next_1b:
                        next_1b = current_batter_name
                elif p_res == "二塁打":
                    if not next_2b:
                        next_2b = current_batter_name
                elif p_res == "三塁打":
                    if not next_3b:
                        next_3b = current_batter_name
                elif p_res in ["本塁打", "併殺打"]:
                    next_1b = None
                    next_2b = None
                    next_3b = None

                st.session_state["p_persistent_runners"] = {
                    "1b": next_1b,
                    "2b": next_2b,
                    "3b": next_3b,
                }

            st.session_state["needs_pitching_form_clear"] = True

            st.success(f"✅ {target_pitcher_name}投手の記録を保存しました")
            time.sleep(0.5)
            st.rerun()

    # --- 全イニング詳細履歴表示 ---
    st.write("")
    st.markdown("#### 📊 全イニング 攻撃・守備 詳細履歴")

    has_batting_history = not today_batting_df.empty
    has_pitching_history = (
        not today_pitching_df.empty
        and not today_pitching_df[~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"])].empty
    )

    if has_batting_history or has_pitching_history:
        exclude_res = ["スタメン", "守備変更", "交代", "ベンチ", "試合前", "まとめ入力", "", "nan", "残塁"]
        exclude_pattern = r"進塁|得点|残塁"

        valid_batting_df = pd.DataFrame()
        if not today_batting_df.empty:
            res_s = today_batting_df["結果"].astype(str).str.strip() if "結果" in today_batting_df.columns else pd.Series("", index=today_batting_df.index)
            type_s = today_batting_df["種別"].astype(str).str.strip() if "種別" in today_batting_df.columns else pd.Series("", index=today_batting_df.index)
            
            pos_col = "守備位置" if "守備位置" in today_batting_df.columns else ("位置" if "位置" in today_batting_df.columns else "")
            pos_s = today_batting_df[pos_col].astype(str).str.strip() if pos_col else pd.Series("", index=today_batting_df.index)

            is_bat_excluded = (
                res_s.isin(exclude_res) | 
                res_s.str.contains(exclude_pattern, na=False) |
                type_s.str.contains(exclude_pattern, na=False) |
                pos_s.str.contains(exclude_pattern, na=False)
            )
            valid_batting_df = today_batting_df[~is_bat_excluded].copy()

        valid_pitching_df = pd.DataFrame()
        if not today_pitching_df.empty:
            mask_pit = ~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"])
            if "種別" in today_pitching_df.columns:
                mask_pit = mask_pit & (today_pitching_df["種別"].str.contains("詳細", na=False) | today_pitching_df["打順"].notna())
            if "結果" in today_pitching_df.columns:
                mask_pit = mask_pit & ~today_pitching_df["結果"].astype(str).str.contains(exclude_pattern, na=False)
            valid_pitching_df = today_pitching_df[mask_pit].copy()

        raw_inns = list(
            set(
                (valid_batting_df["イニング"].dropna().astype(str).tolist() if not valid_batting_df.empty and "イニング" in valid_batting_df.columns else [])
                + (valid_pitching_df["イニング"].dropna().astype(str).tolist() if not valid_pitching_df.empty and "イニング" in valid_pitching_df.columns else [])
            )
        )

        exclude_inns = ["まとめ入力", "試合前", "ベンチ", "", "nan", "None"]
        active_innings = [inn for inn in raw_inns if inn not in exclude_inns]

        def inning_sort_key(inn):
            inn_str = str(inn)
            is_ext = 1 if "延長" in inn_str else 0
            m = re.search(r"(\d+)", inn_str)
            num = int(m.group(1)) if m else 99
            sub = 0 if "表" in inn_str else (1 if "裏" in inn_str else 2)
            return (is_ext, num, sub)

        active_innings.sort(key=inning_sort_key)

        if active_innings:
            for inn in active_innings:
                inn_id = inn.replace("回", "").replace("表", "").replace("裏", "")
                st.markdown(f"<div id='inning-{inn_id}' style='scroll-margin-top: 100px;'></div>", unsafe_allow_html=True)

                inn_bat_df = (
                    valid_batting_df[valid_batting_df["イニング"] == inn]
                    if not valid_batting_df.empty and "イニング" in valid_batting_df.columns
                    else pd.DataFrame()
                )
                if not inn_bat_df.empty:
                    st.markdown("---")
                    st.markdown(f"### 📍 **{inn}（攻撃）**")
                    bat_items = []
                    for _, row in inn_bat_df.iterrows():
                        b_order = row.get("打順", "")
                        try:
                            b_order_str = f"{int(float(b_order))}番" if pd.notna(b_order) and str(b_order).strip() != "" else ""
                        except (ValueError, TypeError):
                            b_order_str = f"{b_order}番" if b_order else ""

                        p_name = row.get("打者名", row.get("選手名", ""))
                        res = row.get("結果", "")
                        direction = row.get("打球方向", "")
                        rbi = pd.to_numeric(row.get("打点", 0), errors="coerce")
                        run = pd.to_numeric(row.get("得点", 0), errors="coerce")

                        res_str = str(res)
                        if direction and str(direction) not in ["---", "nan", "None", ""]:
                            res_str = f"{direction}{res_str}"
                        if pd.notna(rbi) and rbi > 0:
                            res_str = f"{res_str} ・ 打点{int(rbi)}"
                        if pd.notna(run) and run > 0:
                            res_str = f"{res_str} 🟢得点"

                        bat_items.append({"打順": b_order_str, "打者": p_name, "結果": res_str})
                    df_bat_disp = pd.DataFrame(bat_items).T
                    st.dataframe(apply_dataframe_style(df_bat_disp, highlight_batting), use_container_width=True)

                inn_pit_df = (
                    valid_pitching_df[valid_pitching_df["イニング"] == inn]
                    if not valid_pitching_df.empty and "イニング" in valid_pitching_df.columns
                    else pd.DataFrame()
                )
                if not inn_pit_df.empty:
                    st.markdown("---")
                    st.markdown(f"### 📍 **{inn}（守備）**")
                    pit_items = []
                    for _, row in inn_pit_df.iterrows():
                        b_ord_val = row.get("打順")
                        if pd.notna(b_ord_val) and str(b_ord_val).strip() not in ["", "nan", "None"]:
                            try:
                                b_idx = f"{int(float(b_ord_val))}番"
                            except (ValueError, TypeError):
                                b_idx = f"{b_ord_val}番"
                        else:
                            raw_b_idx = str(row.get("種別", "")).split(":")[1].replace("番打者", "") if "種別" in row and ":" in str(row.get("種別", "")) else "?"
                            try:
                                b_idx = f"{int(float(raw_b_idx))}番"
                            except (ValueError, TypeError):
                                b_idx = f"{raw_b_idx}番" if raw_b_idx != "?" else "?"

                        pitcher_n = row.get("投手名", row.get("選手名", ""))
                        batter_n = row.get("打者名", "")

                        raw_res = str(row.get("結果", ""))
                        pos_str = str(row.get("打球方向", "")) or str(row.get("守備位置", "")) or str(row.get("位置", ""))
                        if pos_str and pos_str not in ["nan", "None", ""]:
                            raw_res = f"{raw_res}({pos_str})"
                        fielder_name = str(row.get("処理野手", ""))
                        if fielder_name and fielder_name not in ["nan", "None", ""]:
                            clean_name = fielder_name.replace("(", "").replace(")", "")
                            res_text = f"{raw_res} [{clean_name}]"
                        else:
                            res_text = raw_res
                        rows_val = pd.to_numeric(row.get("失点", 0), errors="coerce")
                        runs = int(runs_val) if pd.notna(runs_val) else 0
                        if runs > 0:
                            res_text = f"{res_text} 💥失点{runs}"

                        item_dict = {"打順": b_idx, "投手": pitcher_n}
                        if batter_n:
                            item_dict["打者"] = batter_n
                        item_dict["結果"] = res_text

                        pit_items.append(item_dict)
                    df_pit_disp = pd.DataFrame(pit_items).T
                    st.dataframe(apply_dataframe_style(df_pit_disp, highlight_pitching), use_container_width=True)
        else:
            st.caption("詳細データはまだありません。")
    else:
        st.caption("詳細データはまだありません。")