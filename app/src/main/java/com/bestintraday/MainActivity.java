package com.bestintraday;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.graphics.Typeface;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Locale;

public class MainActivity extends Activity {
    private EditText apiKeyInput, accessTokenInput, totalInput, positionInput;
    private RadioButton liveRadio, manualRadio;
    private TextView status;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 44);
        }
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
        rules.setText("LOCKED STRATEGY\nEMA200 + 20-bar breakout + volume ≥ 6× previous 20 completed bars\n+1% move → 1% trailing stop • NO EOD EXIT");
        rules.setTextSize(14);
        box.addView(rules);

        TextView modeTitle = new TextView(this);
        modeTitle.setText("START MODE");
        modeTitle.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        box.addView(modeTitle);
        RadioGroup modes = new RadioGroup(this);
        manualRadio = new RadioButton(this);
        manualRadio.setText("MANUAL — signals/virtual positions, NO automatic orders");
        manualRadio.setChecked(true);
        liveRadio = new RadioButton(this);
        liveRadio.setText("LIVE — automatic Zerodha orders");
        modes.addView(manualRadio);
        modes.addView(liveRadio);
        box.addView(modes);

        apiKeyInput = field("Zerodha Kite API Key", false);
        accessTokenInput = field("Zerodha daily Access Token", true);
        totalInput = field("Total capital (₹)", false);
        totalInput.setText("5000000");
        positionInput = field("Capital per stock (₹)", false);
        positionInput.setText("200000");
        box.addView(apiKeyInput);
        box.addView(accessTokenInput);
        box.addView(totalInput);
        box.addView(positionInput);

        TextView calculation = new TextView(this);
        calculation.setText("25 positions at ₹2L each with the defaults");
        calculation.setPadding(0, 8, 0, 8);
        box.addView(calculation);

        LinearLayout buttons = new LinearLayout(this);
        Button start = new Button(this);
        start.setText("START IN BACKGROUND");
        start.setOnClickListener(v -> startTrading());
        Button stop = new Button(this);
        stop.setText("STOP");
        stop.setOnClickListener(v -> stopTrading());
        buttons.addView(start, new LinearLayout.LayoutParams(0, -2, 1));
        buttons.addView(stop, new LinearLayout.LayoutParams(0, -2, 1));
        box.addView(buttons);

        status = new TextView(this);
        status.setText("READY — MANUAL MODE\nApp will show a persistent notification while the engine runs in background.");
        status.setTextSize(15);
        box.addView(status);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);
        setContentView(scroll);
    }

    private EditText field(String hint, boolean password) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setSingleLine(true);
        if (password) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        else e.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        e.setPadding(0, 10, 0, 10);
        return e;
    }

    private void startTrading() {
        String api = apiKeyInput.getText().toString().trim();
        String token = accessTokenInput.getText().toString().trim();
        if (api.isEmpty() || token.isEmpty()) {
            status.setText("API KEY and DAILY ACCESS TOKEN are required.");
            return;
        }
        double total, position;
        try {
            total = Double.parseDouble(totalInput.getText().toString().trim());
            position = Double.parseDouble(positionInput.getText().toString().trim());
        } catch (Exception e) {
            status.setText("Enter valid capital amounts.");
            return;
        }
        if (total <= 0 || position <= 0 || position > total) {
            status.setText("Capital per stock must be > 0 and <= total capital.");
            return;
        }
        int slots = (int) Math.floor(total / position);
        boolean live = liveRadio.isChecked();
        if (live) {
            Toast.makeText(this, "LIVE mode selected. Automatic Zerodha orders will be enabled.", Toast.LENGTH_LONG).show();
        }
        Intent i = new Intent(this, TradingService.class);
        i.setAction(TradingService.ACTION_START);
        i.putExtra(TradingService.EXTRA_API_KEY, api);
        i.putExtra(TradingService.EXTRA_ACCESS_TOKEN, token);
        i.putExtra(TradingService.EXTRA_LIVE, live);
        i.putExtra(TradingService.EXTRA_TOTAL, total);
        i.putExtra(TradingService.EXTRA_POSITION, position);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i); else startService(i);
        status.setText(String.format(Locale.US, "%s STARTED\nTotal ₹%.0f • Per stock ₹%.0f • Max positions %d\n6× volume • 1%% activation • 1%% TSL • NO EOD EXIT\nBackground notification is active.", live ? "LIVE" : "MANUAL", total, position, slots));
    }

    private void stopTrading() {
        Intent i = new Intent(this, TradingService.class);
        i.setAction(TradingService.ACTION_STOP);
        startService(i);
        status.setText("STOP REQUEST SENT — engine will close its WebSocket and stop.");
    }
}
