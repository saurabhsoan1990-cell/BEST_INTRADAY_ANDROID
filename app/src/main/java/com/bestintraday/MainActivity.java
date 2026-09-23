package com.bestintraday;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Typeface;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private EditText apiKeyInput;
    private EditText accessTokenInput;
    private CheckBox liveCheck;
    private TextView status;
    private TextView output;
    private Button startButton;
    private Button stopButton;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private boolean running = false;

    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            if (!running) return;
            snapshot();
            handler.postDelayed(this, 2000L);
        }
    };

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
    }

    private void buildUi() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(28, 28, 28, 28);

        TextView title = new TextView(this);
        title.setText("BEST INTRADAY • ZERODHA");
        title.setTextSize(23);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        box.addView(title);

        TextView rules = new TextView(this);
        rules.setText("₹50L total • ₹2L/stock • max 25 positions\nEMA200 + breakout + volume ≥ 5× previous 20-bar average\n1% activation • 1% TSL • NO EOD EXIT");
        rules.setTextSize(14);
        box.addView(rules);

        apiKeyInput = new EditText(this);
        apiKeyInput.setHint("Zerodha Kite API Key");
        apiKeyInput.setSingleLine(true);
        box.addView(apiKeyInput);

        accessTokenInput = new EditText(this);
        accessTokenInput.setHint("Zerodha daily Access Token");
        accessTokenInput.setSingleLine(true);
        accessTokenInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        box.addView(accessTokenInput);

        liveCheck = new CheckBox(this);
        liveCheck.setText("LIVE ORDER MODE — unchecked = PAPER");
        liveCheck.setChecked(false);
        box.addView(liveCheck);

        LinearLayout buttons = new LinearLayout(this);
        startButton = new Button(this);
        startButton.setText("START");
        startButton.setOnClickListener(v -> startEngine());
        stopButton = new Button(this);
        stopButton.setText("STOP");
        stopButton.setEnabled(false);
        stopButton.setOnClickListener(v -> stopEngine());
        buttons.addView(startButton, new LinearLayout.LayoutParams(0, -2, 1));
        buttons.addView(stopButton, new LinearLayout.LayoutParams(0, -2, 1));
        box.addView(buttons);

        status = new TextView(this);
        status.setText("READY — PAPER MODE");
        status.setTextSize(16);
        box.addView(status);

        output = new TextView(this);
        output.setTextSize(14);
        output.setTextIsSelectable(true);
        box.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);
        setContentView(scroll);
    }

    private void startEngine() {
        final String key = apiKeyInput.getText().toString().trim();
        final String token = accessTokenInput.getText().toString().trim();
        final boolean live = liveCheck.isChecked();
        if (key.isEmpty() || token.isEmpty()) {
            status.setText("ERROR: API key and access token required");
            return;
        }
        if (live) {
            status.setText("LIVE MODE — starting only after credentials/connectivity checks");
        } else {
            status.setText("PAPER MODE — warming up");
        }
        startButton.setEnabled(false);
        stopButton.setEnabled(true);
        running = true;
        executor.execute(() -> {
            try {
                Python py = Python.getInstance();
                PyObject bridge = py.getModule("scanner_bridge");
                String result = bridge.callAttr("start_engine", key, token, live).toString();
                runOnUiThread(() -> {
                    status.setText(result);
                    handler.removeCallbacks(refresh);
                    handler.post(refresh);
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    status.setText("START ERROR");
                    output.setText(e.toString());
                    running = false;
                    startButton.setEnabled(true);
                    stopButton.setEnabled(false);
                });
            }
        });
    }

    private void stopEngine() {
        running = false;
        handler.removeCallbacks(refresh);
        executor.execute(() -> {
            try {
                Python py = Python.getInstance();
                PyObject bridge = py.getModule("scanner_bridge");
                bridge.callAttr("stop_engine");
            } catch (Exception ignored) {}
            runOnUiThread(() -> {
                status.setText("STOPPED");
                startButton.setEnabled(true);
                stopButton.setEnabled(false);
            });
        });
    }

    private void snapshot() {
        executor.execute(() -> {
            try {
                Python py = Python.getInstance();
                PyObject bridge = py.getModule("scanner_bridge");
                String json = bridge.callAttr("snapshot").toString();
                runOnUiThread(() -> render(json));
            } catch (Exception e) {
                runOnUiThread(() -> output.setText(e.toString()));
            }
        });
    }

    private void render(String json) {
        try {
            JSONObject root = new JSONObject(json);
            if (!root.optBoolean("ok", false)) {
                output.setText(root.optString("error", json));
                return;
            }
            StringBuilder s = new StringBuilder();
            s.append("RUNNING: ").append(root.optBoolean("running"))
             .append("   WARMING: ").append(root.optBoolean("warming"))
             .append("   MODE: ").append(root.optBoolean("live") ? "LIVE" : "PAPER")
             .append("\nNSE symbols: ").append(root.optInt("symbols")).append("\n\n");

            JSONObject positions = root.optJSONObject("positions");
            s.append("OPEN POSITIONS: ").append(positions == null ? 0 : positions.length()).append("/25\n");
            if (positions != null) {
                JSONArray names = positions.names();
                if (names != null) for (int i = 0; i < names.length(); i++) {
                    String sym = names.getString(i);
                    JSONObject p = positions.getJSONObject(sym);
                    s.append(sym).append("  qty=").append(p.optInt("qty"))
                     .append(" entry=").append(p.optDouble("entry"))
                     .append(" peak=").append(p.optDouble("peak"))
                     .append(" TSL=").append(p.optBoolean("active") ? "ON" : "WAIT")
                     .append("\n");
                }
            }
            s.append("\nRECENT EVENTS\n");
            JSONArray events = root.optJSONArray("events");
            if (events != null) {
                for (int i = 0; i < Math.min(events.length(), 25); i++) {
                    JSONObject e = events.getJSONObject(i);
                    s.append(e.optString("time")).append("  ")
                     .append(e.optString("type")).append("  ")
                     .append(e.optString("sym", ""));
                    if (e.has("price")) s.append(" ₹").append(e.optDouble("price"));
                    if (e.has("qty")) s.append(" qty=").append(e.optInt("qty"));
                    if (e.has("pnl")) s.append(" P&L=").append(e.optDouble("pnl"));
                    if (e.has("message")) s.append(" ").append(e.optString("message"));
                    s.append("\n");
                }
            }
            output.setText(s.toString());
        } catch (Exception e) {
            output.setText(json + "\n" + e);
        }
    }

    @Override protected void onDestroy() {
        running = false;
        handler.removeCallbacks(refresh);
        executor.shutdownNow();
        super.onDestroy();
    }
}
