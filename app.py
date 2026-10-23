import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# 页面基础配置：默认适配移动端宽屏排版
st.set_page_config(page_title="AUD/USD 助手", page_icon="💱", layout="centered")

st.title("💱 AUD/USD 汇率与记账")

# 1. 抓取与分析汇率数据
@st.cache_data(ttl=300)
def load_fx_data():
    ticker = yf.Ticker("AUDUSD=X")
    df = ticker.history(period="1y", interval="1d")
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['Upper'] = df['SMA20'] + (df['Close'].rolling(20).std() * 2)
    df['Lower'] = df['SMA20'] - (df['Close'].rolling(20).std() * 2)
    return df

try:
    df = load_fx_data()
    curr_rate = float(df['Close'].iloc[-1])
    lower_band = float(df['Lower'].iloc[-1])
    upper_band = float(df['Upper'].iloc[-1])
    sma_20 = float(df['SMA20'].iloc[-1])

    # 顶部关键指标卡片
    col1, col2 = st.columns(2)
    col1.metric("当前汇率", f"{curr_rate:.4f}")
    col2.metric("20日均线", f"{sma_20:.4f}")

    # 交易决策信号提示
    if curr_rate <= lower_band:
        st.success("🟢 **买入 AUD 信号**：当前处于布林带下轨超卖区，适合用 USD 换回 AUD。")
    elif curr_rate >= upper_band:
        st.warning("🔴 **卖出 AUD 信号**：当前处于布林带上轨超买区，适合将 AUD 换为 USD。")
    else:
        st.info("⚪ **观望区间**：当前汇率在正常均值范围内波动。")

    # 移动端折线图展示
    st.line_chart(df[['Close', 'Upper', 'Lower']].tail(60))

except Exception as e:
    st.error(f"行情数据加载失败: {e}")
    curr_rate = 0.6500

st.divider()

# 2. 记账表单
st.subheader("📝 记录本次换汇")

# 连接 Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

with st.form("trade_entry_form"):
    trade_type = st.selectbox("仓位类型", ["核心长期", "波段套利"])
    action = st.selectbox("交易方向", ["AUD 兑换 USD (卖澳币)", "USD 兑换 AUD (买澳币)"])
    rate_input = st.number_input("实际成交汇率", value=curr_rate, format="%.4f")
    amount_in = st.number_input("支出金额", min_value=0.0, step=100.0)

    # 自动计算预估换回金额
    if "AUD 兑换 USD" in action:
        calc_out = amount_in * rate_input
        out_label = f"换得 USD: ${calc_out:.2f}"
    else:
        calc_out = amount_in / rate_input if rate_input > 0 else 0.0
        out_label = f"换得 AUD: ${calc_out:.2f}"
    
    st.caption(out_label)
    note = st.text_input("备注信息", placeholder="例：挂单成交、第1笔网格等")
    
    submitted = st.form_submit_button("保存到 Google 表格", use_container_width=True)

    if submitted:
        if amount_in <= 0:
            st.warning("请输入有效金额！")
        else:
            try:
                # 读取现有表格并追加新记录
                existing_data = conn.read(ttl=0)
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Type": trade_type,
                    "Action": action,
                    "Rate": rate_input,
                    "Amount_In": amount_in,
                    "Amount_Out": round(calc_out, 2),
                    "Note": note
                }])
                updated_data = pd.concat([existing_data, new_row], ignore_index=True)
                conn.update(data=updated_data)
                st.success("✅ 记录成功保存至 Google 表格！")
            except Exception as err:
                st.error(f"保存失败，请检查表格权限: {err}")

# 3. 历史记录查看
with st.expander("📊 查看历史交易记录"):
    try:
        log_df = conn.read(ttl=0)
        st.dataframe(log_df.tail(10), use_container_width=True)
    except Exception:
        st.caption("暂无记录或无法连接表格。")
