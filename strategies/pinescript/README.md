# TradingView Pine Script Strategies

Three professional trading strategies with common mistakes fixed.

## 📊 Strategy 1: Golden Cross EMA Strategy

**File:** `golden_cross_strategy.pine`

### Features:
- **Golden Cross Entry**: Fast EMA (50) crosses above Slow EMA (200) for long positions
- **Death Cross Entry**: Fast EMA crosses below Slow EMA for short positions
- **Trend Confirmation**: Only trades when price is above/below both EMAs
- **Stop Loss & Take Profit**: Configurable percentage-based risk management
- **Visual Indicators**: Plots EMAs, cross signals, and trend background

### Common Mistakes Fixed:
1. ✅ **Added trend confirmation** - Prevents false signals by checking price position
2. ✅ **Proper stop loss calculation** - Uses percentage-based stops that adjust with price
3. ✅ **Exit strategy** - Uses `strategy.exit()` with both stop and limit for proper risk management
4. ✅ **Signal filtering** - Only trades when price confirms the trend direction

---

## 📈 Strategy 2: RSI Strategy

**File:** `rsi_strategy.pine`

### Features:
- **RSI Overbought/Oversold**: Enters when RSI crosses 30 (oversold) or 70 (overbought)
- **Divergence Detection**: Optional bullish/bearish divergence signals
- **Momentum Confirmation**: RSI must be rising for longs, falling for shorts
- **Auto-Exit**: Closes positions when RSI reaches opposite extreme
- **Stop Loss & Take Profit**: Risk management for all trades

### Common Mistakes Fixed:
1. ✅ **Divergence logic** - Properly detects price vs RSI divergences (not just overbought/oversold)
2. ✅ **Momentum confirmation** - Prevents entry on weak signals by requiring RSI direction
3. ✅ **Exit strategy** - Closes positions when RSI reaches opposite extreme (prevents holding too long)
4. ✅ **Proper signal timing** - Uses `ta.crossover()` and `ta.crossunder()` instead of just comparing values
5. ✅ **Variable management** - Uses `var` for persistent state in divergence detection

---

## 📉 Strategy 3: Bollinger Bands Strategy

**File:** `bollinger_bands_strategy.pine`

### Features:
- **Mean Reversion**: Enters when price touches bands and bounces
- **Volume Filter**: Optional filter requiring above-average volume
- **Squeeze Detection**: Identifies periods of low volatility
- **Volatility Measurement**: Uses band width to measure market volatility
- **Multiple Entry Conditions**: Supports both crossover and bounce patterns

### Common Mistakes Fixed:
1. ✅ **Mean reversion logic** - Properly identifies bounces from bands (not just touching)
2. ✅ **Volume confirmation** - Optional filter to ensure real moves (not just noise)
3. ✅ **Band width calculation** - Uses relative band width for volatility measurement
4. ✅ **Exit conditions** - Exits when price reaches middle band (mean reversion complete)
5. ✅ **Squeeze indicator** - Identifies low volatility periods (potential breakout setups)
6. ✅ **Price position checks** - Uses percentage-based proximity checks instead of exact values

---

## 🎯 Visible Entry Signals

All strategies now feature **highly visible entry signals**:

- ✅ **Large colored arrows** (🟢 Green for LONG, 🔴 Red for SHORT) - `size.large`
- ✅ **Detailed text labels** showing:
  - Entry price
  - Stop Loss level
  - Take Profit level
  - Additional info (RSI value, BB levels, etc.)
- ✅ **Background highlights** when signals trigger
- ✅ **Alert conditions** ready for TradingView alerts

### Setting Up Alerts

1. Right-click on the chart → **Add Alert**
2. Select your strategy from the condition dropdown
3. Choose:
   - **🟢 [Strategy] LONG Signal** for buy alerts
   - **🔴 [Strategy] SHORT Signal** for sell alerts
4. Configure notification settings (email, SMS, popup, etc.)

## 🚀 How to Use

1. **Copy the code** from any `.pine` file
2. **Open TradingView** and go to Pine Editor
3. **Paste the code** and click "Add to Chart"
4. **Configure parameters** in the strategy settings:
   - Stop Loss %
   - Take Profit %
   - Indicator periods (EMA, RSI, BB)
5. **Set up alerts** (optional but recommended)
6. **Backtest** on your preferred timeframe and instrument

## ⚠️ Important Notes

- **Risk Management**: Always use stop losses (default 2% recommended)
- **Backtesting**: Test on multiple timeframes and instruments
- **Market Conditions**: These strategies work best in trending (Golden Cross) or ranging (BB/RSI) markets
- **Commission**: Adjust strategy settings for realistic commission costs
- **Slippage**: Consider slippage in live trading

## 🔧 Key Improvements Made

1. **Proper Entry/Exit Logic**: All strategies use `strategy.entry()` and `strategy.exit()` correctly
2. **Risk Management**: Stop losses and take profits are properly calculated and applied
3. **Signal Filtering**: Multiple confirmation conditions prevent false signals
4. **State Management**: Proper use of `var` for persistent variables where needed
5. **Visual Feedback**: Clear plotting and signals for easy chart analysis
6. **Parameter Flexibility**: All key values are configurable via inputs

---

**Happy Trading! 📈**

