package com.bestintraday;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class TradingService extends Service {
    public static final String ACTION_START = "com.bestintraday.START";
    public static final String ACTION_STOP = "com.bestintraday.STOP";
    public static final String EXTRA_API_KEY = "api_key";
    public static final String EXTRA_ACCESS_TOKEN = "access_token";
    public static final String EXTRA_LIVE = "live";
    public static final String EXTRA_TOTAL = "total";
    public static final String EXTRA_POSITION = "position";
    private static final String CHANNEL_ID = "best_intraday_trading";
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private volatile boolean started = false;
    private String lastEventKey = "";

    @Override public void onCreate() { super.onCreate(); createChannel(); }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            started = false; stopEngine(); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); return START_NOT_STICKY;
        }
        if (intent != null && ACTION_START.equals(intent.getAction())) {
            String apiKey = intent.getStringExtra(EXTRA_API_KEY);
            String accessToken = intent.getStringExtra(EXTRA_ACCESS_TOKEN);
            boolean live = intent.getBooleanExtra(EXTRA_LIVE, false);
            double total = intent.getDoubleExtra(EXTRA_TOTAL, 5000000.0);
            double position = intent.getDoubleExtra(EXTRA_POSITION, 200000.0);
            startForeground(1, buildNotification("Starting " + (live ? "LIVE" : "MANUAL") + " engine..."));
            executor.execute(() -> startEngine(apiKey, accessToken, live, total, position));
        }
        return START_STICKY;
    }

    private void startEngine(String apiKey, String accessToken, boolean live, double total, double position) {
        try {
            PyObject bridge = Python.getInstance().getModule("scanner_bridge");
            bridge.callAttr("start_engine", apiKey, accessToken, live, total, position);
            started = true;
            updateNotification("Running " + (live ? "LIVE" : "MANUAL") + " • 6× volume • ₹" + money(total) + " / ₹" + money(position));
            monitor(bridge);
        } catch (Exception e) {
            started = false;
            updateNotification("START ERROR: " + shortText(e.toString(), 100));
        }
    }

    private void monitor(PyObject bridge) {
        while (started) {
            try {
                Thread.sleep(5000L);
                JSONObject root = new JSONObject(bridge.callAttr("snapshot").toString());
                JSONArray events = root.optJSONArray("events");
                if (events != null && events.length() > 0) {
                    JSONObject e = events.getJSONObject(0);
                    String key = e.optString("time") + "|" + e.optString("type") + "|" + e.optString("sym");
                    if (!key.equals(lastEventKey)) {
                        lastEventKey = key;
                        String type = e.optString("type");
                        if ("BUY".equals(type) || "SELL".equals(type) || "TSL_ON".equals(type) || "ERROR".equals(type)) {
                            String msg = type + " " + e.optString("sym", "") + (e.has("price") ? " ₹" + e.optDouble("price") : "");
                            updateNotification(shortText(msg, 110));
                        }
                    }
                }
            } catch (Exception ignored) {}
        }
    }

    private void stopEngine() {
        executor.execute(() -> { try { Python.getInstance().getModule("scanner_bridge").callAttr("stop_engine"); } catch (Exception ignored) {} });
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("BEST INTRADAY")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_menu_manage)
                .setOngoing(true)
                .setContentIntent(pi)
                .setCategory(Notification.CATEGORY_SERVICE)
                .build();
    }

    private void updateNotification(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) nm.notify(1, buildNotification(text));
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "Trading engine", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("BEST INTRADAY background trading engine");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(channel);
        }
    }

    private static String money(double x) { return String.format(java.util.Locale.US, "%.0f", x); }
    private static String shortText(String s, int n) { return s.length() <= n ? s : s.substring(0, n); }

    @Override public void onTimeout(int startId, int fgsType) { started = false; stopEngine(); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); }
    @Override public void onDestroy() { started = false; stopEngine(); executor.shutdownNow(); super.onDestroy(); }
    @Override public IBinder onBind(Intent intent) { return null; }
}
