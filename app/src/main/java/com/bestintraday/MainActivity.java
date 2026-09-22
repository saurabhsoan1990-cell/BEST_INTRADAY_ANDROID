package com.bestintraday;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.graphics.Typeface;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private EditText capitalInput;
    private EditText tokenInput;
    private TextView status;
    private TextView output;
    private Button startButton;
    private Button stopButton;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private boolean running = false;

    // Original scanner default is 600 seconds.
    private static final long CYCLE_MS = 10 * 60 * 1000L;

    private final Runnable scheduledScan = new Runnable() {
        @Override public void run() {
            if (!running) return;
            runScan();
            handler.postDelayed(this, CYCLE_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
    }

    private void buildUi() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(28, 28, 28, 28);

        TextView title = new TextView(this);
        title.setText("BEST INTRADAY");
        title.setTextSize(24);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        box.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("TRUE same-time RVOL • Max 2 picks");
        subtitle.setTextSize(14);
        box.addView(subtitle);

        capitalInput = new EditText(this);
        capitalInput.setHint("Capital (₹)");
        capitalInput.setText("200000");
        capitalInput.setInputType(2 | 8192);
        box.addView(capitalInput);

        tokenInput = new EditText(this);
        tokenInput.setHint("Upstox Access Token");
        tokenInput.setSingleLine(true);
        box.addView(tokenInput);

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);

        startButton = new Button(this);
        startButton.setText("START");
        startButton.setOnClickListener(v -> startScanner());

        stopButton = new Button(this);
        stopButton.setText("STOP");
        stopButton.setEnabled(false);
        stopButton.setOnClickListener(v -> stopScanner());

        buttons.addView(startButton, new LinearLayout.LayoutParams(0, -2, 1));
        buttons.addView(stopButton, new LinearLayout.LayoutParams(0, -2, 1));
        box.addView(buttons);

        status = new TextView(this);
        status.setText("Ready");
        status.setTextSize(16);
        box.addView(status);

        output = new TextView(this);
        output.setTextSize(15);
        output.setTextIsSelectable(true);
        box.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);
        setContentView(scroll);
    }

    private void startScanner() {
        running = true;
        startButton.setEnabled(false);
        stopButton.setEnabled(true);
        status.setText("Scanning...");
        runScan();
        handler.removeCallbacks(scheduledScan);
        handler.postDelayed(scheduledScan, CYCLE_MS);
    }

    private void stopScanner() {
        running = false;
        handler.removeCallbacks(scheduledScan);
        startButton.setEnabled(true);
        stopButton.setEnabled(false);
        status.setText("Stopped");
    }

    private void runScan() {
        final String capital = capitalInput.getText().toString().trim();
        final String token = tokenInput.getText().toString().trim();

        executor.execute(() -> {
            try {
                Python py = Python.getInstance();
                PyObject bridge = py.getModule("scanner_bridge");
                String json = bridge.callAttr("scan_once", capital, token).toString();
                runOnUiThread(() -> render(json));
            } catch (Exception e) {
                runOnUiThread(() -> {
                    status.setText("ERROR");
                    output.setText(e.toString());
                });
            }
        });
    }

    private void render(String json) {
        try {
            JSONObject root = new JSONObject(json);
            if (!root.optBoolean("ok", false)) {
                status.setText("ERROR");
                output.setText(root.optString("error", "Unknown error"));
                return;
            }

            String regime = root.optString("regime", "UNKNOWN");
            JSONArray picks = root.optJSONArray("picks");

            StringBuilder s = new StringBuilder();
            s.append("REGIME: ").append(regime).append("\n\n");

            if (picks == null || picks.length() == 0) {
                s.append("NO PICK THIS CYCLE\n");
            } else {
                for (int i = 0; i < picks.length(); i++) {
                    JSONObject p = picks.getJSONObject(i);
                    s.append(i + 1).append(") ")
                            .append(p.optString("sym")).append("\n");
                    s.append("Price: ₹").append(p.optDouble("px"))
                            .append("   Chg: ").append(p.optDouble("chg"))
                            .append("%\n");
                    s.append("Score: ").append(p.optDouble("score"))
                            .append("   RS: ").append(p.optDouble("rs"))
                            .append("   RVOL: ").append(p.optDouble("rvol")).append("x\n");
                    s.append("Qty: ").append(p.optInt("qty"))
                            .append("   Used: ₹").append(p.optDouble("used")).append("\n");
                    s.append("T1: ₹").append(p.optDouble("t1"))
                            .append("   T2: ₹").append(p.optDouble("t2")).append("\n");
                    s.append("Band: ₹").append(p.optDouble("band")).append("\n");
                    s.append("Why: ").append(p.optString("why")).append("\n\n");
                }
            }

            s.append("Updated automatically every 10 minutes while running.");
            output.setText(s.toString());
            status.setText("OK");
        } catch (Exception e) {
            status.setText("PARSE ERROR");
            output.setText(json + "\n\n" + e);
        }
    }

    @Override
    protected void onDestroy() {
        running = false;
        handler.removeCallbacks(scheduledScan);
        executor.shutdownNow();
        super.onDestroy();
    }
}
