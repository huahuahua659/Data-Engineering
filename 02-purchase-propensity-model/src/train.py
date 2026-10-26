from pathlib import Path
import warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, average_precision_score, accuracy_score,
    precision_score, recall_score, f1_score, confusion_matrix
)
from catboost import CatBoostClassifier

warnings.filterwarnings("ignore")

FILE_PATH = Path(r"D:\数据挖掘\用户预测.csv")
OUT_DIR = FILE_PATH.parent

try:
    df = pd.read_csv(FILE_PATH, encoding="utf-8-sig")
except UnicodeDecodeError:
    df = pd.read_csv(FILE_PATH, encoding="gb18030")

df.columns = df.columns.astype(str).str.strip()
df["y"] = pd.to_numeric(df["y"], errors="coerce")
df = df.dropna(subset=["y"]).reset_index(drop=True)
df["y"] = df["y"].astype(int)

X = df.drop(columns=["user_id", "y"], errors="ignore")
y = df["y"]


for col in ["order_cnt_30d", "order_cnt_90d", "amount_30d", "amount_90d"]:
    if col in X.columns:
        X[col] = pd.to_numeric(X[col], errors="coerce")
if {"order_cnt_30d", "order_cnt_90d"}.issubset(X.columns):
    X["recent_order_ratio"] = X["order_cnt_30d"] / (X["order_cnt_90d"] + 1)
if {"amount_30d", "amount_90d"}.issubset(X.columns):
    X["recent_amount_ratio"] = X["amount_30d"] / (X["amount_90d"] + 1)

cat_cols = X.select_dtypes(include=["object", "category", "string"]).columns.tolist()
num_cols = [c for c in X.columns if c not in cat_cols]
for c in num_cols:
    X[c] = pd.to_numeric(X[c], errors="coerce")

# 划分 60 / 20 / 20（验证集给早停，测试集完全隔离）
X_train_val, X_test, y_train_val, y_test, _, id_test = train_test_split(
    X, y, df["user_id"], test_size=0.20, random_state=42, stratify=y)
X_train, X_val, y_train, y_val = train_test_split(
    X_train_val, y_train_val, test_size=0.25, random_state=42, stratify=y_train_val)

# 类别缺失统一填 Unknown
for col in cat_cols:
    X_train[col] = X_train[col].fillna("Unknown").astype(str)
    X_val[col] = X_val[col].fillna("Unknown").astype(str)
    X_test[col] = X_test[col].fillna("Unknown").astype(str)

# 逻辑回归基线（数值：中位数填充+标准化；类别：众数填充+独热）
preprocessor = ColumnTransformer([
    ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                      ("sc", StandardScaler())]), num_cols),
    ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                      ("oh", OneHotEncoder(handle_unknown="ignore"))]), cat_cols),
])
lr = Pipeline([("pre", preprocessor),
               ("model", LogisticRegression(max_iter=2000, random_state=42))])
lr.fit(X_train, y_train)
lr_prob = lr.predict_proba(X_test)[:, 1]

# CatBoost 主模型（早停 + 回滚最优迭代）
cat = CatBoostClassifier(
    iterations=2000, depth=6, learning_rate=0.03, loss_function="Logloss",
    eval_metric="AUC", l2_leaf_reg=5, random_seed=42,
    verbose=False, allow_writing_files=False)
cat.fit(X_train, y_train, cat_features=cat_cols,
        eval_set=(X_val, y_val), early_stopping_rounds=150, use_best_model=True)
cat_prob = cat.predict_proba(X_test)[:, 1]

# 评估
def evaluate(name, y_true, proba):
    pred = (proba >= 0.5).astype(int)
    print(f"\n【{name}】")
    print(f"ROC-AUC：{roc_auc_score(y_true, proba):.4f}   "
          f"AP：{average_precision_score(y_true, proba):.4f}   "
          f"Acc：{accuracy_score(y_true, pred):.4f}")
    print(f"Precision：{precision_score(y_true, pred, zero_division=0):.4f}   "
          f"Recall：{recall_score(y_true, pred, zero_division=0):.4f}   "
          f"F1：{f1_score(y_true, pred, zero_division=0):.4f}")
    print("混淆矩阵(行=真实,列=预测)：\n", confusion_matrix(y_true, pred, labels=[0, 1]))
    return roc_auc_score(y_true, proba)

lr_auc = evaluate("Logistic Regression", y_test, lr_prob)
cat_auc = evaluate("CatBoost", y_test, cat_prob)
print(f"\nAUC 对比：逻辑回归 {lr_auc:.4f} vs CatBoost {cat_auc:.4f}")

# Top 10% 高购买倾向用户
top_df = pd.DataFrame({"y": y_test.to_numpy(), "prob": cat_prob}).sort_values("prob", ascending=False)
top_n = int(np.ceil(len(top_df) * 0.10))
lift = top_df.head(top_n)["y"].mean() / top_df["y"].mean()
print(f"\nTop 10% 购买率：{top_df.head(top_n)['y'].mean():.2%}   "
      f"整体：{top_df['y'].mean():.2%}   Lift：{lift:.2f}")

# 导出测试集预测结果
pd.DataFrame({
    "user_id": id_test.to_numpy(), "y_true": y_test.to_numpy(),
    "prob_logistic": lr_prob, "prob_catboost": cat_prob,
    "pred_catboost_05": (cat_prob >= 0.5).astype(int)
}).sort_values("prob_catboost", ascending=False).to_csv(
    OUT_DIR / "测试集预测结果.csv", index=False, encoding="utf-8-sig")

# 全量重训最终模型并保存
X_all = X.copy()
for col in cat_cols:
    X_all[col] = X_all[col].fillna("Unknown").astype(str)
best_iter = cat.get_best_iteration()
final = CatBoostClassifier(
    iterations=best_iter + 1 if best_iter >= 0 else 1000, depth=6, learning_rate=0.03,
    loss_function="Logloss", eval_metric="AUC", l2_leaf_reg=5, random_seed=42,
    verbose=False, allow_writing_files=False)
final.fit(X_all, y, cat_features=cat_cols)
final.save_model(str(OUT_DIR / "CatBoost用户购买预测模型.cbm"))

# 特征重要性
imp = pd.DataFrame({"feature": final.feature_names_,
                    "importance": final.get_feature_importance()}).sort_values("importance", ascending=False)
imp.to_csv(OUT_DIR / "特征重要性.csv", index=False, encoding="utf-8-sig")
print("\n特征重要性 Top 10：")
print(imp.head(10).to_string(index=False))
