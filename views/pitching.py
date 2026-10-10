import re
import time
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from config.settings import ALL_POSITIONS, SPREADSHEET_URL, TARGET_COLUMNS, MY_TEAM
from utils.players import get_active_players
from utils.ui import fmt_player_name, render_scoreboard
from utils.db import get_connection
from views.team_sharing import share_match_data_to_opponent

st.markdown("""
<style>
/* すべてのボタンやインタラクティブ要素のタップ遅延を解除し、タッチレスポンスを向上 */
button, div[role="button"], input, select, .stButton > button, div[data-baseweb="popover"] {
    touch-action: manipulation !important;
    -webkit-tap-highlight-color: transparent !important;
}

/* ボタンの押し心地（視覚的フィードバック）を明確にする */
button:active, div[role="button"]:active {
    transform: scale(0.96);
    transition: transform 0.05s ease;
}
</style>
""", unsafe_allow_html=True)


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
    if df.empty or "結果" not in df.columns:
        return 0
    
    single_out_list = [
        "三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)",
        "犠飛", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"
    ]
    
    s_outs = len(df[df["結果"].isin(single_out_list)])
    d_outs = len(df[df["結果"] == "併殺打"]) * 2
    t_outs = len(df[df["結果"] == "三重殺"]) * 3
    return s_outs + d_outs + t_outs


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
        if any(keyword in val for keyword in ["💥失点", "得点", "本塁打"]):
            return "color: red; font-weight: bold;"
        elif any(hit in val for hit in ["単打", "二塁打", "三塁打"]):
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
        if name and name not in ["選手", "nan", "None", "", "未選択", "相手投手"]:
            if pos in ["投", "投手", "P"] or name not in opp_pitcher_options:
                opp_pitcher_options.append(name)
            
    dh_p = st.session_state.get("opp_sn_dh_pitcher")
    if dh_p and dh_p not in ["相手投手", "選手", "未選択", "nan", "None", ""]:
        opp_pitcher_options.append(dh_p)

    today_p = filter_today_df(df_pitching, selected_date_str, opp_team)
    p_col = "投手名" if "投手名" in df_pitching.columns else "選手名"

    if not today_p.empty and p_col in today_p.columns:
        existing_p = today_p[p_col].dropna().astype(str).str.strip().tolist()
        opp_pitcher_options.extend([p for p in existing_p if p not in ALL_PLAYERS and p not in ["相手投手"]])

    default_opps = [f"選手{i}" for i in range(1, 10)]
    opp_pitcher_options = list(dict.fromkeys([p for p in opp_pitcher_options + default_opps if p and p not in ["nan", "None", "", "相手投手"]]))

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
                "ID", "日付", "グラウンド", "対戦相手", "試合種別", "イニング", p_col, "結果", "自責点", "勝敗"
            ])

            if "日付" in updated_df.columns and "対戦相手" in updated_df.columns:
                today_mask = (
                    (updated_df["日付"].astype(str) == selected_date_str) &
                    (updated_df["対戦相手"].astype(str).str.strip() == str(opp_team).strip())
                )
                updated_df.loc[today_mask, "勝敗"] = "ー"

                current_max_id = int(pd.to_numeric(updated_df["ID"], errors="coerce").fillna(0).max()) if not updated_df.empty and "ID" in updated_df.columns else 0

                for p_name, dec_val in dec_map.items():
                    p_mask = today_mask & (updated_df[p_col].astype(str).str.strip() == p_name)
                    if p_mask.any():
                        updated_df.loc[p_mask, "勝敗"] = dec_val
                    else:
                        current_max_id += 1
                        new_row = {
                            "ID": current_max_id,
                            "日付": selected_date_str,
                            "グラウンド": ground_name,
                            "対戦相手": opp_team,
                            "試合種別": match_type,
                            "イニング": "試合終了",
                            p_col: p_name,
                            "結果": "ー",
                            "打点": 0,
                            "自責点": 0,
                            "勝敗": dec_val,
                            "エラー野手": ""
                        }
                        updated_df = pd.concat([updated_df, pd.DataFrame([new_row])], ignore_index=True)

            for col in TARGET_COLUMNS:
                if col not in updated_df.columns:
                    updated_df[col] = 0 if col in ["ID", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""

            save_df = updated_df[TARGET_COLUMNS].copy()

            try:
                target_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
                conn.update(spreadsheet=target_url, worksheet=ws_pitching, data=save_df)
                st.cache_data.clear()
                st.success("✅ 責任投手情報を保存しました！")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"保存失敗: {e}")


# --- 直近の投手スコア登録を取り消す（Undo）関数 ---
def undo_last_pitching_entry(df_pitching, selected_date_str, opp_team, match_type, ws_pitching, conn):
    target_date_str = pd.to_datetime(selected_date_str, errors='coerce').strftime('%Y-%m-%d')
    if "日付" in df_pitching.columns:
        df_pitching_copy = df_pitching.copy()
        df_pitching_copy["_date_str"] = pd.to_datetime(df_pitching_copy["日付"], errors='coerce').dt.strftime('%Y-%m-%d')
        today_pit = df_pitching_copy[
            (df_pitching_copy["_date_str"] == target_date_str) & 
            (df_pitching_copy["対戦相手"].astype(str).str.strip() == str(opp_team).strip()) & 
            (df_pitching_copy["試合種別"].astype(str).str.strip() == str(match_type).strip())
        ]
    else:
        today_pit = pd.DataFrame()

    if today_pit.empty:
        st.warning("⚠️ 取り消し可能な本日の投手スコア登録データがありません。")
        return

    last_ids = st.session_state.get("last_added_ids_pitching", [])
    if not last_ids:
        max_id = pd.to_numeric(today_pit["ID"], errors="coerce").max()
        if pd.notna(max_id):
            last_ids = [int(max_id)]

    if not last_ids:
        st.warning("⚠️ 取り消し対象のデータが見つかりませんでした。")
        return

    last_numeric_ids = set(pd.to_numeric(pd.Series(last_ids), errors="coerce").dropna().tolist())
    df_numeric_ids = pd.to_numeric(df_pitching["ID"], errors="coerce")
    df_filtered = df_pitching[~df_numeric_ids.isin(last_numeric_ids)].copy()
    
    if "_date_str" in df_filtered.columns:
        df_filtered = df_filtered.drop(columns=["_date_str"])

    for col in TARGET_COLUMNS:
        if col not in df_filtered.columns:
            df_filtered[col] = 0 if col in ["ID", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""

    df_to_save = df_filtered[TARGET_COLUMNS].copy()

    try:
        target_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
        conn.update(spreadsheet=target_url, worksheet=ws_pitching, data=df_to_save)
        
        st.cache_data.clear()
        cache_key = f"cache_pitching_{selected_date_str}_{opp_team}_{match_type}"
        st.session_state[cache_key] = df_filtered
        st.session_state.pop("cached_df_pitching", None)
        st.session_state.pop("last_added_ids_pitching", None)

        # 🏃★ 走者状況・入力状態・世代カウンターの完全リセット処理 ★
        st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
        st.session_state["p_clear_counter"] = st.session_state.get("p_clear_counter", 0) + 1

        keys_to_clear = [k for k in list(st.session_state.keys()) if any(k.startswith(p) for p in [
            "p_runner_", "pitching_quick_", "p_b_count_", "p_s_count_", "p_f_count_", "p_pitch_count_"
        ])]
        for k in keys_to_clear:
            del st.session_state[k]

        st.success("✅ 直近のスコア登録を取り消しました！")
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        st.error(f"取り消しに失敗しました: {e}")


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

    with st.popover(f"📤 この試合データを対戦相手【{opp_team}】に共有・送信する", use_container_width=True):
        st.markdown(f"##### 🤝 対戦相手【{opp_team}】へのデータ共有")
        st.caption("ホストチームとして記録したこの試合のスコア（打撃・投手データ）を反転させ、相手チームのスプレッドシートへ自動登録します。")
        st.warning("※ 相手チーム側に同じ日付・同じ対戦相手のデータが既に存在する場合は、最新データで上書き更新されます。")
        
        if st.button(f"🚀 【{opp_team}】のスプレッドシートに送信する", type="primary", use_container_width=True, key=f"share_btn_pitching_{selected_date_str}_{opp_team}"):
            with st.spinner("相手チームのデータベースへ送信中..."):
                conn_db = get_connection()
                success, msg = share_match_data_to_opponent(
                    conn=conn_db,
                    host_team_name=MY_TEAM,
                    target_opp=opp_team,
                    match_date_str=selected_date_str,
                    match_type=match_type,
                    match_bat=today_batting_df,
                    match_pit=today_pitching_df
                )
                if success:
                    st.success(msg)
                    st.balloons()
                else:
                    st.error(msg)

    if "p_clear_counter" not in st.session_state:
        st.session_state["p_clear_counter"] = 0

    curr_counter = st.session_state.get("p_clear_counter", 0)

    current_match_id = f"{selected_date_str}_{opp_team}_{match_type}"
    if st.session_state.get("last_p_match_id") != current_match_id:
        keys_to_reset = [
            "p_det_inn", "opp_batter_index", "p_persistent_runners", "opp_sn_dh_pitcher", "opp_lineup_states"
        ]
        for k in list(st.session_state.keys()):
            if k in keys_to_reset or k.startswith("sync_") or k.startswith("opp_sp_") or k.startswith("opp_sn_") or k.startswith("pill_opp_") or "pitching_quick" in k or "p_runner" in k or "p_b_count" in k or "p_s_count" in k or "p_f_count" in k or "p_pitch_count" in k:
                del st.session_state[k]
        st.session_state["last_p_match_id"] = current_match_id
        st.session_state["p_clear_counter"] = 0
        curr_counter = 0

    if "p_persistent_runners" not in st.session_state:
        st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}

    p_inning_suffix = "裏" if is_kagura_top else "表"

    if "opp_batter_index" not in st.session_state:
        st.session_state["opp_batter_index"] = 1
    if "opp_batter_count" not in st.session_state:
        st.session_state["opp_batter_count"] = 9
    if "p_det_inn" not in st.session_state:
        st.session_state["p_det_inn"] = f"1回{p_inning_suffix}"

    if "opp_lineup_states" not in st.session_state:
        st.session_state["opp_lineup_states"] = {}

    for i in range(20):
        sn_k = f"opp_sn_{i}"
        default_val = f"選手{i + 1}"
        if st.session_state.get(sn_k) in [None, "", "選手", "未選択", "nan", "None", "相手投手"]:
            st.session_state[sn_k] = default_val

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

    inn_options = []
    for i in range(1, 10):
        inn_options.extend([f"{i}回表", f"{i}回裏"])
    inn_options.extend(["延長表", "延長裏"])

    current_inn_val = st.session_state.get("p_det_inn", f"1回{p_inning_suffix}")

    # ★ 追加：すでに3アウトになっている場合は自動で次のイニングへ進める（batting_15.pyと同等の処理）
    if not today_pitching_df.empty and "イニング" in today_pitching_df.columns:
        p_inn_df_check = today_pitching_df[today_pitching_df["イニング"] == current_inn_val]
        existing_outs = calculate_outs(p_inn_df_check)
        if existing_outs >= 3:
            try:
                curr_idx = inn_options.index(current_inn_val)
                if curr_idx < len(inn_options) - 2:
                    current_inn_val = inn_options[curr_idx + 2]
                    st.session_state["p_det_inn"] = current_inn_val
            except ValueError:
                pass

    if "opp_batter_offset" not in st.session_state:
        st.session_state["opp_batter_offset"] = 0

    PA_RESULTS_PITCHING = [
        "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打",
        "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "三重殺", "振り逃げ三振",
        "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害"
    ]

    active_opp_orders = 9
    opp_display_count = st.session_state.get("opp_batter_count", 9)
    for idx_check in range(opp_display_count - 1, -1, -1):
        if st.session_state.get(f"opp_sn_{idx_check}"):
            active_opp_orders = idx_check + 1
            break

    if not today_pitching_df.empty and "結果" in today_pitching_df.columns:
        valid_opp_pa = today_pitching_df[today_pitching_df["結果"].astype(str).isin(PA_RESULTS_PITCHING)]
        total_opp_pa = len(valid_opp_pa)
    else:
        total_opp_pa = 0

    current_opp_batter_index = (total_opp_pa + st.session_state.get("opp_batter_offset", 0)) % active_opp_orders
    current_opp_order_num = current_opp_batter_index + 1

    raw_opp_batter = st.session_state.get(f"opp_sn_{current_opp_batter_index}", "")
    if raw_opp_batter and str(raw_opp_batter).strip() not in ["None", "nan", "", "未選択", "相手投手"]:
        formatted_opp_batter_name = str(raw_opp_batter).strip()
    else:
        formatted_opp_batter_name = f"選手{current_opp_order_num}"

    st.divider()

    col_adj1, col_adj2, col_adj3, col_adj4 = st.columns([2.5, 1.0, 1.0, 1.0])
    with col_adj1:
        st.markdown(
            f"<div style='font-weight:bold; font-size:16px; line-height:2.4;'>📍 打順調整 (オフセット: {st.session_state.get('opp_batter_offset', 0)})</div>",
            unsafe_allow_html=True,
        )
    with col_adj2:
        if st.button("◀ 前へ", key="btn_opp_offset_prev", use_container_width=True):
            st.session_state["opp_batter_offset"] = st.session_state.get("opp_batter_offset", 0) - 1
            st.rerun()
    with col_adj3:
        if st.button("リセット", key="btn_opp_offset_reset", use_container_width=True):
            st.session_state["opp_batter_offset"] = 0
            st.rerun()
    with col_adj4:
        if st.button("次へ ▶", key="btn_opp_offset_next", use_container_width=True):
            st.session_state["opp_batter_offset"] = st.session_state.get("opp_batter_offset", 0) + 1
            st.rerun()

    st.divider()

    with st.container():
        c_sub1, c_sub2 = st.columns([3, 2])
        with c_sub1:
            submit_detail = st.button("スコア登録実行", type="primary", use_container_width=True, key="submit_pitching_action")
        with c_sub2:
            undo_submit_detail = st.button("↺ 直近の登録を取り消す", type="secondary", use_container_width=True, key="undo_pitching_action", help="直前に登録した投手スコアデータを取り消して登録前の状態に戻します")

        if undo_submit_detail:
            undo_last_pitching_entry(df_pitching, selected_date_str, opp_team, match_type, ws_pitching, conn)

        if st.session_state.get("pitching_error_msg"):
            st.error(st.session_state["pitching_error_msg"])
            st.session_state["pitching_error_msg"] = None

        c_inn, c_outs = st.columns([1.2, 3.8])
        with c_inn:
            def_inn_ix = inn_options.index(current_inn_val) if current_inn_val in inn_options else 0
            # ★ 修正：key="pitching_inn_select" を削除し、打撃側と同じく index の動的更新が効くようにする
            current_inn = st.selectbox("イニング選択", inn_options, index=def_inn_ix, label_visibility="collapsed")
            st.session_state["p_det_inn"] = current_inn

        with c_outs:
            p_inn_df_disp = (
                today_pitching_df[today_pitching_df["イニング"] == current_inn]
                if not today_pitching_df.empty and "イニング" in today_pitching_df.columns
                else pd.DataFrame()
            )
            disp_outs = calculate_outs(p_inn_df_disp) % 3

            b_cnt = st.session_state.get(f"p_b_count_{curr_counter}", 0)
            s_cnt = st.session_state.get(f"p_s_count_{curr_counter}", 0)
            p_cnt = st.session_state.get(f"p_pitch_count_{curr_counter}", 0)

            st.markdown(render_bso_indicator(disp_outs, b_cnt, s_cnt, p_cnt), unsafe_allow_html=True)

            b_col1, b_col2, b_col3, b_col4 = st.columns([1.1, 1.1, 1.1, 0.8])

            with b_col1:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#22c55e;'>🟢 ボール</div>", unsafe_allow_html=True)
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("➖", key=f"btn_p_b_sub_{curr_counter}", use_container_width=True, disabled=(b_cnt <= 0)):
                        st.session_state[f"p_pitch_count_{curr_counter}"] = max(0, p_cnt - 1)
                        st.session_state[f"p_b_count_{curr_counter}"] = max(0, b_cnt - 1)
                        st.rerun()
                with bc2:
                    if st.button("➕", key=f"btn_p_b_add_{curr_counter}", use_container_width=True, disabled=(b_cnt >= 3)):
                        st.session_state[f"p_pitch_count_{curr_counter}"] = p_cnt + 1
                        if b_cnt < 3:
                            st.session_state[f"p_b_count_{curr_counter}"] = b_cnt + 1
                        st.rerun()

            with b_col2:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#eab308;'>🟡 ストライク</div>", unsafe_allow_html=True)
                sc1, sc2 = st.columns(2)
                with sc1:
                    if st.button("➖", key=f"btn_p_s_sub_{curr_counter}", use_container_width=True, disabled=(s_cnt <= 0)):
                        st.session_state[f"p_pitch_count_{curr_counter}"] = max(0, p_cnt - 1)
                        st.session_state[f"p_s_count_{curr_counter}"] = max(0, s_cnt - 1)
                        st.rerun()
                with sc2:
                    if st.button("➕", key=f"btn_p_s_add_{curr_counter}", use_container_width=True, disabled=(s_cnt >= 2)):
                        st.session_state[f"p_pitch_count_{curr_counter}"] = p_cnt + 1
                        if s_cnt < 2:
                            st.session_state[f"p_s_count_{curr_counter}"] = s_cnt + 1
                        st.rerun()

            f_cnt = st.session_state.get(f"p_f_count_{curr_counter}", 0)

            with b_col3:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#6b7280;'>⚪ ファール</div>", unsafe_allow_html=True)
                fc1, fc2 = st.columns(2)
                with fc1:
                    if st.button("➖", key=f"btn_p_f_sub_{curr_counter}", use_container_width=True, disabled=(f_cnt <= 0)):
                        st.session_state[f"p_pitch_count_{curr_counter}"] = max(0, p_cnt - 1)
                        st.session_state[f"p_f_count_{curr_counter}"] = max(0, f_cnt - 1)
                        st.rerun()
                with fc2:
                    if st.button("➕", key=f"btn_p_f_add_{curr_counter}", use_container_width=True):
                        st.session_state[f"p_pitch_count_{curr_counter}"] = p_cnt + 1
                        st.session_state[f"p_f_count_{curr_counter}"] = f_cnt + 1
                        if s_cnt < 2:
                            st.session_state[f"p_s_count_{curr_counter}"] = s_cnt + 1
                        st.rerun()

            with b_col4:
                st.markdown("<div style='font-size:12px; font-weight:bold; text-align:center; color:#374151;'>リセット</div>", unsafe_allow_html=True)
                if st.button("🔄", key=f"btn_p_reset_bso_{curr_counter}", use_container_width=True):
                    st.session_state[f"p_b_count_{curr_counter}"] = 0
                    st.session_state[f"p_s_count_{curr_counter}"] = 0
                    st.session_state[f"p_f_count_{curr_counter}"] = 0
                    st.session_state[f"p_pitch_count_{curr_counter}"] = 0
                    st.rerun()

    st.divider()

    q_cols = [4.0, 5.0]
    qc = st.columns(q_cols)

    with qc[0]:
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 0px 12px; border-radius: 8px; border-left: 8px solid #ff4b4b; height: 50px; display: flex; align-items: center; justify-content: flex-start; gap: 10px; box-sizing: border-box;">
            <span style="color: #555; font-weight: bold; white-space: nowrap;">📍 打順</span>
            <span style="color: #111; font-weight: bold; white-space: nowrap;">{current_opp_order_num}番</span>
            <span style="color: #ff4b4b; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{formatted_opp_batter_name}</span>
        </div>
        """, unsafe_allow_html=True)

    with qc[1]:
        current_res = st.session_state.get(f"pitching_quick_sr_{curr_counter}")
        current_dirs = st.session_state.get(f"pitching_quick_sd_{curr_counter}", [])
        current_ef = st.session_state.get(f"pitching_quick_ef_{curr_counter}")
        current_rbi = st.session_state.get(f"pitching_quick_si_{curr_counter}")
        current_er = st.session_state.get(f"pitching_quick_er_{curr_counter}")
        er_val = current_er if current_er is not None else 0

        res_label = f" 🟢 {current_res}" if current_res else ""
        dir_label = f" ({''.join(current_dirs)})" if current_dirs else ""
        ef_label = f" [E:{current_ef}]" if current_ef else ""
        rbi_label = f" [打点{current_rbi}]" if current_rbi is not None else ""
        run_er_label = f" [自責{er_val}]" if (er_val > 0 or current_res) else ""

        summary_btn_label = f"投球結果{res_label}{dir_label}{ef_label}{rbi_label}{run_er_label} 🔽"

        with st.popover(summary_btn_label, use_container_width=True):
            st.markdown("##### ⚾ 投球結果を選択")
            res_options = [
                "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打",
                "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "三重殺", "振り逃げ三振",
                "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "ボーク", "暴投", "捕逸",
                "牽制死", "盗塁死", "盗塁", "走塁死"
            ]
            st.pills("投球結果", res_options, key=f"pitching_quick_sr_{curr_counter}", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚾ 打球方向・送球経路を選択（複数選択可）")
            dir_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
            st.pills("打球方向", dir_options, selection_mode="multi", key=f"pitching_quick_sd_{curr_counter}", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚠ エラー野手を選択（エラー発生時）")
            ef_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]
            st.pills("エラー野手", ef_options, key=f"pitching_quick_ef_{curr_counter}", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚾ 打点がある場合は選択 (1〜4)")
            rbi_options = [0, 1, 2, 3, 4]
            st.pills("打点", rbi_options, key=f"pitching_quick_si_{curr_counter}", label_visibility="collapsed")

            st.markdown("---")
            st.markdown("##### ⚾ 自責点を選択 (0〜4)")
            er_options = [0, 1, 2, 3, 4]
            st.pills("自責点", er_options, key=f"pitching_quick_er_{curr_counter}", label_visibility="collapsed")

            st.markdown("---")
            if st.button("🔄 入力をすべてクリア", use_container_width=True, key=f"pitching_all_clear_btn_{curr_counter}"):
                st.session_state["p_clear_counter"] = curr_counter + 1
                st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
                st.rerun()

    st.divider()

    opp_count = st.session_state.get("opp_batter_count", 9)
    curr_opp_idx = st.session_state.get("opp_batter_index", 1)

    default_opp_players = [f"選手{i}" for i in range(1, 21)]
    opp_player_options = []

    if "fetched_opp_players" in st.session_state:
        df_opp_p = st.session_state["fetched_opp_players"]
        p_col_opp = "打者名" if "打者名" in df_opp_p.columns else "選手名"
        if isinstance(df_opp_p, pd.DataFrame) and not df_opp_p.empty and p_col_opp in df_opp_p.columns:
            opp_player_options.extend(df_opp_p[p_col_opp].dropna().astype(str).str.strip().tolist())

    if "fetched_opp_order" in st.session_state:
        df_opp_o = st.session_state["fetched_opp_order"]
        if isinstance(df_opp_o, pd.DataFrame) and not df_opp_o.empty:
            o_col_p = "打者名" if "打者名" in df_opp_o.columns else "選手名"
            if o_col_p in df_opp_o.columns:
                opp_player_options.extend(df_opp_o[o_col_p].dropna().astype(str).str.strip().tolist())

    opp_bench_list = st.session_state.get("persistent_opp_bench", [])
    for b_name in opp_bench_list:
        if b_name and str(b_name) not in ["None", "nan", ""]:
            opp_player_options.append(str(b_name).strip())

    for k, v in list(st.session_state.items()):
        if k.startswith("opp_sn_") and v and str(v) not in ["None", "nan", "選手", "相手投手"]:
            opp_player_options.append(str(v).strip())

    default_names = {f"選手{i}" for i in range(1, 21)}
    real_players = [p for p in opp_player_options if p and p not in default_names and not p.startswith("選手") and p != "相手投手"]

    if real_players:
        # 打順に入っている選手名（デフォルト名含む）を選択肢に維持
        active_sn = [str(st.session_state.get(f"opp_sn_{i}")).strip() for i in range(20) if st.session_state.get(f"opp_sn_{i}")]
        opp_player_options = list(dict.fromkeys(real_players + [p for p in active_sn if p and p not in ["None", "nan", "", "相手投手"]]))
    else:
        opp_player_options = list(default_opp_players)

    opp_player_options = list(dict.fromkeys([p for p in opp_player_options if p and p not in ["nan", "None", "", "相手投手"]]))
    runner_options = ["なし"] + opp_player_options

    st.markdown("##### 🏃 走者状況")

    p_runners = st.session_state.get("p_persistent_runners", {"1b": None, "2b": None, "3b": None})

    for b_key in ["1b", "2b", "3b"]:
        sel_key = f"p_runner_{b_key}_{curr_counter}"
        # 🌟 runner_options に存在しない値が残っている場合も「なし」に補正
        if sel_key not in st.session_state or st.session_state[sel_key] is None or st.session_state[sel_key] not in runner_options:
            val = p_runners.get(b_key)
            st.session_state[sel_key] = val if (val and val in runner_options) else "なし"

    r3_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死"]
    r2_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死", "進塁1"]
    r1_res_options = ["得点", "盗塁", "盗塁死", "走塁死", "牽制死", "進塁1", "進塁2"]
    out_fielder_options = ["投", "捕", "一", "二", "三", "遊", "左", "中", "右"]

    r_cols = st.columns(3)

    with r_cols[0]:
        st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>3塁</div>", unsafe_allow_html=True)

        r3_val = st.session_state.get(f"p_runner_3b_{curr_counter}", "なし")
        r3_label = f"🟢 {r3_val} 🔽" if r3_val and r3_val != "なし" else "走者選択 🔽"
        with st.popover(r3_label, use_container_width=True):
            st.markdown("##### 3塁走者を選択")
            st.pills("3塁走者", runner_options, key=f"p_runner_3b_{curr_counter}", label_visibility="collapsed")

        r3_res = st.session_state.get(f"p_runner_3b_res_{curr_counter}")
        r3_f = st.session_state.get(f"p_runner_3b_fielder_{curr_counter}")
        r3_btn = (
            f"🟢 {r3_res}({r3_f}) 🔽" if (r3_res in ["走塁死", "盗塁死", "牽制死"] and r3_f)
            else (f"🟢 {r3_res} 🔽" if r3_res else "走塁結果 🔽")
        )
        with st.popover(r3_btn, use_container_width=True):
            st.markdown("##### 3塁 走塁結果を選択")
            cur_r3_res = st.pills("3塁結果ピル", r3_res_options, key=f"p_runner_3b_res_{curr_counter}", label_visibility="collapsed")
            if cur_r3_res in ["走塁死", "盗塁死", "牽制死"]:
                st.markdown("---")
                st.markdown("##### 🎯 処理野手（補殺）を選択")
                st.pills("3塁処理野手ピル", out_fielder_options, key=f"p_runner_3b_fielder_{curr_counter}", label_visibility="collapsed")

    with r_cols[1]:
        st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>2塁</div>", unsafe_allow_html=True)

        r2_val = st.session_state.get(f"p_runner_2b_{curr_counter}", "なし")
        r2_label = f"🟢 {r2_val} 🔽" if r2_val and r2_val != "なし" else "走者選択 🔽"
        with st.popover(r2_label, use_container_width=True):
            st.markdown("##### 2塁走者を選択")
            st.pills("2塁走者", runner_options, key=f"p_runner_2b_{curr_counter}", label_visibility="collapsed")

        r2_res = st.session_state.get(f"p_runner_2b_res_{curr_counter}")
        r2_f = st.session_state.get(f"p_runner_2b_fielder_{curr_counter}")
        r2_btn = (
            f"🟢 {r2_res}({r2_f}) 🔽" if (r2_res in ["走塁死", "盗塁死", "牽制死"] and r2_f)
            else (f"🟢 {r2_res} 🔽" if r2_res else "走塁結果 🔽")
        )
        with st.popover(r2_btn, use_container_width=True):
            st.markdown("##### 2塁 走塁結果を選択")
            cur_r2_res = st.pills("2塁結果ピル", r2_res_options, key=f"p_runner_2b_res_{curr_counter}", label_visibility="collapsed")
            if cur_r2_res in ["走塁死", "盗塁死", "牽制死"]:
                st.markdown("---")
                st.markdown("##### 🎯 処理野手（補殺）を選択")
                st.pills("2塁処理野手ピル", out_fielder_options, key=f"p_runner_2b_fielder_{curr_counter}", label_visibility="collapsed")

    with r_cols[2]:
        st.markdown("<div style='text-align:center; font-weight:bold; background:#e0ebff; padding:2px; border-radius:4px;'>1塁</div>", unsafe_allow_html=True)

        r1_val = st.session_state.get(f"p_runner_1b_{curr_counter}", "なし")
        r1_label = f"🟢 {r1_val} 🔽" if r1_val and r1_val != "なし" else "走者選択 🔽"
        with st.popover(r1_label, use_container_width=True):
            st.markdown("##### 1塁走者を選択")
            st.pills("1塁走者", runner_options, key=f"p_runner_1b_{curr_counter}", label_visibility="collapsed")

        r1_res = st.session_state.get(f"p_runner_1b_res_{curr_counter}")
        r1_f = st.session_state.get(f"p_runner_1b_fielder_{curr_counter}")
        r1_btn = (
            f"🟢 {r1_res}({r1_f}) 🔽" if (r1_res in ["走塁死", "盗塁死", "牽制死"] and r1_f)
            else (f"🟢 {r1_res} 🔽" if r1_res else "走塁結果 🔽")
        )
        with st.popover(r1_btn, use_container_width=True):
            st.markdown("##### 1塁 走塁結果を選択")
            cur_r1_res = st.pills("1塁結果ピル", r1_res_options, key=f"p_runner_1b_res_{curr_counter}", label_visibility="collapsed")
            if cur_r1_res in ["走塁死", "盗塁死", "牽制死"]:
                st.markdown("---")
                st.markdown("##### 🎯 処理野手（補殺）を選択")
                st.pills("1塁処理野手ピル", out_fielder_options, key=f"p_runner_1b_fielder_{curr_counter}", label_visibility="collapsed")

    st.session_state["p_persistent_runners"] = {
        "1b": st.session_state.get(f"p_runner_1b_{curr_counter}") if st.session_state.get(f"p_runner_1b_{curr_counter}") not in [None, "なし", ""] else None,
        "2b": st.session_state.get(f"p_runner_2b_{curr_counter}") if st.session_state.get(f"p_runner_2b_{curr_counter}") not in [None, "なし", ""] else None,
        "3b": st.session_state.get(f"p_runner_3b_{curr_counter}") if st.session_state.get(f"p_runner_3b_{curr_counter}") not in [None, "なし", ""] else None,
    }

    st.divider()

    fetched_order_applied_key = f"applied_opp_order_{selected_date_str}_{opp_team}"
    if "fetched_opp_order" in st.session_state and not st.session_state.get(fetched_order_applied_key):
        df_opp_o = st.session_state["fetched_opp_order"]
        if isinstance(df_opp_o, pd.DataFrame) and not df_opp_o.empty:
            starters_from_order = []
            bench_from_order = []

            for _, row in df_opp_o.iterrows():
                order_str = str(row.get("打順", "")).strip()
                pos_str = str(row.get("守備位置", row.get("位置", "未選択"))).strip()
                name_str = str(row.get("打者名", row.get("選手名", ""))).strip()

                if name_str and name_str not in ["nan", "None", "", "選手"]:
                    if order_str == "控え" or pos_str == "控え":
                        if name_str not in bench_from_order:
                            bench_from_order.append(name_str)
                    else:
                        starters_from_order.append({"name": name_str, "pos": pos_str})

            for idx, s in enumerate(starters_from_order):
                sn_k = f"opp_sn_{idx}"
                sp_k = f"opp_sp_{idx}"
                cur_pos = s["pos"] if s["pos"] in pos_options else "未選択"
                cur_name = s["name"]

                st.session_state[sp_k] = cur_pos
                st.session_state[sn_k] = cur_name

            if bench_from_order:
                st.session_state["persistent_opp_bench"] = bench_from_order
                st.session_state["opp_bench_selection_widget"] = bench_from_order
            
            st.session_state[fetched_order_applied_key] = True

    RES_SHORT_MAP = {
        "本塁打": "本", "三塁打": "三", "二塁打": "二", "単打": "安", "三振": "振",
        "凡退(ゴロ)": "ゴ", "凡退(フライ)": "飛", "四球": "球", "死球": "死", "犠打(ゴロ)": "犠",
        "犠打(フライ)": "犠", "犠飛": "犠飛", "失策(ゴロ)": "失", "失策(フライ)": "失",
        "野選": "野", "併殺打": "併", "三重殺": "三殺", "振り逃げ三振": "逃", "打撃妨害": "妨",
    }

    opp_history_dict = {}
    if not today_pitching_df.empty:
        non_at_bat_events = ["スタメン", "スタ", "スタメン登録", "守備変更", "交代", "ベンチ", "試合前", "まとめ入力", "", "nan", "None"]
        
        detail_df = today_pitching_df[
            ~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"]) &
            ~today_pitching_df["結果"].astype(str).str.strip().isin(non_at_bat_events)
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
                res = str(row.get("結果", "")).strip()
                
                if res in non_at_bat_events or "スタ" in res:
                    continue
                
                if res in ["本塁打", "得点"]:
                    total_runs += 1

                if res in ["盗塁", "盗塁成功"]:
                    stolen_base_count += 1
                    continue
                elif res in ["盗塁死", "走塁死", "牽制死", "走塁記録", "進塁1", "進塁2", "進塁", "得点"]:
                    continue

                count += 1
                res_short = RES_SHORT_MAP.get(res, res[:2] if len(res) >= 2 else res)

                raw_dir = str(row.get("打球方向", ""))
                p_dir = raw_dir if raw_dir not in ["---", "nan", "None", "ー", ""] else ""

                disp_text = f"{p_dir}{res_short}"

                color_style = ""
                is_hit = res in ["単打", "二塁打", "三塁打", "本塁打"]

                if is_hit or res == "本塁打":
                    color_style = "color: red;" if res == "本塁打" else "color: blue;"

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

        if pos_key not in st.session_state or st.session_state[pos_key] not in pos_options:
            st.session_state[pos_key] = "未選択"
        cur_pos = st.session_state[pos_key]

        # 選手名の初期化
        if name_key not in st.session_state or not st.session_state[name_key] or st.session_state[name_key] == "相手投手":
            if i < len(opp_player_options):
                st.session_state[name_key] = opp_player_options[i]
            else:
                default_name = f"選手{order_num}"
                st.session_state[name_key] = default_name

        cur_name = st.session_state[name_key]

        # 🌟 session_state の値が選択肢に存在しない場合は追加してエラーを防止
        if cur_name and cur_name not in opp_player_options:
            opp_player_options.append(cur_name)

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
                    st.pills(
                        f"相手守備_{i}",
                        pos_options,
                        key=pos_key,
                        label_visibility="collapsed",
                    )

            with c_row[2]:
                name_btn_label = f"🟢 {cur_name} 🔽"
                with st.popover(name_btn_label, use_container_width=True):
                    st.markdown(f"##### {order_num}番 選手を選択")
                    st.pills(
                        f"相手選手_{i}",
                        opp_player_options,
                        key=name_key,
                        label_visibility="collapsed",
                    )

            with c_row[3]:
                history_text = opp_history_dict.get(order_num, "")
                st.markdown(
                    f"<div style='font-size:15px; line-height:1.4; padding-top:6px; color:#444; overflow-x:auto; white-space:nowrap;'>{history_text}</div>",
                    unsafe_allow_html=True,
                )

    dh_player_options = list(dict.fromkeys(["未選択"] + opp_player_options))
    dh_p_key = "opp_sn_dh_pitcher"

    default_dh_p = "未選択"
    for i in range(20):
        if st.session_state.get(f"opp_sp_{i}") in ["投", "投手", "P"]:
            p_n = st.session_state.get(f"opp_sn_{i}")
            if p_n and p_n in dh_player_options:
                default_dh_p = p_n
                break

    if dh_p_key not in st.session_state or st.session_state[dh_p_key] not in dh_player_options or st.session_state[dh_p_key] == "相手投手":
        st.session_state[dh_p_key] = default_dh_p

    cur_opp_dh_p = st.session_state[dh_p_key]
    # 🌟 選択中のDH投手名が選択肢にない場合は追加
    if cur_opp_dh_p and cur_opp_dh_p not in dh_player_options:
        dh_player_options.append(cur_opp_dh_p)

    with st.container(border=True):
        c_dh_row = st.columns([0.8, 2.5, 3.5, 5.2])
        with c_dh_row[0]:
            st.markdown("<div style='text-align:center; font-size:16px; font-weight:bold; padding-top:10px;'>投</div>", unsafe_allow_html=True)
        with c_dh_row[1]:
            st.markdown("<div style='text-align:center; font-size:14px; font-weight:bold; padding-top:10px; color:#4f46e5;'>🟢 投 (DH時)</div>", unsafe_allow_html=True)
        with c_dh_row[2]:
            name_btn_label = f"🟢 {cur_opp_dh_p} 🔽" if cur_opp_dh_p != "未選択" else "投手 (DH時) 選択 🔽"
            with st.popover(name_btn_label, use_container_width=True):
                st.markdown("##### ⚾ 相手投手を選択")
                st.pills(
                    "相手DH投手ピル",
                    dh_player_options,
                    key=dh_p_key,
                    label_visibility="collapsed",
                )
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
                for k in [f"opp_sn_{idx}", f"opp_sp_{idx}"]:
                    st.session_state.pop(k, None)
                st.rerun()
    with col_disp3:
        if st.button("➕ 追加 (最大20)", key="btn_opp_inc", use_container_width=True):
            if st.session_state["opp_batter_count"] < 20:
                st.session_state["opp_batter_count"] += 1
                st.rerun()

    st.divider()
    opp_bench_list = st.session_state.get("persistent_opp_bench", [])
    valid_opp_bench = [b for b in opp_bench_list if b in opp_player_options]

    if "opp_bench_selection_widget" not in st.session_state or (not st.session_state["opp_bench_selection_widget"] and valid_opp_bench):
        st.session_state["opp_bench_selection_widget"] = valid_opp_bench

    with st.expander(" 🚌 相手チーム ベンチ入りメンバー（控え）", expanded=True):
        selected_opp_bench = st.multiselect(
            "相手ベンチメンバー", 
            options=opp_player_options, 
            key="opp_bench_selection_widget"
        )
        st.session_state["persistent_opp_bench"] = selected_opp_bench

    if submit_detail:
        # ★【追加】未定義エラー（NameError）を防止する初期化ブロック
        sub_validation_error = None
        opp_rows_to_add = []

        require_dir_results = [
            "凡退(ゴロ)", "凡退(フライ)", "単打", "二塁打", "三塁打", "本塁打",
            "犠打(ゴロ)", "犠打(フライ)", "犠飛", "失策(ゴロ)", "失策(フライ)",
            "野選", "併殺打", "三重殺"
        ]

        must_advance_results = [
            "単打", "二塁打", "三塁打", 
            "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"
        ]
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

        p_res = st.session_state.get(f"pitching_quick_sr_{curr_counter}")
        target_fielder_pos_list = st.session_state.get(f"pitching_quick_sd_{curr_counter}", [])
        p_ef = st.session_state.get(f"pitching_quick_ef_{curr_counter}", "") or ""

        cur_1b_runner_name = st.session_state.get(f"p_runner_1b_{curr_counter}")
        cur_2b_runner_name = st.session_state.get(f"p_runner_2b_{curr_counter}")
        cur_3b_runner_name = st.session_state.get(f"p_runner_3b_{curr_counter}")

        cur_1b = cur_1b_runner_name not in [None, "なし", ""]
        cur_2b = cur_2b_runner_name not in [None, "なし", ""]
        cur_3b = cur_3b_runner_name not in [None, "なし", ""]

        res_1b = st.session_state.get(f"p_runner_1b_res_{curr_counter}")
        res_2b = st.session_state.get(f"p_runner_2b_res_{curr_counter}")
        res_3b = st.session_state.get(f"p_runner_3b_res_{curr_counter}")

        # ★ 修正箇所1: 本塁打の場合は走者結果が未選択なら自動で「得点」扱いとする
        if p_res == "本塁打":
            if cur_1b and not res_1b: res_1b = "得点"
            if cur_2b and not res_2b: res_2b = "得点"
            if cur_3b and not res_3b: res_3b = "得点"

        current_rbi = st.session_state.get(f"pitching_quick_si_{curr_counter}")
        
        r3_res_val = res_3b
        r1_is_run = (res_1b == "得点")
        r2_is_run = (res_2b == "得点")
        r3_is_run = (r3_res_val == "得点" or r3_res_val == "盗塁")
        p_run = (1 if r1_is_run else 0) + (1 if r2_is_run else 0) + (1 if r3_is_run else 0) + (1 if p_res == "本塁打" else 0)

        # ★ 修正箇所2: 本塁打の場合、打点が未設定であれば失点数 (1 + 走者数) を自動入力
        if p_res == "本塁打" and (current_rbi is None or current_rbi == 0):
            p_rbi = p_run
        else:
            p_rbi = int(current_rbi) if current_rbi is not None else 0

        current_er = st.session_state.get(f"pitching_quick_er_{curr_counter}")
        p_er = current_er if current_er is not None else 0

        # --------------------------------------------------
        # バリデーションチェック部
        # --------------------------------------------------
        if sub_validation_error:
            st.session_state["pitching_error_msg"] = sub_validation_error
            st.rerun()
        elif not p_res and not (res_1b or res_2b or res_3b) and not opp_rows_to_add:
            st.session_state["pitching_error_msg"] = "⚠️ 登録する内容（投球結果・走塁結果・メンバー変更等）を選択してください。"
            st.rerun()
        elif p_res and p_res in require_dir_results and not target_fielder_pos_list:
            st.session_state["pitching_error_msg"] = f"⚠️ 「{p_res}」を登録するには、打球方向を選択してください。"
            st.rerun()
        elif p_res and p_res in ["失策(ゴロ)", "失策(フライ)"] and not p_ef:
            st.session_state["pitching_error_msg"] = f"⚠️ 「{p_res}」を登録するには、エラー野手を選択してください。"
            st.rerun()
        # ★ 修正箇所3: 「elif p_res == '本塁打' and p_run == 0:」の不要なエラーチェックを削除
        elif p_res == "野選" and ((cur_1b and not res_1b) or (cur_2b and not res_2b) or (cur_3b and not res_3b)):
            st.session_state["pitching_error_msg"] = "⚠️ 野選が選択されています。ランナーの走塁結果（得点・進塁・走塁死）を選択してください。"
            st.rerun()
        elif cur_1b and p_res in must_advance_results and not res_1b:
            st.session_state["pitching_error_msg"] = "⚠️ 1塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        elif cur_2b and p_res in must_advance_results and not res_2b:
            st.session_state["pitching_error_msg"] = "⚠️ 2塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        elif cur_3b and p_res in must_advance_results and not res_3b:
            st.session_state["pitching_error_msg"] = "⚠️ 3塁走者がいます。走塁結果を選択してください。"
            st.rerun()
        else:
            target_pitcher_name = clean_player_name(input_name)
            batter_idx_int = st.session_state.get("opp_batter_index", 1)

            default_b_name = f"選手{batter_idx_int}"
            raw_batter_name = st.session_state.get(f"opp_sn_{batter_idx_int - 1}", default_b_name)
            current_batter_name = raw_batter_name if raw_batter_name not in ["None", "nan", "", "相手投手"] else default_b_name

            if cur_1b and cur_2b and cur_3b:
                runner_status = "満塁"
            elif cur_2b or cur_3b:
                runner_status = "得点圏"
            elif cur_1b:
                runner_status = "ランナー1塁"
            else:
                runner_status = "ランナーなし"

            records_to_save = list(opp_rows_to_add)
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
                elif p_res == "三重殺":
                    add_outs = 3
                elif p_res in [
                    "三振", "凡退(ゴロ)", "凡退(フライ)", "犠打(ゴロ)", "犠打(フライ)",
                    "犠飛", "野選", "牽制死", "盗塁死", "走塁死", "振り逃げ三振"
                ]:
                    add_outs = 1

                add_outs_total += add_outs  # ★【追加】打者のアウト数を合計アウト数に加算！

                if p_res in ["盗塁", "盗塁死"]:
                    target_fielder_pos_str = "捕"
                    fielder_display = clean_player_name(target_catcher_disp) if target_catcher_disp else ""

                s_cnt_val = st.session_state.get(f"p_s_count_{curr_counter}", 0)
                f_cnt_val = st.session_state.get(f"p_f_count_{curr_counter}", 0)
                b_cnt_val = st.session_state.get(f"p_b_count_{curr_counter}", 0)

                final_strike_count = s_cnt_val + f_cnt_val
                final_ball_count = b_cnt_val

                if p_res in ["四球", "死球"]:
                    final_ball_count += 1
                elif p_res:
                    final_strike_count += 1

                final_pitch_count = final_ball_count + final_strike_count

            if p_res:
                target_fielder_pos_str = "-".join(target_fielder_pos_list)

                # ★ 自チームのエラー野手名を取得
                ef_player_name = get_player_by_position(p_ef) if p_ef else ""
                error_fielder_disp = ef_player_name if ef_player_name else p_ef

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
                    "エラー野手": error_fielder_disp,  # ★ p_ef から error_fielder_disp (選手名) に変更
                    "結果": p_res,
                    "打点": p_rbi,
                    "自責点": p_er,
                    "勝敗": "ー",
                    "球数": final_pitch_count,
                    "ストライク": final_strike_count,
                    "ファールボール": f_cnt_val,
                    "ボール": b_cnt_val,
                    "ランナー状況": runner_status
                }
                records_to_save.append(rec)

            # --------------------------------------------------
            # 走者の登録レコード生成ループ
            # --------------------------------------------------
            for b_key in ["1b", "2b", "3b"]:
                r_name_raw = st.session_state.get(f"p_runner_{b_key}_{curr_counter}")
                r_res = st.session_state.get(f"p_runner_{b_key}_res_{curr_counter}")
                r_f = st.session_state.get(f"p_runner_{b_key}_fielder_{curr_counter}", "")

                # ★ 修正箇所4: 本塁打の場合、走者結果が未選択なら自動で「得点」としてレコード追加
                if p_res == "本塁打" and r_name_raw not in [None, "なし", ""] and not r_res:
                    r_res = "得点"

                if r_res:
                    if p_res in ["併殺打", "三重殺"]:
                        r_outs = 0
                    else:
                        r_outs = 1 if r_res in ["走塁死", "盗塁死", "牽制死"] else 0

                    fielder_disp = ""
                    if r_f:
                        found_f_name = get_player_by_position(r_f)
                        fielder_disp = found_f_name if found_f_name else f"({r_f})"

                    r_runner_name = clean_player_name(r_name_raw) if (r_name_raw and r_name_raw not in ["なし", "None", "nan", ""]) else current_batter_name
                    r_order_num = batter_idx_int
                    if r_name_raw and r_name_raw not in ["なし", "None", "nan", ""]:
                        clean_r = clean_player_name(r_name_raw)
                        for i in range(opp_count):
                            sn_val = st.session_state.get(f"opp_sn_{i}")
                            if sn_val and clean_player_name(sn_val) == clean_r:
                                r_order_num = i + 1
                                break

                    runner_rec = {
                        "日付": selected_date_str,
                        "グラウンド": final_ground,
                        "対戦相手": final_opp,
                        "試合種別": final_match_type,
                        "イニング": current_inn,
                        "投手名": target_pitcher_name,
                        "打順": r_order_num,
                        "打者名": r_runner_name,
                        "守備位置": r_f if r_f else "ー",
                        "打球方向": r_f if r_f else "ー",
                        "処理野手": fielder_disp,
                        "エラー野手": "",
                        "結果": r_res,
                        "打点": 0,
                        "自責点": 0,
                        "勝敗": "ー",
                        "ストライク": 0,
                        "ボール": 0,
                    }
                    records_to_save.append(runner_rec)
                    add_outs_total += r_outs

            if records_to_save:
                current_max_id = int(pd.to_numeric(df_pitching["ID"], errors="coerce").fillna(0).max()) if not df_pitching.empty and "ID" in df_pitching.columns else 0
                added_p_ids = []
                for rec in records_to_save:
                    current_max_id += 1
                    rec["ID"] = current_max_id
                    added_p_ids.append(current_max_id)

                updated_p_df = pd.concat([df_pitching, pd.DataFrame(records_to_save)], ignore_index=True)

                for col in TARGET_COLUMNS:
                    if col not in updated_p_df.columns:
                        updated_p_df[col] = 0 if col in ["ID", "打点", "自責点", "球数", "ストライク", "ファールボール", "ボール"] else ""

                save_df = updated_p_df[TARGET_COLUMNS].copy()
                target_url = st.session_state.get("my_spreadsheet_url", SPREADSHEET_URL)
                conn.update(spreadsheet=target_url, worksheet=ws_pitching, data=save_df)
                st.cache_data.clear()
                st.session_state["last_added_ids_pitching"] = added_p_ids

            # ★ 修正後：打席完了結果（PA_RESULTS_PITCHING）に含まれる場合のみ打順を進める
            if p_res and p_res in PA_RESULTS_PITCHING and p_res not in ["盗塁", "盗塁死", "牽制死", "暴投", "捕逸", "ボーク", "走塁死"]:
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
                st.session_state["p_persistent_runners"] = {"1b": None, "2b": None, "3b": None}
                try:
                    curr_idx = inn_options.index(current_inn)
                    if curr_idx < len(inn_options) - 2:
                        st.session_state["p_det_inn"] = inn_options[curr_idx + 2]
                except ValueError:
                    pass
            else:
                r1_next = "1b" if cur_1b_runner_name else None
                r2_next = "2b" if cur_2b_runner_name else None
                r3_next = "3b" if cur_3b_runner_name else None

                if p_res == "併殺打":
                    r1_next = None

                if cur_1b_runner_name and res_1b:
                    if res_1b in ["盗塁", "進塁1", "進塁"]:
                        r1_next = "2b"
                    elif res_1b == "進塁2":
                        r1_next = "3b"
                    elif res_1b in ["得点", "走塁死", "盗塁死", "牽制死"]:
                        r1_next = None

                if cur_2b_runner_name and res_2b:
                    if res_2b in ["盗塁", "進塁1", "進塁"]:
                        r2_next = "3b"
                    elif res_2b in ["進塁2", "得点", "走塁死", "盗塁死", "牽制死"]:
                        r2_next = None

                if cur_3b_runner_name and res_3b:
                    if res_3b in ["得点", "走塁死", "盗塁死", "牽制死", "盗塁", "進塁1", "進塁2", "進塁"]:
                        r3_next = None

                if p_res in ["四球", "死球"]:
                    r1_next = "2b" if cur_1b_runner_name else None
                    r2_next = "3b" if (cur_2b_runner_name and cur_1b_runner_name) else ("2b" if cur_2b_runner_name else None)
                    r3_next = None if (cur_3b_runner_name and cur_2b_runner_name and cur_1b_runner_name) else ("3b" if cur_3b_runner_name else None)

                b_next = None
                if p_res in ["単打", "四球", "死球", "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害", "振り逃げ三振"]:
                    b_next = "1b"
                elif p_res == "二塁打":
                    b_next = "2b"
                elif p_res == "三塁打":
                    b_next = "3b"

                next_runners = {"1b": None, "2b": None, "3b": None}

                if r1_next in next_runners: next_runners[r1_next] = cur_1b_runner_name
                if r2_next in next_runners: next_runners[r2_next] = cur_2b_runner_name
                if r3_next in next_runners: next_runners[r3_next] = cur_3b_runner_name
                if b_next in next_runners and current_batter_name:
                    next_runners[b_next] = current_batter_name

                st.session_state["p_persistent_runners"] = next_runners

            next_counter = curr_counter + 1
            st.session_state["p_clear_counter"] = next_counter

            PA_RESULTS = [
                "凡退(ゴロ)", "凡退(フライ)", "三振", "単打", "二塁打", "三塁打", "本塁打",
                "四球", "死球", "犠打(ゴロ)", "犠打(フライ)", "犠飛", "併殺打", "三重殺", "振り逃げ三振",
                "失策(ゴロ)", "失策(フライ)", "野選", "打撃妨害"
            ]
            is_pa_completed = bool(p_res and p_res in PA_RESULTS)
            
            if not is_pa_completed:
                st.session_state[f"p_b_count_{next_counter}"] = st.session_state.get(f"p_b_count_{curr_counter}", 0)
                st.session_state[f"p_s_count_{next_counter}"] = st.session_state.get(f"p_s_count_{curr_counter}", 0)
                st.session_state[f"p_f_count_{next_counter}"] = st.session_state.get(f"p_f_count_{curr_counter}", 0)
                st.session_state[f"p_pitch_count_{next_counter}"] = st.session_state.get(f"p_pitch_count_{curr_counter}", 0)

            st.success(f"✅ 記録を保存しました")
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
            pos_col = "守備位置" if "守備位置" in today_batting_df.columns else ("位置" if "位置" in today_batting_df.columns else "")
            pos_s = today_batting_df[pos_col].astype(str).str.strip() if pos_col else pd.Series("", index=today_batting_df.index)

            is_bat_excluded = (
                res_s.isin(exclude_res) | 
                res_s.str.contains(exclude_pattern, na=False) |
                pos_s.str.contains(exclude_pattern, na=False)
            )
            valid_batting_df = today_batting_df[~is_bat_excluded].copy()

        valid_pitching_df = pd.DataFrame()
        if not today_pitching_df.empty:
            mask_pit = (
                ~today_pitching_df["イニング"].astype(str).isin(["試合終了", "まとめ入力", "", "nan"]) &
                today_pitching_df["打順"].notna()
            )
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

                        ef_pos = str(row.get("エラー野手", ""))
                        if ef_pos and ef_pos not in ["nan", "None", ""]:
                            raw_res = f"{raw_res} [失策:{ef_pos}]"

                        fielder_name = str(row.get("処理野手", ""))
                        if fielder_name and fielder_name not in ["nan", "None", ""]:
                            clean_name = fielder_name.replace("(", "").replace(")", "")
                            res_text = f"{raw_res} [{clean_name}]"
                        else:
                            res_text = raw_res

                        rbi_val = pd.to_numeric(row.get("打点", 0), errors="coerce")
                        rbi = int(rbi_val) if pd.notna(rbi_val) else 0
                        if rbi > 0:
                            res_text = f"{res_text} 打点{rbi}"

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