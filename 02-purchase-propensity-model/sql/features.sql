WITH hist AS (
  SELECT
    user_id,
    /* ===== RFM ===== */
    DATEDIFF('2024-11-01', MAX(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN order_time END)) AS recency_days,
    SUM(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN 1 ELSE 0 END) AS order_count,
    SUM(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN amount ELSE 0 END) AS total_amount,
    AVG(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN amount END) AS avg_amount,
    MAX(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN amount END) AS max_amount,
    /* ===== 商品行为 ===== */
    SUM(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN quantity ELSE 0 END) AS total_quantity,
    COUNT(DISTINCT CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN DATE(order_time) END) AS active_days,
    COUNT(DISTINCT CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN product_id END) AS product_cnt,
    COUNT(DISTINCT CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN category END) AS category_cnt,
    COUNT(DISTINCT CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN brand END) AS brand_cnt,
    /* ===== 营销偏好 ===== */
    AVG(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN CASE WHEN promotion_type IS NOT NULL THEN 1 ELSE 0 END END) AS promotion_rate,
    AVG(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN is_hot END) AS hot_rate,
    /* ===== 订单质量 ===== */
    AVG(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) AS cancel_rate,
    AVG(CASE WHEN order_status IN ('Paid', 'Shipped', 'Delivered') THEN fulfillment_time END) AS avg_fulfillment,
    /* ===== 最近活跃度 ===== */
    SUM(CASE WHEN order_time >= '2024-10-01' AND order_status IN ('Paid', 'Shipped', 'Delivered') THEN 1 ELSE 0 END) AS order_cnt_30d,
    SUM(CASE WHEN order_time >= '2024-09-01' AND order_status IN ('Paid', 'Shipped', 'Delivered') THEN 1 ELSE 0 END) AS order_cnt_60d,
    SUM(CASE WHEN order_time >= '2024-08-01' AND order_status IN ('Paid', 'Shipped', 'Delivered') THEN 1 ELSE 0 END) AS order_cnt_90d,
    SUM(CASE WHEN order_time >= '2024-10-01' AND order_status IN ('Paid', 'Shipped', 'Delivered') THEN amount ELSE 0 END) AS amount_30d,
    SUM(CASE WHEN order_time >= '2024-08-01' AND order_status IN ('Paid', 'Shipped', 'Delivered') THEN amount ELSE 0 END) AS amount_90d
  FROM
    `order`
  WHERE
    order_time >= '2024-05-01'
    AND order_time < '2024-11-01'
  GROUP BY
    user_id
),
label AS (
  SELECT
    user_id,
    1 AS y
  FROM
    `order`
  WHERE
    order_time >= '2024-11-01'
    AND order_time < '2025-01-01'
    AND order_status IN ('Paid', 'Shipped', 'Delivered')
  GROUP BY
    user_id
) SELECT
  u.user_id,
  u.gender,
  u.age,
  u.register_channel,
  u.user_region_level,
  u.user_province_name,
  COALESCE(h.recency_days, 999) AS recency_days,
  COALESCE(h.order_count, 0) AS order_count,
  COALESCE(h.total_amount, 0) AS total_amount,
  COALESCE(h.avg_amount, 0) AS avg_amount,
  COALESCE(h.max_amount, 0) AS max_amount,
  COALESCE(h.total_quantity, 0) AS total_quantity,
  COALESCE(h.active_days, 0) AS active_days,
  COALESCE(h.product_cnt, 0) AS product_cnt,
  COALESCE(h.category_cnt, 0) AS category_cnt,
  COALESCE(h.brand_cnt, 0) AS brand_cnt,
  COALESCE(h.promotion_rate, 0) AS promotion_rate,
  COALESCE(h.hot_rate, 0) AS hot_rate,
  COALESCE(h.cancel_rate, 0) AS cancel_rate,
  COALESCE(h.avg_fulfillment, 0) AS avg_fulfillment,
  COALESCE(h.order_cnt_30d, 0) AS order_cnt_30d,
  COALESCE(h.order_cnt_60d, 0) AS order_cnt_60d,
  COALESCE(h.order_cnt_90d, 0) AS order_cnt_90d,
  COALESCE(h.amount_30d, 0) AS amount_30d,
  COALESCE(h.amount_90d, 0) AS amount_90d,
  COALESCE(l.y, 0) AS y
FROM
  `user` u
  LEFT JOIN hist h ON u.user_id = h.user_id
  LEFT JOIN label l ON u.user_id = l.user_id
WHERE
  STR_TO_DATE(u.register_time, '%Y/%m/%d %H:%i') < '2024-11-01';