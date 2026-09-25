package com.bestintraday;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.util.Locale;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONObject;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;

public class MainActivity extends Activity {
    private static final String PREFS="best_intraday_upstox", TOKEN="upstox_token", TOTAL="total_capital", POSITION="position_capital", LIVE="live_mode";
    private static final int BG=Color.rgb(5,14,25), PANEL=Color.rgb(8,27,42), PANEL2=Color.rgb(13,38,56), TEXT=Color.rgb(241,248,250), MUTED=Color.rgb(145,166,181), CYAN=Color.rgb(0,196,255), GREEN=Color.rgb(21,226,119), RED=Color.rgb(255,72,82), LINE=Color.rgb(25,58,78), AMBER=Color.rgb(255,190,63);
    private LinearLayout root, content; private EditText tokenInput,totalInput,positionInput; private RadioButton liveRadio,manualRadio; private JSONObject snapshot=new JSONObject();
    private final ScheduledExecutorService refresh=Executors.newSingleThreadScheduledExecutor();

    private int dp(int v){return (int)(v*getResources().getDisplayMetrics().density+0.5f);} 
    private GradientDrawable bg(int c,int stroke,int r){GradientDrawable g=new GradientDrawable();g.setColor(c);g.setCornerRadius(dp(r));if(stroke!=Color.TRANSPARENT)g.setStroke(dp(1),stroke);return g;}
    private TextView text(String s,float z,int c,boolean b){TextView t=new TextView(this);t.setText(s);t.setTextSize(z);t.setTextColor(c);t.setTypeface(Typeface.DEFAULT,b?Typeface.BOLD:Typeface.NORMAL);return t;}
    private TextView button(String s,int c){TextView t=text(s,13,TEXT,true);t.setGravity(Gravity.CENTER);t.setMinHeight(dp(48));t.setBackground(bg(c,c,12));return t;}
    private LinearLayout card(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(dp(14),dp(12),dp(14),dp(12));l.setBackground(bg(PANEL,LINE,14));return l;}
    private void gap(LinearLayout l,int h){TextView x=new TextView(this);l.addView(x,new LinearLayout.LayoutParams(1,dp(h)));}

    @Override protected void onCreate(Bundle b){super.onCreate(b);if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},44);build();refresh.scheduleAtFixedRate(this::refreshSnapshot,1,3,TimeUnit.SECONDS);}

    private void build(){
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(BG);
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(14),dp(10),dp(14),dp(8));
        LinearLayout ht=new LinearLayout(this);ht.setOrientation(LinearLayout.VERTICAL);ht.addView(text("BEST INTRADAY",22,TEXT,true));ht.addView(text("6X LIVE TRADING • REAL SCANNER",10,MUTED,true));header.addView(ht,new LinearLayout.LayoutParams(0,dp(58),1));
        TextView status=text("● OFFLINE",11,RED,true);status.setTag("status");header.addView(status);root.addView(header);
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(12),dp(5),dp(12),dp(20));ScrollView sc=new ScrollView(this);sc.addView(content);root.addView(sc,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);render();
    }

    private void render(){content.removeAllViews();
        LinearLayout controls=card(); controls.addView(text("ENGINE CONTROL",12,CYAN,true)); gap(controls,5);
        tokenInput=new EditText(this);tokenInput.setHint("Upstox access token");tokenInput.setHintTextColor(MUTED);tokenInput.setTextColor(TEXT);tokenInput.setSingleLine(true);tokenInput.setText(getPreferences());tokenInput.setBackground(bg(PANEL2,LINE,10));tokenInput.setPadding(dp(12),0,dp(12),0);tokenInput.setMinHeight(dp(50));controls.addView(tokenInput);
        gap(controls,7);
        LinearLayout money=new LinearLayout(this); totalInput=field("Total capital",getFloat(TOTAL,5000000));positionInput=field("Position capital",getFloat(POSITION,200000));money.addView(totalInput,new LinearLayout.LayoutParams(0,dp(50),1));TextView spacer=new TextView(this);money.addView(spacer,new LinearLayout.LayoutParams(dp(7),1));money.addView(positionInput,new LinearLayout.LayoutParams(0,dp(50),1));controls.addView(money);
        gap(controls,7); RadioGroup rg=new RadioGroup(this);rg.setOrientation(RadioGroup.HORIZONTAL);manualRadio=new RadioButton(this);manualRadio.setText(" Manual Trading");manualRadio.setTextColor(TEXT);liveRadio=new RadioButton(this);liveRadio.setText(" Live Trading");liveRadio.setTextColor(TEXT);rg.addView(manualRadio);rg.addView(liveRadio);rg.check(getBoolean(LIVE,false)?liveRadio.getId():manualRadio.getId()); if(liveRadio.getId()==-1){liveRadio.setId(1002);manualRadio.setId(1001);rg.check(getBoolean(LIVE,false)?1002:1001);} controls.addView(rg);
        gap(controls,7);LinearLayout buttons=new LinearLayout(this);TextView start=button("START ENGINE",GREEN),stop=button("STOP ENGINE",RED);buttons.addView(start,new LinearLayout.LayoutParams(0,dp(50),1));TextView s=new TextView(this);buttons.addView(s,new LinearLayout.LayoutParams(dp(7),1));buttons.addView(stop,new LinearLayout.LayoutParams(0,dp(50),1));controls.addView(buttons);content.addView(controls);gap(content,10);
        LinearLayout scan=card();scan.addView(text("LIVE MARKET SCAN",16,CYAN,true));scan.addView(text("Real results from the Upstox 6× engine — no demo stocks",10,MUTED,false));gap(scan,7);addScan(scan);content.addView(scan);gap(content,10);
        LinearLayout events=card();events.addView(text("ENGINE ACTIVITY",13,CYAN,true));addEvents(events);content.addView(events);
        start.setOnClickListener(v->startEngine());stop.setOnClickListener(v->stopEngine());
    }

    private EditText field(String hint,double val){EditText e=new EditText(this);e.setHint(hint);e.setHintTextColor(MUTED);e.setTextColor(TEXT);e.setText(String.format(Locale.US,"%.0f",val));e.setSingleLine(true);e.setBackground(bg(PANEL2,LINE,10));e.setPadding(dp(12),0,dp(12),0);return e;}
    private String getPreferences(){return getSharedPreferences(PREFS,MODE_PRIVATE).getString(TOKEN,"");}
    private double getFloat(String k,double d){return getSharedPreferences(PREFS,MODE_PRIVATE).getFloat(k,(float)d);}
    private boolean getBoolean(String k,boolean d){return getSharedPreferences(PREFS,MODE_PRIVATE).getBoolean(k,d);}

    private void startEngine(){
        String token=tokenInput.getText().toString().trim(); if(token.isEmpty()){Toast.makeText(this,"Enter Upstox access token",Toast.LENGTH_LONG).show();return;}
        double total=parse(totalInput.getText().toString(),5000000), position=parse(positionInput.getText().toString(),200000); boolean live=liveRadio.isChecked();
        getSharedPreferences(PREFS,MODE_PRIVATE).edit().putString(TOKEN,token).putFloat(TOTAL,(float)total).putFloat(POSITION,(float)position).putBoolean(LIVE,live).apply();
        Intent i=new Intent(this,TradingService.class).setAction(TradingService.ACTION_START).putExtra(TradingService.EXTRA_ACCESS_TOKEN,token).putExtra(TradingService.EXTRA_LIVE,live).putExtra(TradingService.EXTRA_TOTAL,total).putExtra(TradingService.EXTRA_POSITION,position);
        if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i); Toast.makeText(this,"Engine started — it stays in background until Stop Engine",Toast.LENGTH_LONG).show();
    }
    private void stopEngine(){startService(new Intent(this,TradingService.class).setAction(TradingService.ACTION_STOP));Toast.makeText(this,"Engine stopped",Toast.LENGTH_SHORT).show();}
    private double parse(String s,double d){try{return Double.parseDouble(s.replace(",",""));}catch(Exception e){return d;}}

    private void refreshSnapshot(){try{PyObject b=Python.getInstance().getModule("scanner_bridge");JSONObject x=new JSONObject(b.callAttr("snapshot").toString());runOnUiThread(()->{snapshot=x;render();});}catch(Exception ignored){}}

    private void addScan(LinearLayout l){
        int scanned=snapshot.optInt("stocks_scanned",0); JSONArray signals=snapshot.optJSONArray("signals"); int sig=signals==null?0:signals.length();
        l.addView(text(scanned+" stocks scanned  •  "+sig+" real signal(s)",12,TEXT,true)); gap(l,7);
        JSONArray arr=snapshot.optJSONArray("scan_results"); if(arr==null||arr.length()==0){l.addView(text(snapshot.optBoolean("running",false)?"Scanner warming up / waiting for live candles…":"Engine stopped",11,MUTED,false));return;}
        int shown=0; for(int i=0;i<arr.length()&&shown<25;i++){try{JSONObject x=arr.getJSONObject(i);if(!x.optBoolean("signal",false))continue;LinearLayout c=card();LinearLayout h=new LinearLayout(this);h.addView(text(x.optString("symbol"),14,TEXT,true),new LinearLayout.LayoutParams(0,dp(30),1));h.addView(text("6X BUY",11,GREEN,true));c.addView(h);c.addView(text(String.format(Locale.US,"Price ₹%.2f  •  Vol %.1fx  •  EMA200 %.2f",x.optDouble("price"),x.optDouble("volume_multiple"),x.optDouble("ema200")),10,MUTED,false));l.addView(c);gap(l,5);shown++;}catch(Exception ignored){}}
        if(shown==0)l.addView(text("No stock currently meets all 6X filters.",11,MUTED,false));
    }

    private void addEvents(LinearLayout l){JSONArray a=snapshot.optJSONArray("events");if(a==null||a.length()==0){l.addView(text("No events yet.",11,MUTED,false));return;}for(int i=0;i<Math.min(12,a.length());i++){try{JSONObject e=a.getJSONObject(i);String line=e.optString("type")+"  "+e.optString("sym")+"  "+e.optString("text");l.addView(text(line,10,e.optString("type").equals("ERROR")?RED:TEXT,false));}catch(Exception ignored){}}}

    @Override protected void onDestroy(){refresh.shutdownNow();super.onDestroy();}
}
