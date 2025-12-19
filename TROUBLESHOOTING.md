# Troubleshooting Market Analytics Display

## Recent Changes Made

I've updated the CSS to make the Market Analytics view full-width and added pan/zoom functionality to the charts.

### CSS Changes:
1. Added `.container:has(.dashboard)` rule to make container full-width on trading dashboard
2. Fixed duplicate margin rule in `.dashboard` CSS
3. Added proper padding to `.dashboard` class
4. Kept all `.analytics-full-width` and `.analytics-card-full` classes intact

### Chart Features Added:
- **Zoom**: Use mouse wheel to zoom in/out on the X-axis
- **Pan**: Hold SHIFT and drag to pan left/right
- **Reset**: Double-click chart to reset zoom
- Charts are configured with proper grid lines, tooltips, and legends

## How to See the Changes

### 1. Restart Flask Server
```bash
# Stop the current server (Ctrl+C in the terminal)
# Then restart:
python app.py
```

### 2. Clear Browser Cache
**Hard Refresh:**
- **Chrome/Edge (Mac)**: `Cmd + Shift + R`
- **Chrome/Edge (Windows)**: `Ctrl + Shift + R`
- **Safari**: `Cmd + Option + R`
- **Firefox**: `Ctrl + Shift + R` or `Cmd + Shift + R`

**Or Clear Cache Completely:**
1. Open browser Developer Tools (F12)
2. Right-click the refresh button
3. Select "Empty Cache and Hard Reload"

### 3. Check Browser Console for Chart Data
1. Open Developer Tools (F12)
2. Go to the "Console" tab
3. Click on the "Market Analytics" tab in your app
4. Look for these console messages:
   - "Metrics data: {...}" - Shows the data loaded from API
   - "Player [name] price history: [...]" - Shows each player's price data
   - "Price chart datasets: [...]" - Shows the chart configuration

If you see these messages with data, the charts should display. If they're empty, you may need to:
- Place some trades to generate price history
- Execute some orders to create transaction data

### 4. Verify Full-Width Display
After clearing cache and refreshing:
- The Market Analytics section should expand to fill the full browser width
- Charts should be wider than the Trading view
- You should see zoom controls when hovering over charts

## Expected Behavior

### Market Analytics Tab Should Show:
1. **Market Overview** - Total trades, volume, active players
2. **All Players - Price History** - Line chart with all players' prices over time
   - Different color for each player
   - Legend at top showing player names
   - Gridlines for easier reading
3. **All Players - Trading Volume** - Bar chart showing trade volumes
   - Stacked bars for each player
   - Y-axis shows share count

### Chart Interactions:
- **Wheel scroll** = Zoom in/out on X-axis
- **Shift + Drag** = Pan left/right
- **Double-click** = Reset zoom to original view
- **Hover** = Show tooltip with exact values

## Still Not Working?

If after following all steps above the charts still look narrow or don't show zoom features:

1. Check that the Flask server restarted successfully
2. Verify the CSS file timestamp is recent: `ls -la static/style.css`
3. Try a different browser to rule out cache issues
4. Check browser console for any JavaScript errors
5. Verify you have trades/transactions to display (charts will be empty if no data exists)

## Testing the Features

To test zoom/pan:
1. Navigate to Market Analytics tab
2. Place your mouse over a chart
3. Scroll mouse wheel - chart should zoom on X-axis
4. Hold SHIFT and click-drag - chart should pan horizontally
5. Double-click chart - should reset to original view
