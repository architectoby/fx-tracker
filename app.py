import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import altair as alt

st.set_page_config(page_title="AUD/USD 助手", page_icon="💱", layout="centered")

st.title("💱 汇率监控与记账")

# 1. 抓取与分析汇率数据
@st.cache_data(ttl=300)
def load_fx_data():
    ticker = yf.Ticker("AUDUSD=X")
    df = ticker.history(period="1y", interval="1d")
    return df[['Close']].copy()

try:
    raw_df = load_fx_data()
    
    # 新增：全局视角切换开关 (控制所有计算和图表的基准)
   # 初始化会话状态
    if "is_usd_base" not in st.session_state:
        st.session_state.is_usd_base = False

    # 根据当前状态设定动态标签
    toggle_label = "🔄 当前视角: USD/AUD (1美元 = ?澳币)" if st.session_state.is_usd_base else "🔄 当前视角: AUD/USD (1澳币 = ?美元)"
    
    # 渲染开关并绑定状态
    is_usd_base = st.toggle(toggle_label, key="is_usd_base")
    
    df = raw_df.copy()
    if is_usd_base:
        # 将 0.65 转换为 1.53 视角
        df['Close'] = 1 / df['Close']
        
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['Upper'] = df['SMA20'] + (df['Close'].rolling(20).std() * 2)
    df['Lower'] = df['SMA20'] - (df['Close'].rolling(20).std() * 2)
    
    curr_rate = float(df['Close'].iloc[-1])
    lower_band = float(df['Lower'].iloc[-1])
    upper_band = float(df['Upper'].iloc[-1])
    sma_20 = float(df['SMA20'].iloc[-1])

    # 顶部关键指标卡片
    col1, col2 = st.columns(2)
    col1.metric("当前汇率", f"{curr_rate:.4f}")
    col2.metric("20日均线", f"{sma_20:.4f}")

    # 交易决策信号提示
    if not is_usd_base:
        if curr_rate <= lower_band:
            st.success("🟢 **买入 AUD 信号**：当前处于布林带下轨超卖区，适合用 USD 换回 AUD。")
        elif curr_rate >= upper_band:
            st.warning("🔴 **卖出 AUD 信号**：当前处于布林带上轨超买区，适合将 AUD 换为 USD。")
    else:
        if curr_rate >= upper_band:
            st.success("🟢 **买入 AUD 信号**：USD达到高点，适合用 USD 换回 AUD。")
        elif curr_rate <= lower_band:
            st.warning("🔴 **卖出 AUD 信号**：USD跌至低点，适合将 AUD 换为 USD。")

   # 准备图表数据并解除时区限制（Altair 需要）
    chart_data = df[['Close', 'Upper', 'Lower']].tail(60).copy()
    chart_data.index = chart_data.index.tz_localize(None) 
    chart_data = chart_data.reset_index()
    time_col = chart_data.columns[0]
    chart_data = chart_data.melt(time_col, var_name='指标', value_name='汇率')
    
    # 根据当前视角设定 Y 轴区间
    y_min, y_max = (1.2500, 1.6500) if is_usd_base else (0.5500, 0.8500)
    
    # 渲染自定义区间图表
    chart = alt.Chart(chart_data).mark_line().encode(
        x=alt.X(f'{time_col}:T', title=''),
        y=alt.Y('汇率:Q', scale=alt.Scale(domain=[y_min, y_max])),
        color=alt.Color('指标:N', legend=alt.Legend(title="图例"))
    ).interactive()
    
    st.altair_chart(chart, use_container_width=True)

except Exception as e:
    st.error(f"行情数据加载失败: {e}")
    curr_rate = 0.6500

st.divider()

# 2. 记账表单
st.subheader("📝 记录本次换汇")

conn = st.connection("gsheets", type=GSheetsConnection)

with st.form("trade_entry_form"):
    # 新增：改为横排的按钮样式
    trade_type = st.radio("仓位类型", ["核心长期", "波段套利"], horizontal=True)
    
    # 新增：点击直观切换交易方向
    action = st.radio("交易方向 (点击切换)", 
                      ["🇦🇺 卖出 AUD (换回USD)", "🇺🇸 卖出 USD (换回AUD)"], 
                      horizontal=True)
    
    rate_input = st.number_input("实际成交汇率 (按你看到的填)", value=curr_rate, format="%.4f")
    amount_in = st.number_input("支出金额", min_value=0.0, step=100.0)

    # 自动计算逻辑（兼容两个视角的数学转换）
    if "卖出 AUD" in action:
        calc_out = amount_in * rate_input if not is_usd_base else (amount_in / rate_input if rate_input > 0 else 0)
        out_label = f"预计换得: ${calc_out:.2f} USD"
        db_action = "AUD -> USD"
    else:
        calc_out = (amount_in / rate_input if rate_input > 0 else 0) if not is_usd_base else amount_in * rate_input
        out_label = f"预计换得: ${calc_out:.2f} AUD"
        db_action = "USD -> AUD"
    
    st.caption(out_label)
    note = st.text_input("备注信息", placeholder="例：挂单成交、第1笔网格等")
    
    submitted = st.form_submit_button("保存到 Google 表格", use_container_width=True)

    if submitted:
        if amount_in <= 0:
            st.warning("请输入有效金额！")
        else:
            try:
                existing_data = conn.read(ttl=0)
                new_row = pd.DataFrame([{
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Type": trade_type,
                    "Action": db_action,
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
