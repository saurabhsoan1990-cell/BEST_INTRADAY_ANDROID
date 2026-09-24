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
import java.text.NumberFormat;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONObject;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;

public class MainActivity extends Activity {
    private static final String PREFS="best_intraday_upstox", TOKEN="upstox_token", TOTAL="total_capital", POSITION="position_capital", LIVE="live_mode";
    private static final int BG=Color.rgb(7,12,23), PANEL=Color.rgb(15,23,39), PANEL2=Color.rgb(20,30,49), TEXT=Color.rgb(241,245,249), MUTED=Color.rgb(139,153,176), BLUE=Color.rgb(65,132,255), GREEN=Color.rgb(38,194,137), RED=Color.rgb(239,86,86), LINE=Color.rgb(37,52,76), AMBER=Color.rgb(242,174,70);
    private EditText tokenInput,totalInput,positionInput; private RadioButton liveRadio,manualRadio; private LinearLayout root,dashboard,settings,content; private TextView engine,funds,trades,positions,activity,status,available,deployed,remaining,pnl,winrate; private final ScheduledExecutorService refresh=Executors.newSingleThreadScheduledExecutor(); private final NumberFormat money=NumberFormat.getCurrencyInstance(new Locale("en","IN"));

    @Override protected void onCreate(Bundle b){super.onCreate(b); if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},44); buildUi();loadPrefs();refresh.scheduleAtFixedRate(this::refreshDashboard,1,5,TimeUnit.SECONDS);}
    private GradientDrawable bg(int c,int s,int r){GradientDrawable g=new GradientDrawable();g.setColor(c);g.setCornerRadius(r);g.setStroke(1,s);return g;}
    private TextView text(String s,float z,int c,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(z);t.setTextColor(c);t.setTypeface(Typeface.DEFAULT,bold?Typeface.BOLD:Typeface.NORMAL);return t;}
    private TextView label(String s){TextView t=text(s.toUpperCase(Locale.US),10,MUTED,true);t.setLetterSpacing(.08f);return t;}
    private TextView value(String s,float z){TextView t=text(s,z,TEXT,true);t.setGravity(Gravity.CENTER_VERTICAL);return t;}
    private LinearLayout box(int c){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(16,14,16,14);l.setBackground(bg(c,LINE,22));return l;}
    private void gap(LinearLayout l,int h){TextView v=new TextView(this);l.addView(v,new LinearLayout.LayoutParams(1,h));}
    private Button nav(String s,boolean on){Button b=new Button(this);b.setText(s);b.setTextColor(on?TEXT:MUTED);b.setTextSize(12);b.setAllCaps(false);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setBackground(bg(on?PANEL2:BG,on?BLUE:BG,18));return b;}
    private Button action(String s,boolean primary){Button b=new Button(this);b.setText(s);b.setTextColor(TEXT);b.setTextSize(12);b.setAllCaps(false);b.setTypeface(Typeface.DEFAULT,Typeface.BOLD);b.setBackground(bg(primary?BLUE:PANEL2,primary?BLUE:LINE,18));return b;}
    private EditText field(String hint,boolean secret){EditText e=new EditText(this);e.setHint(hint);e.setHintTextColor(MUTED);e.setTextColor(TEXT);e.setSingleLine(true);e.setPadding(14,2,14,2);e.setBackground(bg(PANEL2,LINE,16));e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);return e;}
    private TextView metric(String title,String val){LinearLayout c=box(PANEL);c.addView(label(title));TextView v=value(val,19);c.addView(v,new LinearLayout.LayoutParams(-1,38));return v;}

    private void buildUi(){
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(16,12,16,12);root.setBackgroundColor(BG);
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);TextView brand=text("BEST INTRADAY",22,TEXT,true);header.addView(brand,new LinearLayout.LayoutParams(0,52,1));TextView live=text("  6× STRATEGY  ",10,TEXT,true);live.setGravity(Gravity.CENTER);live.setBackground(bg(Color.rgb(21,72,61),GREEN,30));header.addView(live,new LinearLayout.LayoutParams(104,34));root.addView(header);
        TextView subtitle=text("LIVE TRADING TERMINAL  •  UPSTOX",10,MUTED,true);subtitle.setPadding(3,0,3,12);root.addView(subtitle);
        LinearLayout tabs=new LinearLayout(this);Button db=nav("Dashboard",true),st=nav("Settings",false);tabs.addView(db,new LinearLayout.LayoutParams(0,44,1));tabs.addView(st,new LinearLayout.LayoutParams(0,44,1));root.addView(tabs);gap(root,8);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);dashboard=new LinearLayout(this);dashboard.setOrientation(LinearLayout.VERTICAL);settings=new LinearLayout(this);settings.setOrientation(LinearLayout.VERTICAL);settings.setVisibility(View.GONE);
        engine=sectionCard("ENGINE STATUS","OFFLINE","Waiting for engine");dashboard.addView(engine);gap(dashboard,10);
        LinearLayout metrics=new LinearLayout(this);metrics.setOrientation(LinearLayout.HORIZONTAL);available=metric("AVAILABLE","₹0");deployed=metric("DEPLOYED","₹0");remaining=metric("REMAINING","₹0");metrics.addView(available,new LinearLayout.LayoutParams(0,82,1));addMargin(metrics,8);metrics.addView(deployed,new LinearLayout.LayoutParams(0,82,1));addMargin(metrics,8);metrics.addView(remaining,new LinearLayout.LayoutParams(0,82,1));dashboard.addView(metrics);gap(dashboard,10);
        LinearLayout stats=new LinearLayout(this);stats.setOrientation(LinearLayout.HORIZONTAL);pnl=metric("TODAY P&L","₹0");winrate=metric("WIN RATE","—");stats.addView(pnl,new LinearLayout.LayoutParams(0,82,1));addMargin(stats,8);stats.addView(winrate,new LinearLayout.LayoutParams(0,82,1));dashboard.addView(stats);gap(dashboard,10);
        positions=sectionCard("OPEN POSITIONS","None","No active position");dashboard.addView(positions);gap(dashboard,10);
        trades=sectionCard("TODAY'S TRADES","None","Completed trades appear here");dashboard.addView(trades);gap(dashboard,10);
        activity=sectionCard("LIVE ACTIVITY","No events","Engine activity stream");dashboard.addView(activity);gap(dashboard,10);
        status=sectionCard("SYSTEM","Ready","Background service status");dashboard.addView(status);
        buildSettings();content.addView(dashboard);content.addView(settings);scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
        db.setOnClickListener(v->{dashboard.setVisibility(View.VISIBLE);settings.setVisibility(View.GONE);});st.setOnClickListener(v->{dashboard.setVisibility(View.GONE);settings.setVisibility(View.VISIBLE);});
    }
    private void addMargin(LinearLayout l,int w){TextView x=new TextView(this);l.addView(x,new LinearLayout.LayoutParams(w,1));}
    private TextView sectionCard(String title,String main,String sub){LinearLayout c=box(PANEL);c.setMinimumHeight(76);c.addView(label(title));TextView m=value(main,17);m.setPadding(0,3,0,0);c.addView(m);TextView s=text(sub,10,MUTED,false);s.setPadding(0,2,0,0);c.addView(s);return new Holder(c,m);}
    private static class Holder extends TextView{Holder(LinearLayout parent,TextView main){super(parent.getContext());setTag(main);}}
    private void buildSettings(){
        TextView h=text("SETTINGS",24,TEXT,true);settings.addView(h);TextView q=text("Broker, capital and execution controls",11,MUTED,false);q.setPadding(0,2,0,18);settings.addView(q);
        settings.addView(label("UPSTOX CONNECTION"));gap(settings,6);tokenInput=field("Paste today's Upstox access token",true);settings.addView(tokenInput);TextView n=text("Stored locally on this phone. Replace when a new token is required.",10,MUTED,false);n.setPadding(3,6,3,12);settings.addView(n);
        settings.addView(label("CAPITAL MANAGEMENT"));gap(settings,6);totalInput=field("Total capital (₹)",false);settings.addView(totalInput);gap(settings,7);positionInput=field("Capital per stock (₹)",false);settings.addView(positionInput);gap(settings,14);
        settings.addView(label("EXECUTION MODE"));RadioGroup modes=new RadioGroup(this);manualRadio=new RadioButton(this);manualRadio.setText("MANUAL  •  signals / virtual trades");manualRadio.setTextColor(TEXT);liveRadio=new RadioButton(this);liveRadio.setText("LIVE  •  real Upstox orders");liveRadio.setTextColor(TEXT);manualRadio.setChecked(true);modes.addView(manualRadio);modes.addView(liveRadio);settings.addView(modes);gap(settings,12);
        settings.addView(label("STRATEGY LOCK"));gap(settings,6);LinearLayout rules=box(PANEL);rules.addView(text("ENTRY",11,BLUE,true));rules.addView(text("Close > EMA200\nVolume ≥ 6× 20-bar volume MA\nClose > previous 20-bar high",12,TEXT,false));gap(rules,8);rules.addView(text("EXIT",11,AMBER,true));rules.addView(text("+1% activation  →  1% trailing stop\nNO EOD EXIT",12,TEXT,false));gap(rules,8);rules.addView(text("POSITION",11,GREEN,true));rules.addView(text("Maximum = floor(total capital / capital per stock)",12,TEXT,false));settings.addView(rules);gap(settings,14);
        LinearLayout ctl=new LinearLayout(this);Button start=action("START ENGINE",true),stop=action("STOP",false);start.setOnClickListener(v->startEngine());stop.setOnClickListener(v->stopEngine());ctl.addView(start,new LinearLayout.LayoutParams(0,50,1));addMargin(ctl,8);ctl.addView(stop,new LinearLayout.LayoutParams(0,50,1));settings.addView(ctl);TextView warn=text("LIVE mode sends real orders. Verify your Upstox API/algo setup before enabling LIVE.",10,MUTED,false);warn.setPadding(4,12,4,12);settings.addView(warn);
    }
    private void loadPrefs(){SharedPreferences p=getSharedPreferences(PREFS,MODE_PRIVATE);tokenInput.setText(p.getString(TOKEN,""));totalInput.setText(p.getString(TOTAL,"5000000"));positionInput.setText(p.getString(POSITION,"200000"));boolean live=p.getBoolean(LIVE,false);liveRadio.setChecked(live);manualRadio.setChecked(!live);}
    private void savePrefs(){getSharedPreferences(PREFS,MODE_PRIVATE).edit().putString(TOKEN,tokenInput.getText().toString().trim()).putString(TOTAL,totalInput.getText().toString().trim()).putString(POSITION,positionInput.getText().toString().trim()).putBoolean(LIVE,liveRadio.isChecked()).apply();}
    private void startEngine(){savePrefs();String token=tokenInput.getText().toString().trim();if(token.isEmpty()){status.setText("SYSTEM\nUpstox access token is required.");return;}double total,position;try{total=Double.parseDouble(totalInput.getText().toString());position=Double.parseDouble(positionInput.getText().toString());}catch(Exception e){status.setText("SYSTEM\nEnter valid capital amounts.");return;}if(total<=0||position<=0||position>total){status.setText("SYSTEM\nPer-stock capital must be >0 and ≤ total capital.");return;}Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_START);i.putExtra(TradingService.EXTRA_ACCESS_TOKEN,token);i.putExtra(TradingService.EXTRA_LIVE,liveRadio.isChecked());i.putExtra(TradingService.EXTRA_TOTAL,total);i.putExtra(TradingService.EXTRA_POSITION,position);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);status.setText("SYSTEM\n"+(liveRadio.isChecked()?"LIVE":"MANUAL")+" engine start requested.");}
    private void stopEngine(){Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_STOP);startService(i);status.setText("SYSTEM\nStop requested.");}
    private void refreshDashboard(){runOnUiThread(()->{try{PyObject bridge=Python.getInstance().getModule("scanner_bridge");JSONObject o=new JSONObject(bridge.callAttr("snapshot").toString());render(o);}catch(Exception e){}});}
    private String rs(double v){return money.format(v);}
    private TextView main(TextView holder){Object t=holder.getTag();return t instanceof TextView?(TextView)t:holder;}
    private void render(JSONObject o)throws Exception{boolean running=o.optBoolean("running",false),live=o.optBoolean("live",false);engine.setText("ENGINE STATUS\n"+(running?(live?"LIVE RUNNING":"MANUAL RUNNING"):"OFFLINE")+"\n6× ENTRY  •  "+o.optInt("max_positions",0)+" MAX POSITIONS  •  "+o.optString("last_update",""));JSONObject f=o.optJSONObject("funds");double avail=0,cash=0;if(f!=null){JSONObject a=f.optJSONObject("available_to_trade");if(a!=null){avail=a.optDouble("total",0);JSONObject ca=a.optJSONObject("cash_available_to_trade");if(ca!=null)cash=ca.optDouble("total",0);}}JSONArray ps=o.optJSONArray("positions");double used=0;if(ps!=null)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);used+=x.optDouble("entry")*x.optDouble("qty");}double total=o.optDouble("total_capital",0);main(available).setText(rs(avail));main(deployed).setText(rs(used));main(remaining).setText(rs(Math.max(0,total-used)));JSONArray tr=o.optJSONArray("trades");double day=0;int wins=0;StringBuilder t=new StringBuilder("TODAY'S TRADES\n");if(tr!=null)for(int i=0;i<tr.length();i++){JSONObject x=tr.getJSONObject(i);double pl=x.optDouble("pnl");day+=pl;if(pl>0)wins++;t.append(x.optString("symbol")).append("   BUY ").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append("  →  SELL ").append(String.format(Locale.US,"%.2f",x.optDouble("exit"))).append("   ").append(rs(pl)).append("   ").append(x.optString("reason")).append("\n");}main(pnl).setText(rs(day));main(winrate).setText(tr==null||tr.length()==0?"—":String.format(Locale.US,"%.1f%%",100.0*wins/tr.length()));trades.setText(t.length()>15?t.toString():"TODAY'S TRADES\nNo completed trades yet\nCompleted trades appear here");StringBuilder p=new StringBuilder("OPEN POSITIONS\n");if(ps!=null&&ps.length()>0)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);p.append(x.optString("symbol")).append("   ₹").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append("   ").append(x.optBoolean("active")?"TSL ACTIVE":"WAITING +1%").append(x.has("stop")&&!x.isNull("stop")?"   STOP ₹"+String.format(Locale.US,"%.2f",x.optDouble("stop")):"").append("\n");}else p.append("No active position");positions.setText(p.toString());JSONArray ev=o.optJSONArray("events");StringBuilder e=new StringBuilder("LIVE ACTIVITY\n");if(ev!=null)for(int i=0;i<Math.min(ev.length(),25);i++){JSONObject x=ev.getJSONObject(i);e.append(x.optString("time")).append("   ").append(x.optString("type")).append(" ").append(x.optString("sym")).append(x.has("price")?" ₹"+String.format(Locale.US,"%.2f",x.optDouble("price")):"").append(x.has("text")?"   "+x.optString("text"):"").append("\n");}if(ev==null||ev.length()==0)e.append("No events yet");activity.setText(e.toString());}
    @Override protected void onDestroy(){super.onDestroy();refresh.shutdownNow();}
}
