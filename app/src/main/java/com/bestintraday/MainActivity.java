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
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;

import com.chaquo.python.Python;
import com.chaquo.python.PyObject;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.NumberFormat;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MainActivity extends Activity {
    private static final String PREFS="best_intraday_upstox", TOKEN="upstox_token", TOTAL="total_capital", POSITION="position_capital", LIVE="live_mode";
    private static final int BG=Color.rgb(8,15,29), SURFACE=Color.rgb(17,27,46), SURFACE2=Color.rgb(22,35,58), TEXT=Color.rgb(239,244,252), MUTED=Color.rgb(151,165,188), ACCENT=Color.rgb(72,142,255), GREEN=Color.rgb(39,196,137), RED=Color.rgb(242,91,91), BORDER=Color.rgb(39,55,80);
    private EditText tokenInput,totalInput,positionInput; private RadioButton liveRadio,manualRadio; private LinearLayout root,dashboard,settings; private TextView status,headline,fundsCard,positionsCard,tradesCard,eventsCard; private final ScheduledExecutorService refresh=Executors.newSingleThreadScheduledExecutor(); private final NumberFormat money=NumberFormat.getCurrencyInstance(new Locale("en","IN"));
    @Override protected void onCreate(Bundle b){super.onCreate(b); if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},44); buildUi();loadPrefs();refresh.scheduleAtFixedRate(this::refreshDashboard,1,5,TimeUnit.SECONDS);}
    private GradientDrawable bg(int color,int stroke){GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(24);g.setStroke(1,stroke);return g;}
    private TextView tv(String s,float size,int color,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(size);t.setTextColor(color);t.setTypeface(Typeface.DEFAULT,bold?Typeface.BOLD:Typeface.NORMAL);return t;}
    private TextView section(String s){TextView t=tv(s.toUpperCase(Locale.US),12,MUTED,true);t.setPadding(4,20,4,8);return t;}
    private TextView card(String title){TextView t=tv(title,14,TEXT,false);t.setPadding(20,18,20,18);t.setBackground(bg(SURFACE,BORDER));return t;}
    private EditText field(String hint,boolean secret){EditText e=new EditText(this);e.setHint(hint);e.setHintTextColor(MUTED);e.setTextColor(TEXT);e.setSingleLine(true);e.setPadding(16,4,16,4);e.setBackground(bg(SURFACE2,BORDER));e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);return e;}
    private Button button(String text,boolean primary){Button b=new Button(this);b.setText(text);b.setTextColor(TEXT);b.setTextSize(12);b.setAllCaps(false);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setBackground(bg(primary?ACCENT:SURFACE2,BORDER));return b;}
    private LinearLayout row(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.HORIZONTAL);return l;}
    private void addGap(LinearLayout l,int h){TextView x=new TextView(this);l.addView(x,new LinearLayout.LayoutParams(1,h));}

    private void buildUi(){
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(18,14,18,18);root.setBackgroundColor(BG);
        LinearLayout top=row();top.setGravity(Gravity.CENTER_VERTICAL);TextView title=tv("BEST INTRADAY",24,TEXT,true);top.addView(title,new LinearLayout.LayoutParams(0,56,1));TextView badge=tv(" 6× LIVE ",11,TEXT,true);badge.setGravity(Gravity.CENTER);badge.setBackground(bg(Color.rgb(24,83,74),Color.rgb(39,196,137)));top.addView(badge,new LinearLayout.LayoutParams(82,38));root.addView(top);
        TextView sub=tv("EMA200  •  20-BAR BREAKOUT  •  VOLUME ≥ 6×",11,MUTED,true);sub.setPadding(4,0,4,10);root.addView(sub);
        LinearLayout nav=row();Button db=button("Dashboard",true),st=button("Settings",false);nav.addView(db,new LinearLayout.LayoutParams(0,46,1));nav.addView(st,new LinearLayout.LayoutParams(0,46,1));root.addView(nav);
        dashboard=new LinearLayout(this);dashboard.setOrientation(LinearLayout.VERTICAL);
        headline=card("ENGINE  •  OFFLINE");dashboard.addView(headline);addGap(dashboard,8);
        fundsCard=card("FUNDS\nLoading...");dashboard.addView(fundsCard);addGap(dashboard,8);
        positionsCard=card("OPEN POSITIONS\nNone");dashboard.addView(positionsCard);addGap(dashboard,8);
        tradesCard=card("TODAY'S TRADES\nNone");dashboard.addView(tradesCard);addGap(dashboard,8);
        eventsCard=card("LIVE ACTIVITY\nNo events yet");dashboard.addView(eventsCard);addGap(dashboard,8);status=card("SYSTEM STATUS\nReady");dashboard.addView(status);
        settings=new LinearLayout(this);settings.setOrientation(LinearLayout.VERTICAL);settings.setVisibility(View.GONE);
        settings.addView(section("Broker connection"));settings.addView(tv("UPSTOX ACCESS TOKEN",11,MUTED,true));addGap(settings,5);tokenInput=field("Paste today's Upstox access token",true);settings.addView(tokenInput);TextView note=tv("Stored locally on this phone. Replace it when Upstox requires a new access token.",11,MUTED,false);note.setPadding(4,7,4,0);settings.addView(note);
        settings.addView(section("Capital controls"));settings.addView(tv("TOTAL CAPITAL (₹)",11,MUTED,true));addGap(settings,5);totalInput=field("Total capital",false);settings.addView(totalInput);addGap(settings,8);settings.addView(tv("CAPITAL PER STOCK (₹)",11,MUTED,true));addGap(settings,5);positionInput=field("Capital per stock",false);settings.addView(positionInput);
        settings.addView(section("Execution mode"));RadioGroup modes=new RadioGroup(this);manualRadio=new RadioButton(this);manualRadio.setText("MANUAL  •  signals / virtual trades");manualRadio.setTextColor(TEXT);liveRadio=new RadioButton(this);liveRadio.setText("LIVE  •  real Upstox orders");liveRadio.setTextColor(TEXT);manualRadio.setChecked(true);modes.addView(manualRadio);modes.addView(liveRadio);settings.addView(modes);
        settings.addView(section("Strategy lock"));TextView rules=card("6× ENTRY\nClose > EMA200\nVolume ≥ 6× 20-bar volume MA\nClose > previous 20-bar high\n\nEXIT\n+1% activation → 1% trailing stop\nNO EOD EXIT\n\nPOSITION\nMaximum = floor(total capital / capital per stock)");settings.addView(rules);
        addGap(settings,10);LinearLayout controls=row();Button start=button("Start engine",true);start.setOnClickListener(v->startEngine());Button stop=button("Stop",false);stop.setOnClickListener(v->stopEngine());controls.addView(start,new LinearLayout.LayoutParams(0,50,1));controls.addView(stop,new LinearLayout.LayoutParams(0,50,1));settings.addView(controls);
        TextView warn=tv("LIVE mode sends real orders. Make sure your Upstox API/algo setup is compliant before enabling LIVE.",11,MUTED,false);warn.setPadding(5,12,5,8);settings.addView(warn);
        db.setOnClickListener(v->{dashboard.setVisibility(View.VISIBLE);settings.setVisibility(View.GONE);});st.setOnClickListener(v->{dashboard.setVisibility(View.GONE);settings.setVisibility(View.VISIBLE);});
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.addView(dashboard);body.addView(settings);scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
    }
    private void loadPrefs(){SharedPreferences p=getSharedPreferences(PREFS,MODE_PRIVATE);tokenInput.setText(p.getString(TOKEN,""));totalInput.setText(p.getString(TOTAL,"5000000"));positionInput.setText(p.getString(POSITION,"200000"));boolean live=p.getBoolean(LIVE,false);liveRadio.setChecked(live);manualRadio.setChecked(!live);}
    private void savePrefs(){getSharedPreferences(PREFS,MODE_PRIVATE).edit().putString(TOKEN,tokenInput.getText().toString().trim()).putString(TOTAL,totalInput.getText().toString().trim()).putString(POSITION,positionInput.getText().toString().trim()).putBoolean(LIVE,liveRadio.isChecked()).apply();}
    private void startEngine(){savePrefs();String token=tokenInput.getText().toString().trim();if(token.isEmpty()){status.setText("SYSTEM STATUS\nUpstox access token is required.");return;}double total,position;try{total=Double.parseDouble(totalInput.getText().toString());position=Double.parseDouble(positionInput.getText().toString());}catch(Exception e){status.setText("SYSTEM STATUS\nEnter valid capital amounts.");return;}if(total<=0||position<=0||position>total){status.setText("SYSTEM STATUS\nPer-stock capital must be >0 and ≤ total capital.");return;}boolean live=liveRadio.isChecked();Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_START);i.putExtra(TradingService.EXTRA_ACCESS_TOKEN,token);i.putExtra(TradingService.EXTRA_LIVE,live);i.putExtra(TradingService.EXTRA_TOTAL,total);i.putExtra(TradingService.EXTRA_POSITION,position);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);status.setText("SYSTEM STATUS\n"+(live?"LIVE":"MANUAL")+" engine start requested.");}
    private void stopEngine(){Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_STOP);startService(i);status.setText("SYSTEM STATUS\nStop requested.");}
    private void refreshDashboard(){runOnUiThread(()->{try{PyObject bridge=Python.getInstance().getModule("scanner_bridge");JSONObject o=new JSONObject(bridge.callAttr("snapshot").toString());render(o);}catch(Exception e){headline.setText("ENGINE  •  OFFLINE");}});}
    private String rs(double v){return money.format(v).replace("₹","₹");}
    private void render(JSONObject o)throws Exception{boolean running=o.optBoolean("running",false),live=o.optBoolean("live",false);headline.setText("ENGINE  •  "+(running?(live?"LIVE RUNNING":"MANUAL RUNNING"):"OFFLINE")+"\n6× ENTRY  •  "+o.optInt("max_positions",0)+" MAX POSITIONS  •  UPDATED "+o.optString("last_update",""));JSONObject f=o.optJSONObject("funds");double avail=0,cash=0;if(f!=null){JSONObject a=f.optJSONObject("available_to_trade");if(a!=null){avail=a.optDouble("total",0);JSONObject ca=a.optJSONObject("cash_available_to_trade");if(ca!=null)cash=ca.optDouble("total",0);}}JSONArray ps=o.optJSONArray("positions");double used=0;if(ps!=null)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);used+=x.optDouble("entry")*x.optDouble("qty");}double total=o.optDouble("total_capital",0);fundsCard.setText("FUNDS & CAPITAL\nBroker available: "+rs(avail)+"\nCash available: "+rs(cash)+"\nStrategy capital: "+rs(total)+"\nCapital deployed: "+rs(used)+"\nCapital remaining: "+rs(Math.max(0,total-used))+"\nPer stock: "+rs(o.optDouble("position_capital",0)));StringBuilder p=new StringBuilder("OPEN POSITIONS  •  "+(ps==null?0:ps.length())+"\n");if(ps!=null)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);p.append(x.optString("symbol")).append("   ₹").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append("   ").append(x.optBoolean("active")?"TSL ACTIVE":"WAITING +1%").append(x.has("stop")&&!x.isNull("stop")?"   STOP ₹"+String.format(Locale.US,"%.2f",x.optDouble("stop")):"").append("\n");}positionsCard.setText(p.toString());JSONArray tr=o.optJSONArray("trades");StringBuilder t=new StringBuilder("TODAY'S TRADES\n");if(tr!=null)for(int i=0;i<Math.min(tr.length(),50);i++){JSONObject x=tr.getJSONObject(i);t.append(x.optString("symbol")).append("   BUY ₹").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append(" → SELL ₹").append(String.format(Locale.US,"%.2f",x.optDouble("exit"))).append("   ").append(rs(x.optDouble("pnl"))).append("   ").append(x.optString("reason")).append("\n");}if(tr==null||tr.length()==0)t.append("No completed trades yet.");tradesCard.setText(t.toString());JSONArray ev=o.optJSONArray("events");StringBuilder e=new StringBuilder("LIVE ACTIVITY\n");if(ev!=null)for(int i=0;i<Math.min(ev.length(),30);i++){JSONObject x=ev.getJSONObject(i);e.append(x.optString("time")).append("   ").append(x.optString("type")).append(" ").append(x.optString("sym")).append(x.has("price")?" ₹"+String.format(Locale.US,"%.2f",x.optDouble("price")):"").append(x.has("text")?"   "+x.optString("text"):"").append("\n");}eventsCard.setText(e.toString());}
    @Override protected void onDestroy(){super.onDestroy();refresh.shutdownNow();}
}
