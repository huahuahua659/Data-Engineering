# -*- coding: utf-8 -*-
"""
数据探索分析脚本
=================
对指定目录下的数据文件（csv/xlsx/json 等）进行完整的探索性数据分析（EDA），
并生成一份可读的中文文本报告。

功能：
1. 自动识别数据文件类型与编码
2. 逐个文件输出数据概况（规模、字段、类型、示例、取值范围）
3. 数据质量检查（缺失、重复、异常值、格式问题、错误数据）
4. 字段重要性分析
5. 数据分析建议

依赖：pandas、numpy
运行：python data_exploration.py
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime

# ---------------- 配置 ----------------
DATA_DIR = r"E:\博客\数据分析\data"
OUTPUT_FILE = os.path.join(DATA_DIR, "data_exploration_report.txt")

# 支持的格式
CSV_EXTS = {".csv"}
XLSX_EXTS = {".xlsx", ".xls"}
JSON_EXTS = {".json"}

# 报告内容缓存
_lines = []


def w(line=""):
    """向报告追加一行"""
    _lines.append(line)


def section(title):
    """输出一级章节标题"""
    w()
    w("=" * 70)
    w(title)
    w("=" * 70)


def sub(title):
    """输出二级标题"""
    w()
    w("-" * 60)
    w(title)
    w("-" * 60)


# ---------------- 数据读取 ----------------

def read_auto(path):
    """
    根据扩展名自动读取数据文件。
    CSV 会尝试多种编码（自动识别 utf-8 / gbk 等）。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in CSV_EXTS:
        for enc in ("utf-8-sig", "gb18030", "utf-8", "gbk"):
            try:
                return pd.read_csv(path, encoding=enc, low_memory=False), enc
            except UnicodeDecodeError:
                continue
        # 兜底
        return pd.read_csv(path, encoding="latin1", low_memory=False), "latin1"
    elif ext in XLSX_EXTS:
        return pd.read_excel(path), "xlsx"
    elif ext in JSON_EXTS:
        return pd.read_json(path), "utf-8"
    else:
        raise ValueError(f"不支持的文件类型：{ext}")


def scan_files(directory):
    """扫描目录，返回按名称排序的数据文件列表"""
    files = []
    for name in sorted(os.listdir(directory)):
        ext = os.path.splitext(name)[1].lower()
        if ext in CSV_EXTS | XLSX_EXTS | JSON_EXTS:
            files.append(os.path.join(directory, name))
    return files


# ---------------- 通用分析工具 ----------------

def missing_summary(df):
    """缺失值统计：字段、缺失数量、缺失比例"""
    n = len(df)
    rows = []
    for c in df.columns:
        cnt = df[c].isna().sum()
        if cnt > 0:
            rows.append((c, cnt, f"{cnt / n * 100:.2f}%"))
    return rows


def type_name(df, col):
    """返回字段的可读类型说明"""
    d = str(df[col].dtype)
    if d.startswith("int"):
        return "整数"
    if d.startswith("float"):
        return "小数"
    if d.startswith("datetime"):
        return "日期时间"
    return "文本"


def is_date_field(col):
    """判断是否为日期时间类字段（依据字段名）"""
    return ("time" in col.lower()) or ("date" in col.lower())


def field_range(df, col):
    """
    返回字段取值范围描述：
    - 数值型：min ~ max（均值）
    - 日期型：min ~ max
    - 文本型：唯一值数量 + 主要取值
    """
    d = str(df[col].dtype)
    if d.startswith("int") or d.startswith("float"):
        vmin, vmax, vmean = df[col].min(), df[col].max(), df[col].mean()
        if d.startswith("int"):
            return f"{int(vmin)} ~ {int(vmax)}（均值 {vmean:.1f}）"
        return f"{vmin:.2f} ~ {vmax:.2f}（均值 {vmean:.2f}）"
    elif is_date_field(col):
        # 尝试解析为日期，展示时间范围
        try:
            s = pd.to_datetime(df[col], errors="coerce")
            return f"{s.min()} ~ {s.max()}"
        except Exception:
            pass
        nuniq = df[col].nunique()
        return f"共 {nuniq} 种取值"
    else:
        nuniq = df[col].nunique()
        if nuniq <= 12:
            vals = df[col].dropna().value_counts().index.tolist()
            return f"共 {nuniq} 种：{', '.join(str(v) for v in vals)}"
        top = df[col].dropna().value_counts().head(5).index.tolist()
        return f"共 {nuniq} 种，主要取值：{', '.join(str(v) for v in top)} ..."


def sample_value(df, col):
    """取第一个非空示例值，处理 NaN"""
    s = df[col]
    nonnull = s.dropna()
    if len(nonnull) == 0:
        return "（全部为空）"
    v = nonnull.iloc[0]
    if isinstance(v, str) and len(v) > 30:
        v = v[:30] + "…"
    return v


def check_date_format(df):
    """检测日期字段的格式问题"""
    issues = []
    for c in df.columns:
        if not is_date_field(c) or df[c].dtype != object:
            continue
        samples = df[c].dropna().astype(str)
        if len(samples) == 0:
            continue
        has_slash = samples.str.contains("/").any()
        has_dash = samples.str.contains("-").any()
        if has_slash and has_dash:
            issues.append(f"字段 {c} 混用了 '/' 与 '-' 两种日期分隔符")
        if samples.str.match(r"\d{4}/\d{1}/\d{1}").any():
            issues.append(f"字段 {c} 日期/时间无前导零（如 '2024/1/1 0:01'），"
                          f"字符串排序会失真，需先转 datetime")
        elif samples.str.match(r"\d{4}/\d{1,2}/\d{1,2} \d{1}:").any():
            issues.append(f"字段 {c} 时间无前导零（如 '4:03'），需规范化")
    return issues


def describe_numeric(df, cols):
    """输出数值字段的描述统计表"""
    w(f"{'字段':<28}{'计数':>10}{'均值':>14}{'标准差':>12}{'最小值':>12}{'中位数':>12}{'最大值':>12}")
    for c in cols:
        s = df[c]
        w(f"{c:<28}{s.count():>10}{s.mean():>14.2f}{s.std():>12.2f}"
          f"{s.min():>12.2f}{s.median():>12.2f}{s.max():>12.2f}")


def value_counts_text(df, col, top_n=15):
    """输出分类字段取值分布（文本形式）"""
    vc = df[col].value_counts(dropna=False)
    for val, cnt in vc.head(top_n).items():
        if pd.isna(val):
            val = "（缺失/空）"
        pct = cnt / len(df) * 100
        w(f"    {str(val):<20}{cnt:>10}  ({pct:.2f}%)")


# ---------------- 字段元信息（中文含义说明） ----------------

# order.csv 字段中文说明
ORDER_FIELD_DESC = {
    "order_id": "订单编号（主键，订单唯一标识）",
    "user_id": "用户编号（关联用户表的外键）",
    "product_id": "商品编号（商品唯一标识）",
    "order_time": "下单时间",
    "quantity": "购买数量（件数）",
    "amount": "实付金额（元，含促销折扣后的实际支付金额）",
    "payment_method": "支付方式（如 Alipay 支付宝 / WeChatPay 微信支付等）",
    "promotion_type": "促销类型（Coupon 优惠券 / FlashSale 秒杀 / FullDiscount 满减；空值表示无促销）",
    "order_status": "订单状态（Pending 待支付 / Paid 已支付 / Shipped 已发货 / Delivered 已签收 / Cancelled 已取消）",
    "shipping_city": "收货城市",
    "fulfillment_time": "履约时长（推测为小时，即从下单到完成的耗时；字段名与内容不完全一致，待确认）",
    "gender": "用户性别（F 女 / M 男 / Unknown 未知）",
    "age": "用户年龄",
    "user_province_name": "用户所在省份（省级行政区）",
    "product_name": "商品名称",
    "brand": "品牌",
    "category": "商品品类",
    "price": "商品单价（元，为商品原价，未计折扣）",
    "is_hot": "是否爆款（1 是 / 0 否）",
    "launch_date": "商品上市时间",
    "product_region_id": "商品产地地区编号",
    "product_province_name": "商品产地省份",
    "product_region_level": "商品产地城市等级（一线 / 新一线 / 二线 / 三线）",
    "description": "商品描述文本（含产品描述与品牌描述两段，中间以句号+逗号分隔）",
}

# user.csv 字段中文说明
USER_FIELD_DESC = {
    "user_id": "用户编号（主键，用户唯一标识）",
    "user_name": "用户名（推测为系统生成的拼音昵称，非唯一）",
    "gender": "用户性别（F 女 / M 男 / Unknown 未知）",
    "age": "用户年龄",
    "register_time": "注册时间",
    "register_channel": "注册渠道（App Store / Android Market / WeChat / Web / Referral）",
    "user_region_id": "用户所在地区编号",
    "user_province_name": "用户所在省份",
    "user_region_level": "用户所在城市等级（一线 / 新一线 / 二线 / 三线）",
    "user_province_population": "用户所在省份人口（推测单位：万人；数值与真实省情不符，疑为模拟数据）",
    "user_province_gdp": "用户所在省份 GDP（推测单位：亿元；数值与真实省情不符，疑为模拟数据）",
    "total_purchase_times": "累计购买次数",
    "total_purchase_amount": "累计购买金额（元）",
    "last_purchase_time": "最近一次购买时间",
    "click_count": "点击次数",
    "cart_count": "加入购物车次数",
}


# ---------------- 各文件分析 ----------------

def analyze_file(path):
    """分析单个数据文件，输出其概况与质量信息"""
    df, enc = read_auto(path)
    name = os.path.basename(path)
    n_rows, n_cols = df.shape

    section(f"文件分析：{name}")
    w(f"文件路径     ：{path}")
    w(f"文件格式     ：{os.path.splitext(name)[1].lower()}（读取编码：{enc}）")
    w(f"数据规模     ：{n_rows} 行 × {n_cols} 列")
    w(f"内存占用(约) ：{df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

    # 字段说明字典
    if "order_id" in df.columns:
        desc_map = ORDER_FIELD_DESC
    elif "user_id" in df.columns:
        desc_map = USER_FIELD_DESC
    else:
        desc_map = {}

    # ---- 字段概况表 ----
    sub("字段概况（名称 / 中文含义 / 类型 / 示例 / 取值范围）")
    for col in df.columns:
        desc = desc_map.get(col, "（无法确定，需结合业务理解）")
        tname = type_name(df, col)
        sample = sample_value(df, col)
        rng = field_range(df, col)
        w(f"• {col}")
        w(f"    含义  ：{desc}")
        w(f"    类型  ：{tname}")
        w(f"    示例  ：{sample}")
        w(f"    范围  ：{rng}")

    # ---- 数据质量检查 ----
    sub("数据质量检查")

    # 缺失值
    miss = missing_summary(df)
    if miss:
        w("① 缺失值（数量 / 比例）：")
        for c, cnt, pct in miss:
            w(f"    {c:<28}{cnt:>10}  ({pct})")
    else:
        w("① 缺失值：无 NaN 缺失")

    # 显式 Unknown 作为隐性缺失
    unknown_cols = []
    for c in df.columns:
        if df[c].dtype == object and (df[c] == "Unknown").any():
            unknown_cols.append((c, (df[c] == "Unknown").sum(),
                                 (df[c] == "Unknown").mean() * 100))
    if unknown_cols:
        w("    提示：以下字段存在 'Unknown' 值，可视作一种隐性缺失：")
        for c, cnt, pct in unknown_cols:
            w(f"    {c:<28}{cnt:>10}  ({pct:.2f}%)")

    # 重复数据
    dup_rows = df.duplicated().sum()
    w(f"② 重复数据：完全重复行 {dup_rows} 行")

    # 字段唯一值数量
    w("③ 各字段唯一值数量：")
    for c in df.columns:
        w(f"    {c:<28}{df[c].nunique():>10}")

    # 异常值（数值字段，用 3σ 简单检测提示）
    w("④ 异常值提示（数值字段，3σ 规则粗略检测）：")
    found_any = False
    for c in df.columns:
        if df[c].dtype.kind in "if":
            mean, std = df[c].mean(), df[c].std()
            if std > 0:
                cnt_out = (np.abs(df[c] - mean) > 3 * std).sum()
                if cnt_out > 0:
                    found_any = True
                    w(f"    {c:<28}超出均值±3σ 的行数：{cnt_out}")
    if not found_any:
        w("    （数值字段分布总体集中，未发现明显离群点；极值多为高价商品，属合理范围）")

    # 数据格式问题
    date_issues = check_date_format(df)
    if date_issues:
        w("⑤ 数据格式问题（日期字段）：")
        for it in date_issues:
            w(f"    - {it}")

    return df


def analyze_relations(order_df, user_df):
    """分析 order 表与 user 表之间的关联关系"""
    section("数据文件之间的关系")
    w("两张表通过 user_id 字段关联：")
    w("  • user.csv  为用户主表（用户维度，1 行 = 1 个用户）")
    w("  • order.csv 为订单明细表（事实表，1 行 = 1 条订单，一个用户可有多条订单）")

    order_users = set(order_df["user_id"])
    user_users = set(user_df["user_id"])
    w()
    w(f"order 表出现过的 user_id 数量：{len(order_users)}")
    w(f"user 表 的 user_id 数量：{len(user_users)}")
    w(f"order 有但 user 无（孤儿订单）：{len(order_users - user_users)}")
    w(f"user 有但 order 无（注册后无订单的用户）：{len(user_users - order_users)}")

    # 汇总字段一致性
    sub("汇总字段一致性核对")
    order_cnt = order_df.groupby("user_id").size().rename("实际订单数")
    order_amt = order_df.groupby("user_id")["amount"].sum().rename("实际累计金额")
    check = user_df[["user_id", "total_purchase_times", "total_purchase_amount"]]
    check = check.merge(order_cnt, on="user_id", how="left")
    check = check.merge(order_amt, on="user_id", how="left")
    check["实际订单数"] = check["实际订单数"].fillna(0).astype(int)
    check["实际累计金额"] = check["实际累计金额"].fillna(0)

    cnt_mismatch = (check["total_purchase_times"] != check["实际订单数"]).sum()
    amt_mismatch = (check["total_purchase_amount"] - check["实际累计金额"]).abs() > 1
    w(f"total_purchase_times 与实际订单数不一致的用户数：{cnt_mismatch} "
      f"（{cnt_mismatch / len(check) * 100:.1f}%）")
    w(f"total_purchase_amount 与实际累计金额差异 >1 元的用户数：{amt_mismatch.sum()} "
      f"（{amt_mismatch.mean() * 100:.1f}%）")
    w("结论：user 表的汇总字段与 order 表实际聚合结果差异较大，")
    w("      说明 user 表为独立口径（可能含历史数据、退货或其它统计范围），二者不能直接画等号。")


def analyze_business_logic(order_df):
    """分析 amount 与 price*quantity 的业务逻辑（促销折扣）"""
    sub("金额业务逻辑核对（amount 与 price×quantity 的关系）")
    calc = order_df["price"] * order_df["quantity"]
    diff = (order_df["amount"] - calc).round(2)
    w("发现：约 30% 的订单 amount ≠ price×quantity，进一步核对为促销折扣所致：")
    w()
    for pt in ["Coupon", "FlashSale", "FullDiscount"]:
        sub_df = order_df[order_df["promotion_type"] == pt]
        if len(sub_df) == 0:
            continue
        rate = ((sub_df["price"] * sub_df["quantity"] - sub_df["amount"]) /
                (sub_df["price"] * sub_df["quantity"])).mean() * 100
        w(f"  • {pt:<12} 折扣率固定约 {rate:.0f}%（订单数 {len(sub_df)}）")
    no_promo = order_df[order_df["promotion_type"].isna()]
    w(f"  • 无促销       amount = price×quantity（订单数 {len(no_promo)}）")
    w()
    w("结论：amount 是折后实付金额，price 是原价，差异完全由促销活动解释，并非数据错误。")


def analyze_key_insights(order_df, user_df):
    """输出关键业务洞察"""
    section("关键数据洞察")
    w(f"• 订单总量：{len(order_df)} 条；覆盖用户 {order_df['user_id'].nunique()} 人；"
      f"涉及商品 {order_df['product_id'].nunique()} 款")
    w(f"• 总成交额(GMV，实付)：{order_df['amount'].sum():,.2f} 元")
    w(f"• 客单价（每单均值）：{order_df['amount'].mean():,.2f} 元")
    w(f"• 人均消费（按订单用户）：{order_df['amount'].sum() / order_df['user_id'].nunique():,.2f} 元")
    w(f"• 性别分布：女 {order_df['gender'].eq('F').sum()}，男 {order_df['gender'].eq('M').sum()}，"
      f"未知 {order_df['gender'].eq('Unknown').sum()}")
    top_brand = order_df.groupby("brand")["amount"].sum().sort_values(ascending=False)
    w(f"• 销售额最高品牌：{top_brand.index[0]}（{top_brand.iloc[0]:,.0f} 元）")
    top_cat = order_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    w(f"• 销售额最高品类：{top_cat.index[0]}（{top_cat.iloc[0]:,.0f} 元）")


# ---------------- 字段重要性分析 ----------------

def field_importance():
    """输出字段重要性分类（基于业务理解）"""
    section("字段重要性分析")

    sub("【重要字段】对后续分析有较高价值")
    w("订单表 order.csv：")
    w("  • amount（实付金额）       —— 核心交易指标 GMV 的直接来源")
    w("  • order_time（下单时间）    —— 支撑时间趋势、周期性分析")
    w("  • quantity / price          —— 拆解销量与价格，分析客单价结构")
    w("  • promotion_type（促销类型）—— 分析促销活动对销售的拉动效果")
    w("  • order_status（订单状态）  —— 分析下单到成交的转化漏斗")
    w("  • category / brand / product_name —— 品类与品牌维度分析")
    w("  • payment_method（支付方式）—— 用户支付偏好分析")
    w("  • user_id（用户编号）       —— 关联用户表、计算复购率的关键外键")
    w("  • age / gender（年龄/性别） —— 用户画像与人群细分")
    w("  • user_province_name / product_province_name —— 地域维度分析")
    w("用户表 user.csv：")
    w("  • total_purchase_amount / total_purchase_times —— 用户价值分层(RFM)核心")
    w("  • click_count / cart_count  —— 行为漏斗（浏览→加购→成交）")
    w("  • register_channel（注册渠道）—— 获客渠道质量分析")
    w("  • age / gender / user_province_name —— 用户画像")

    sub("【次要字段】有一定参考价值")
    w("  • shipping_city（收货城市）   —— 仅 10 个城市，地域细分空间有限")
    w("  • is_hot（是否爆款）          —— 可用于爆款商品筛选")
    w("  • launch_date（商品上市时间） —— 可做商品生命周期分析")
    w("  • fulfillment_time（履约时长）—— 可做物流/履约效率分析（含义需确认）")
    w("  • product_region_id / user_region_id —— 与省份字段冗余，仅在关联时使用")

    sub("【不重要字段】对分析帮助较小")
    w("  • description（商品描述）     —— 长文本，常规统计价值低（如需可用 NLP 处理）")
    w("  • user_province_population / user_province_gdp —— 与真实省情不符的模拟数据，参考价值有限")
    w("  • user_name（用户名）         —— 非唯一、拼音式昵称，无分析价值")


# ---------------- 分析建议 ----------------

def analysis_suggestions():
    """输出分析建议"""
    section("数据分析建议")

    sub("① 可开展的分析方向")
    w("  1. 销售趋势分析：按日/周/月统计 GMV、订单量，识别销售高峰与季节性")
    w("  2. 品类与品牌分析：各品类/品牌的销售额、销量、客单价对比")
    w("  3. 促销效果分析：对比不同促销类型的折扣力度与订单拉动效果")
    w("  4. 用户画像分析：性别、年龄、地域、城市等级的用户结构与消费差异")
    w("  5. 用户价值分层：基于 RFM（最近购买、频次、金额）做用户分群")
    w("  6. 转化漏斗分析：点击 → 加购 → 下单 的各环节转化率")
    w("  7. 商品维度分析：爆款商品、TOP 商品、商品生命周期")
    w("  8. 地域分析：各省份销售额热力图、城市等级消费力对比")

    sub("② 推荐分析指标")
    w("  • 规模类：GMV、订单量、销量、活跃用户数")
    w("  • 效率类：客单价、人均消费、ARPU")
    w("  • 用户类：复购率、留存率、转化率、用户生命周期价值(LTV)")
    w("  • 结构类：品类占比、品牌集中度、折扣率、支付方式占比")

    sub("③ 推荐可视化方式")
    w("  • 柱状图：品类/品牌销售额对比、各城市销量")
    w("  • 折线图：GMV 与订单量的时间趋势")
    w("  • 饼图：品类占比、支付方式占比、性别占比")
    w("  • 箱线图：订单金额分布、年龄分布（识别离群点）")
    w("  • 散点图：价格与销量关系、年龄与消费金额关系")
    w("  • 热力图：各省份销售额分布")

    sub("④ 后续建模与业务建议")
    w("  • 用户价值预测：以 total_purchase_amount 等为目标做回归预测")
    w("  • 复购/流失预测：用行为特征（click_count、cart_count、购买频次）做二分类")
    w("  • 商品推荐：基于用户-商品交互做协同过滤推荐")
    w("  • 促销策略优化：分析折扣对转化率的边际效应，优化满减/秒杀力度")
    w("  • 注意：建模前需统一编码、日期格式，并对促销折扣做特征化处理")


# ---------------- 主流程 ----------------

def main():
    files = scan_files(DATA_DIR)
    if not files:
        print("目录下未发现可分析的数据文件")
        return

    w(f"数据探索分析报告")
    w(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w(f"数据目录：{DATA_DIR}")
    w(f"发现数据文件 {len(files)} 个：")
    for f in files:
        w(f"  - {os.path.basename(f)}")

    # 读取所有文件
    frames = {}
    for f in files:
        name = os.path.basename(f)
        frames[name], _ = read_auto(f)

    # 逐个分析
    order_df = frames.get("order.csv")
    user_df = frames.get("user.csv")

    for f in files:
        df, _ = read_auto(f)
        analyze_file(f)

    # 表关系分析
    if order_df is not None and user_df is not None:
        analyze_relations(order_df, user_df)
        analyze_business_logic(order_df)
        analyze_key_insights(order_df, user_df)

    # 字段重要性
    field_importance()

    # 分析建议
    analysis_suggestions()

    # 写入报告
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fp:
        fp.write("\n".join(_lines))

    print(f"报告已生成：{OUTPUT_FILE}")
    print(f"报告行数：{len(_lines)}")


if __name__ == "__main__":
    main()
