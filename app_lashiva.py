# =========================
# Lashiva 库存管理系统（长表 + 自动承接 + 不落地“当日销量”）
# =========================
# 需求：
# - 库存表（长表）：至少包含 [名称(关联), 日期, SKU, 期初库存（承接）, 当日入库, 期末库存]
# - 销量表：至少包含 [SKU, 数量]，可选 [日期]
# - 换货表：至少包含 [原款SKU, 换货SKU]，可选 [数量, 日期]
# - 行为：先“昨日期末 → 今日期初（承接）”，再读取销量/换货，计算期末
# - 当日销量仅作为临时变量参与计算与展示，不写回库存表

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
import os
import re

st.set_page_config(page_title="Lashiva 库存管理系统", layout="centered")
st.title("Lashiva 库存管理系统")

# ========== 上传区 ==========
stock_file  = st.file_uploader("上传【库存表 CSV】（必选，长表：含 名称（关联） /日期 / SKU / 初期库存（承接） / 当日入库 / 期末库存 等列）", type=["csv"])
sales_files = st.file_uploader("上传【销量 CSV】（现仅支持一张上传）", type=["csv"], accept_multiple_files=True)

if "show_exchange" not in st.session_state:
    st.session_state.show_exchange = False
if st.button("有达人换货吗？（点击切换）"):
    st.session_state.show_exchange = not st.session_state.show_exchange

exchange_df = None
if st.session_state.show_exchange:
    st.info("请上传换货记录 CSV，需包含 原款SKU / 换货SKU / 日期 / 数量。")
    exchange_file = st.file_uploader("上传换货表（可选）", type=["csv"])
    if exchange_file:
        try:
            exchange_df = pd.read_csv(exchange_file)
            st.success("换货表已上传")
        except Exception as e:
            st.error(f"换货表读取失败：{e}")

st.divider()

# ========== 读取并规范库存表 ==========
if stock_file is None:
    st.info("请先上传库存表 CSV。")
    st.stop()

stock_df = pd.read_csv(stock_file)
stock_df.columns = [c.strip() for c in stock_df.columns]

# 必要列检查
need_cols = {"名称（关联）","日期", "SKU", "初期库存（承接）", "当日入库", "期末库存", "安全库存数"}
missing = need_cols - set(stock_df.columns)
if missing:
    st.error(f"库存表缺少必要列：{missing}")
    st.stop()

# 规范日期/SKU
stock_df["日期"] = pd.to_datetime(stock_df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
stock_df["SKU"]  = stock_df["SKU"].astype(str).str.strip().str.upper()

# 选择“工作日期”（默认取库存表里的最大日期，合理跳过周末）
available_dates = sorted(d for d in stock_df["日期"].dropna().unique())
default_date = available_dates[-1] if available_dates else datetime.today().strftime("%Y-%m-%d")
work_date = st.date_input("选择本次更新的【工作日期】", value=pd.to_datetime(default_date)).strftime("%Y-%m-%d")

# =======================
# 开始处理
# =======================
if st.button("开始处理"):

    if not sales_files:
        st.error("请至少上传 1 个销量 CSV。")
        st.stop()

    # ---------- ① 自动承接：昨日期末 → 今日期初（承接） ----------
    prev_date = (pd.to_datetime(work_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    prev_map = (
        stock_df.loc[stock_df["日期"] == prev_date]
        .drop_duplicates(subset=["SKU"], keep="last")
        .set_index("SKU")["期末库存"]
        .pipe(lambda s: pd.to_numeric(s, errors="coerce"))
        .to_dict()
    )

    today_mask = stock_df["日期"] == work_date

    if not today_mask.any():
        # 今天没有行：为全量 SKU 建行，并承接昨日期末（回退：期初基准 → 0）
        base = stock_df.drop_duplicates("SKU")

        new_today = pd.DataFrame({
            "SKU": base["SKU"],
            "日期": work_date,
            "初期库存（承接）": base["SKU"].map(prev_map),
            "当日入库": 0,
            "期末库存": pd.NA,
            "名称（关联）": base["SKU"].map(base.set_index("SKU")["名称（关联）"]) if "名称（关联）" in base.columns else pd.NA
        })

        if "初期库存（基准）" in base.columns:
            seed_map = base.set_index("SKU")["初期库存（基准）"]
            new_today["初期库存（承接）"] = new_today["初期库存（承接）"].fillna(
                new_today["SKU"].map(seed_map)
            )
        new_today["初期库存（承接）"] = pd.to_numeric(new_today["初期库存（承接）"], errors="coerce").fillna(0).astype(int)

        # 可选列跟随（如果库存表本身有这些列）
        for opt_col in ["名称（关联）", "安全库存数"]:
            if opt_col in stock_df.columns and opt_col not in new_today.columns:
                m = base.set_index("SKU")[opt_col].to_dict()
                new_today[opt_col] = new_today["SKU"].map(m)

        keep_cols = [c for c in stock_df.columns if c in new_today.columns]
        stock_df = pd.concat([stock_df, new_today[keep_cols]], ignore_index=True)
        today_mask = stock_df["日期"] == work_date
    else:
        # 今天已有行：只给“承接为空”的行补昨日期末（不覆盖人工值）
        idx_na = stock_df.index[today_mask & stock_df["初期库存（承接）"].isna()]
        stock_df.loc[idx_na, "初期库存（承接）"] = stock_df.loc[idx_na, "SKU"].map(prev_map)

        # 再回退“期初库存（基准）”；最后填 0
        if "初期库存（基准）" in stock_df.columns:
            seed_map = stock_df.drop_duplicates("SKU").set_index("SKU")["初期库存（基准）"].to_dict()
            still_na = stock_df.index[today_mask & stock_df["初期库存（承接）"].isna()]
            stock_df.loc[still_na, "初期库存（承接）"] = stock_df.loc[still_na, "SKU"].map(seed_map)

        stock_df.loc[today_mask, "初期库存（承接）"] = pd.to_numeric(
            stock_df.loc[today_mask, "初期库存（承接）"], errors="coerce"
        ).fillna(0).astype(int)

    # ---------- ② 读取并整合当日销量（多 CSV） ----------
    def read_sales_one(file_obj):
        df = pd.read_csv(file_obj)
        df.columns = [c.strip().lower() for c in df.columns]
        sku_col  = next((c for c in df.columns if c in ["sku", "sku编码", "style", "款式", "商品编码", "sku code", "sku_id"]), None)
        qty_col  = next((c for c in df.columns if c in ["数量", "qty", "quantity", "件数", "销售数量", "销量"]), None)
        date_col = next((c for c in df.columns if c in ["日期", "date", "order_date", "出库日期"]), None)
        if sku_col is None or qty_col is None:
            st.warning(f"文件 {getattr(file_obj, 'name', '(Unnamed)')} 未找到 SKU/数量 列，已跳过（列：{list(df.columns)}）")
            return None
        tmp = df[[sku_col, qty_col] + ([date_col] if date_col else [])].copy()
        tmp.columns = ["sku", "qty"] + (["date"] if date_col else [])
        tmp["sku"] = tmp["sku"].astype(str).str.strip().str.upper()
        tmp["qty"] = pd.to_numeric(tmp["qty"], errors="coerce").fillna(0).astype(int)
        if date_col:
            tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce").dt.strftime("%Y-%m-%d")
            tmp = tmp[tmp["date"] == work_date]
        tmp = tmp[tmp["sku"] != ""]
        # 如需保留负数退货，注释下一行
        tmp = tmp[tmp["qty"] > 0]
        return tmp[["sku", "qty"]]

    sales_list = [x for x in (read_sales_one(f) for f in sales_files) if x is not None]
    if not sales_list:
        st.error("没有可用的当日销量数据。")
        st.stop()

    sales_all = pd.concat(sales_list, ignore_index=True).groupby("sku", as_index=False)["qty"].sum()

    # ---------- ③ 可选：换货对销量 ± 调整 ----------
    if st.session_state.show_exchange and exchange_df is not None:
        ex = exchange_df.copy()
        ex.columns = [c.strip() for c in ex.columns]
        find = lambda choices: next((c for c in ex.columns if c.lower() in choices), None)
        orig_col = find({"原款sku","原款式","原款","original_sku","origsku","orig_sku", "申样sku"})
        new_col  = find({"换货sku","换货款式","换货","new_sku","newsku"})
        qty2_col = find({"数量","qty","quantity"})
        date2_col= find({"日期","date"})

        if not orig_col or not new_col:
            st.warning("换货 CSV 需包含可识别的 原款SKU / 换货SKU 列。本次不做换货调整。")
        else:
            if qty2_col is None:
                ex["数量"] = 1; qty2_col = "数量"
            if date2_col:
                ex["日期"] = pd.to_datetime(ex[date2_col], errors="coerce").dt.strftime("%Y-%m-%d")
                ex = ex[ex["日期"] == work_date]

            ex[orig_col] = ex[orig_col].astype(str).str.strip().str.upper()
            ex[new_col]  = ex[new_col].astype(str).str.strip().str.upper()
            ex[qty2_col] = pd.to_numeric(ex[qty2_col], errors="coerce").fillna(1).astype(int)

            adj_out = ex.groupby(new_col,  as_index=False)[qty2_col].sum().rename(columns={new_col: "sku", qty2_col: "plus_qty"})
            adj_in  = ex.groupby(orig_col, as_index=False)[qty2_col].sum().rename(columns={orig_col: "sku", qty2_col: "minus_qty"})

            adj = (sales_all.merge(adj_out, how="outer", on="sku")
                            .merge(adj_in,  how="outer", on="sku"))
            for col in ["qty", "plus_qty", "minus_qty"]:
                if col not in adj.columns:
                    adj[col] = 0
            adj[["qty","plus_qty","minus_qty"]] = adj[["qty","plus_qty","minus_qty"]].fillna(0).astype(int)
            adj["qty"] = adj["qty"] + adj["plus_qty"] - adj["minus_qty"]
            sales_all = adj[["sku", "qty"]]
            st.info("已根据换货记录对当日销量做出调整。")

    # ---------- ④ 计算当日期末（不在库存表落地“当日销量”列） ----------
    day_mask   = (stock_df["日期"] == work_date)
    sku_to_qty = dict(zip(sales_all["sku"], sales_all["qty"]))
    sold_today = stock_df.loc[day_mask, "SKU"].map(sku_to_qty).fillna(0).astype(int)

    start_val = pd.to_numeric(stock_df.loc[day_mask, "初期库存（承接）"], errors="coerce").fillna(0)
    in_val    = pd.to_numeric(stock_df.loc[day_mask, "当日入库"], errors="coerce").fillna(0)

    stock_df.loc[day_mask, "期末库存"] = (start_val + in_val - sold_today).clip(lower=0).astype(int)

    # ---------- ⑤ 当日视图 + 合计 ----------
    base_cols = ["名称（关联）", "SKU", "初期库存（承接）", "当日入库", "期末库存"] 
    today_view = stock_df.loc[day_mask, base_cols].copy()
    today_view.insert(3, "当日销量", sold_today.values)
    today_view = today_view.sort_values("SKU").reset_index(drop=True)
    today_view.index += 1

    total_row = pd.DataFrame([[
        "—",
        "—",
        int(pd.to_numeric(stock_df.loc[day_mask, "初期库存（承接）"], errors="coerce").fillna(0).sum()),
        int(pd.to_numeric(stock_df.loc[day_mask, "当日入库"], errors="coerce").fillna(0).sum()),
        int(sold_today.sum()),
        int(pd.to_numeric(stock_df.loc[day_mask, "期末库存"], errors="coerce").fillna(0).sum())
    ]], columns=["名称（关联）","SKU","初期库存（承接）","当日入库","当日销量","期末库存"])

    summary_df = pd.concat([today_view, total_row], ignore_index=True)

    # 网页美化
    st.markdown(f'<div class="title-main">库存更新结果（{work_date}）</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("期初库存（合计）", f"{int(total_row['初期库存（承接）'].iloc[0])}")
    c2.metric("当日销量（合计）", f"{int(total_row['当日销量'].iloc[0])}")
    c3.metric("期末库存（合计）", f"{int(total_row['期末库存'].iloc[0])}")

    low_cnt = 0
    if "安全库存数" in stock_df.columns:
        m = (stock_df["日期"]==work_date)
        safe = pd.to_numeric(stock_df.loc[m, "安全库存数"], errors="coerce")
        endv = pd.to_numeric(stock_df.loc[m, "期末库存"], errors="coerce")
        low_cnt = int((endv < safe).sum())

    sku_count = today_view.shape[0]

    st.write(
        f"SKU 数：**{sku_count}**  "
        + (f"｜ 低库存 SKU：**{low_cnt}**" if low_cnt > 0 else "｜ **库存健康**")
    )

    # 条件样式（低库存/入库/零销量）
    def color_rules(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame('', index=df.index, columns=df.columns)
        if "安全库存数" in stock_df.columns:
            safemap = (stock_df[stock_df["日期"]==work_date]
                        .drop_duplicates("SKU")
                        .set_index("SKU")["安全库存数"])
            safev = df["SKU"].map(safemap).astype(float)
            low_mask = (pd.to_numeric(df["期末库存"], errors="coerce") < safev.fillna(float('inf')))
            styles.loc[low_mask, ["期末库存"]] = "background-color:#FFF7E6; color:#7C2D12;"  # 橙

        zero_sales = (pd.to_numeric(df["当日销量"], errors="coerce").fillna(0) == 0)
        styles.loc[zero_sales, ["当日销量"]] = "color:#94A3B8;"  # 灰

        in_green = (pd.to_numeric(df["当日入库"], errors="coerce").fillna(0) > 0)
        styles.loc[in_green, ["当日入库"]] = "background-color:#ECFDF5; color:#065F46;"  # 绿

        styles.loc[df["SKU"]=="—", :] = "font-weight:700; background:#F8FAFC;"
        return styles


    
    numeric_cols = ["初期库存（承接）","当日入库","当日销量","期末库存"]
    styled = summary_df.style \
        .format("{:,.0f}", subset=numeric_cols) \
        .set_properties(**{"white-space":"nowrap"}) \
        .apply(color_rules, axis=None)

    # ---------- ⑥ 展示 & 下载 ----------
    st.subheader(f"库存更新结果（{work_date}）")
    st.dataframe(styled, use_container_width=True)
    

    st.subheader("一键复制当前期末库存")
    st.code("\n".join(today_view.loc[today_view["SKU"]!="—","期末库存"].astype(str).tolist()), language="text")


    csv_out = summary_df.to_csv(index_label="序号").encode("utf-8-sig")
    st.download_button(label="下载库存更新表 CSV", data=csv_out, file_name=f"库存更新结果_{work_date}.csv", mime="text/csv")

    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index_label="序号")
    st.download_button(label="下载库存更新表 Excel", data=out.getvalue(), file_name="库存更新结果.xlsx")

    # ---------- ⑦ 历史记录 ----------
    history_file = "upload_history.csv"
    record = {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "工作日期": work_date,
        "库存文件": stock_file.name if stock_file else "",
        "销量文件数": len(sales_files) if sales_files else 0,
        "是否开启换货区": st.session_state.show_exchange
    }
    try:
        if os.path.exists(history_file):
            hist = pd.read_csv(history_file)
            hist = pd.concat([hist, pd.DataFrame([record])], ignore_index=True)
        else:
            hist = pd.DataFrame([record])
        hist.to_csv(history_file, index=False, encoding="utf-8-sig")
        st.success("已记录历史。")
    except OSError as e:
        st.warning(f"历史记录未落地（环境只读）。详情：{e}")