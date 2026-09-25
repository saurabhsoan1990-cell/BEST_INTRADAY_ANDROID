package com.bestintraday;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.IBinder;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class TradingService extends Service {
    public static final String ACTION_START="com.bestintraday.START", ACTION_STOP="com.bestintraday.STOP";
    public static final String EXTRA_API_KEY="api_key", EXTRA_ACCESS_TOKEN="access_token", EXTRA_LIVE="live", EXTRA_TOTAL="total", EXTRA_POSITION="position";
    private static final String CHANNEL_ID="best_intraday_upstox";
    private static final String PREFS="engine_prefs", P_TOKEN="token", P_LIVE="live", P_TOTAL="total", P_POSITION="position", P_RUNNING="running";
    private final ExecutorService executor=Executors.newSingleThreadExecutor();
    private volatile boolean started=false; private String lastEventKey="";

    @Override public void onCreate(){ super.onCreate(); createChannel(); }

    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null && ACTION_STOP.equals(intent.getAction())){
            getSharedPreferences(PREFS,MODE_PRIVATE).edit().putBoolean(P_RUNNING,false).apply();
            started=false; stopEngine(); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); return START_NOT_STICKY;
        }
        if(intent!=null && ACTION_START.equals(intent.getAction())){
            String token=intent.getStringExtra(EXTRA_ACCESS_TOKEN);
            boolean live=intent.getBooleanExtra(EXTRA_LIVE,false);
            double total=intent.getDoubleExtra(EXTRA_TOTAL,5000000);
            double position=intent.getDoubleExtra(EXTRA_POSITION,200000);
            saveConfig(token,live,total,position);
            launchEngine(token,live,total,position);
        } else if(intent==null && getSharedPreferences(PREFS,MODE_PRIVATE).getBoolean(P_RUNNING,false)) {
            SharedPreferences p=getSharedPreferences(PREFS,MODE_PRIVATE);
            launchEngine(p.getString(P_TOKEN,""),p.getBoolean(P_LIVE,false),p.getFloat(P_TOTAL,5000000f),p.getFloat(P_POSITION,200000f));
        }
        return START_STICKY;
    }

    private void saveConfig(String token,boolean live,double total,double position){
        getSharedPreferences(PREFS,MODE_PRIVATE).edit().putString(P_TOKEN,token).putBoolean(P_LIVE,live).putFloat(P_TOTAL,(float)total).putFloat(P_POSITION,(float)position).putBoolean(P_RUNNING,true).apply();
    }

    private void launchEngine(String token,boolean live,double total,double position){
        if(token==null || token.trim().isEmpty()){ updateNotification("START ERROR: Upstox access token is empty"); return; }
        startForeground(1,buildNotification("Starting "+(live?"LIVE":"MANUAL")+" Upstox 6× scanner..."));
        executor.execute(() -> startEngine(token,live,total,position));
    }

    private void startEngine(String token,boolean live,double total,double position){
        try{
            PyObject bridge=Python.getInstance().getModule("scanner_bridge");
            bridge.callAttr("start_engine","",token,live,total,position);
            started=true;
            updateNotification("Upstox "+(live?"LIVE":"MANUAL")+" • 6× scanner running");
            monitor(bridge);
        }catch(Exception e){
            started=false; getSharedPreferences(PREFS,MODE_PRIVATE).edit().putBoolean(P_RUNNING,false).apply();
            updateNotification("START ERROR: "+shortText(e.toString(),120));
        }
    }

    private void monitor(PyObject bridge){
        while(started){
            try{
                Thread.sleep(5000);
                JSONObject root=new JSONObject(bridge.callAttr("snapshot").toString());
                int scanned=root.optInt("stocks_scanned",0); int signals=root.optJSONArray("signals")!=null?root.optJSONArray("signals").length():0;
                updateNotification("6× Scanner • "+scanned+" scanned • "+signals+" signal(s)");
                JSONArray events=root.optJSONArray("events");
                if(events!=null&&events.length()>0){
                    JSONObject e=events.getJSONObject(0);
                    String key=e.optString("time")+"|"+e.optString("type")+"|"+e.optString("sym");
                    if(!key.equals(lastEventKey)){
                        lastEventKey=key; String type=e.optString("type");
                        if("BUY".equals(type)||"SELL".equals(type)||"TSL_ON".equals(type)||"ERROR".equals(type)) updateNotification(shortText(type+" "+e.optString("sym","")+(e.has("price")?" ₹"+e.optDouble("price"):""),110));
                    }
                }
            }catch(Exception ignored){}
        }
    }

    private void stopEngine(){ executor.execute(() -> { try{ Python.getInstance().getModule("scanner_bridge").callAttr("stop_engine"); }catch(Exception ignored){} }); }

    private Notification buildNotification(String text){
        Intent open=new Intent(this,MainActivity.class);
        PendingIntent pi=PendingIntent.getActivity(this,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this,CHANNEL_ID).setContentTitle("BEST INTRADAY • UPSTOX").setContentText(text).setSmallIcon(android.R.drawable.ic_menu_manage).setOngoing(true).setContentIntent(pi).setCategory(Notification.CATEGORY_SERVICE).build();
    }
    private void updateNotification(String text){ NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE); if(nm!=null) nm.notify(1,buildNotification(text)); }
    private void createChannel(){ if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.O){ NotificationChannel c=new NotificationChannel(CHANNEL_ID,"Upstox trading engine",NotificationManager.IMPORTANCE_LOW); c.setDescription("BEST INTRADAY 6x background engine"); NotificationManager nm=getSystemService(NotificationManager.class); if(nm!=null) nm.createNotificationChannel(c); } }
    private static String shortText(String s,int n){return s.length()<=n?s:s.substring(0,n);}

    @Override public void onDestroy(){ started=false; if(getSharedPreferences(PREFS,MODE_PRIVATE).getBoolean(P_RUNNING,false)) { /* sticky restart remains armed */ } stopEngine(); executor.shutdownNow(); super.onDestroy(); }
    @Override public IBinder onBind(Intent intent){return null;}
}
