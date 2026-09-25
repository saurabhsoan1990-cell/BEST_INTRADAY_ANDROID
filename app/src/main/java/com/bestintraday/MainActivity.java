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
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
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
 private static final String PREFS="best_intraday_upstox",TOKEN="upstox_token",TOTAL="total_capital",POSITION="position_capital",LIVE="live_mode";
 private static final int BG=Color.rgb(7,12,23),PANEL=Color.rgb(15,23,39),PANEL2=Color.rgb(20,30,49),TEXT=Color.rgb(241,245,249),MUTED=Color.rgb(139,153,176),BLUE=Color.rgb(65,132,255),GREEN=Color.rgb(38,194,137),RED=Color.rgb(239,86,86),LINE=Color.rgb(37,52,76),AMBER=Color.rgb(242,174,70);
 private EditText tokenInput,totalInput,positionInput; private RadioButton liveRadio,manualRadio; private LinearLayout root,dashboard,settings; private TextView engine,status,available,deployed,remaining,pnl,winrate,positions,trades,activity; private final ScheduledExecutorService refresh=Executors.newSingleThreadScheduledExecutor(); private final NumberFormat money=NumberFormat.getCurrencyInstance(new Locale("en","IN")); private int dp(float v){return (int)(v*getResources().getDisplayMetrics().density+0.5f);}
 @Override protected void onCreate(Bundle b){super.onCreate(b); if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},44); buildUi(); loadPrefs(); refresh.scheduleAtFixedRate(this::refreshDashboard,1,5,TimeUnit.SECONDS);}
 private GradientDrawable bg(int c,int s,int r){GradientDrawable g=new GradientDrawable();g.setColor(c);g.setCornerRadius(dp(r));if(s!=Color.TRANSPARENT)g.setStroke(dp(1),s);return g;}
 private TextView text(String s,float z,int c,boolean bold){TextView t=new TextView(this);t.setText(s);t.setTextSize(z);t.setTextColor(c);t.setTypeface(Typeface.DEFAULT,bold?Typeface.BOLD:Typeface.NORMAL);return t;}
 private TextView label(String s){TextView t=text(s.toUpperCase(Locale.US),10,MUTED,true);t.setLetterSpacing(.09f);return t;}
 private void gap(LinearLayout l,int h){TextView v=new TextView(this);l.addView(v,new LinearLayout.LayoutParams(1,dp(h)));}
 private LinearLayout card(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setPadding(dp(16),dp(14),dp(16),dp(14));l.setBackground(bg(PANEL,LINE,18));return l;}
 private TextView holder(TextView v){TextView h=text("",1,Color.TRANSPARENT,false);h.setTag(v);return h;}
 private TextView main(TextView h){Object x=h.getTag();return x instanceof TextView?(TextView)x:h;}
 private TextView cardSection(String title,String value,String sub){LinearLayout c=card();c.addView(label(title));TextView m=text(value,16,TEXT,true);m.setPadding(0,dp(5),0,0);c.addView(m);TextView s=text(sub,10,MUTED,false);s.setPadding(0,dp(4),0,0);c.addView(s);TextView h=holder(m);h.setBackground(bg(PANEL,LINE,18));return h;}
 private TextView metric(String title,String value){LinearLayout c=card();c.addView(label(title));TextView v=text(value,17,TEXT,true);v.setPadding(0,dp(5),0,0);c.addView(v,new LinearLayout.LayoutParams(-1,dp(34)));TextView h=holder(v);h.setBackground(bg(PANEL,LINE,18));return h;}
 private EditText field(String hint,boolean secret){EditText e=new EditText(this);e.setHint(hint);e.setHintTextColor(MUTED);e.setTextColor(TEXT);e.setTextSize(16);e.setSingleLine(true);e.setPadding(dp(14),0,dp(14),0);e.setBackground(bg(PANEL2,LINE,14));e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);e.setMinimumHeight(dp(50));return e;}
 private TextView tab(String s,boolean selected){TextView t=text(s,12,selected?TEXT:MUTED,true);t.setGravity(Gravity.CENTER);t.setBackground(bg(selected?PANEL2:BG,selected?BLUE:Color.TRANSPARENT,12));t.setPadding(dp(4),0,dp(4),0);return t;}
 private TextView button(String s,boolean primary){TextView t=text(s,12,TEXT,true);t.setGravity(Gravity.CENTER);t.setBackground(bg(primary?BLUE:PANEL2,primary?BLUE:LINE,14));t.setMinHeight(dp(48));return t;}
 private void buildUi(){
  root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(dp(16),dp(12),dp(16),dp(12));root.setBackgroundColor(BG);
  LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
  LinearLayout title=new LinearLayout(this);title.setOrientation(LinearLayout.VERTICAL);TextView brand=text("BEST INTRADAY",26,TEXT,true);TextView sub=text("LIVE TRADING TERMINAL  •  UPSTOX",11,MUTED,true);title.addView(brand);title.addView(sub);header.addView(title,new LinearLayout.LayoutParams(0,dp(58),1));
  TextView badge=text("6×\nSTRATEGY",11,TEXT,true);badge.setGravity(Gravity.CENTER);badge.setBackground(bg(Color.rgb(21,72,61),GREEN,18));header.addView(badge,new LinearLayout.LayoutParams(dp(86),dp(44)));root.addView(header);
  gap(root,10);
  LinearLayout nav=new LinearLayout(this);nav.setPadding(dp(3),dp(3),dp(3),dp(3));nav.setBackground(bg(PANEL,LINE,14));TextView db=tab("DASHBOARD",true),st=tab("SETTINGS",false);nav.addView(db,new LinearLayout.LayoutParams(0,dp(42),1));nav.addView(st,new LinearLayout.LayoutParams(0,dp(42),1));root.addView(nav);
  ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);LinearLayout content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(0,dp(10),0,dp(24));
  dashboard=new LinearLayout(this);dashboard.setOrientation(LinearLayout.VERTICAL);settings=new LinearLayout(this);settings.setOrientation(LinearLayout.VERTICAL);settings.setVisibility(View.GONE);
  engine=cardSection("ENGINE STATUS","OFFLINE","Ready to start • 6× entry locked");dashboard.addView(engine);gap(dashboard,10);
  LinearLayout m1=new LinearLayout(this);m1.setOrientation(LinearLayout.HORIZONTAL);available=metric("AVAILABLE","₹0");deployed=metric("DEPLOYED","₹0");remaining=metric("REMAINING","₹0");m1.addView(available,new LinearLayout.LayoutParams(0,dp(82),1));gapH(m1,8);m1.addView(deployed,new LinearLayout.LayoutParams(0,dp(82),1));gapH(m1,8);m1.addView(remaining,new LinearLayout.LayoutParams(0,dp(82),1));dashboard.addView(m1);gap(dashboard,10);
  LinearLayout m2=new LinearLayout(this);m2.setOrientation(LinearLayout.HORIZONTAL);pnl=metric("TODAY P&L","₹0");winrate=metric("WIN RATE","—");m2.addView(pnl,new LinearLayout.LayoutParams(0,dp(82),1));gapH(m2,8);m2.addView(winrate,new LinearLayout.LayoutParams(0,dp(82),1));dashboard.addView(m2);gap(dashboard,10);
  positions=cardSection("OPEN POSITIONS","None","No active positions");dashboard.addView(positions);gap(dashboard,10);trades=cardSection("TODAY'S TRADES","None","Completed trades appear here");dashboard.addView(trades);gap(dashboard,10);activity=cardSection("LIVE ACTIVITY","No events","Background engine event stream");dashboard.addView(activity);gap(dashboard,10);status=cardSection("SYSTEM","Ready","Service status");dashboard.addView(status);
  buildSettings();content.addView(dashboard);content.addView(settings);scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
  db.setOnClickListener(v->{db.setBackground(bg(PANEL2,BLUE,12));st.setBackground(bg(BG,Color.TRANSPARENT,12));dashboard.setVisibility(View.VISIBLE);settings.setVisibility(View.GONE);});
  st.setOnClickListener(v->{st.setBackground(bg(PANEL2,BLUE,12));db.setBackground(bg(BG,Color.TRANSPARENT,12));dashboard.setVisibility(View.GONE);settings.setVisibility(View.VISIBLE);});
 }
 private void gapH(LinearLayout l,int w){TextView x=new TextView(this);l.addView(x,new LinearLayout.LayoutParams(dp(w),1));}
 private void buildSettings(){
  TextView h=text("SETTINGS",24,TEXT,true);settings.addView(h);TextView q=text("Broker, capital and execution controls",11,MUTED,false);q.setPadding(0,dp(3),0,dp(18));settings.addView(q);
  settings.addView(label("UPSTOX CONNECTION"));gap(settings,6);tokenInput=field("Paste today's Upstox access token",true);settings.addView(tokenInput);TextView n=text("Stored locally on this phone. Replace when a new token is required.",10,MUTED,false);n.setPadding(dp(3),dp(6),dp(3),dp(14));settings.addView(n);
  settings.addView(label("CAPITAL MANAGEMENT"));gap(settings,6);totalInput=field("Total capital (₹)",false);settings.addView(totalInput);gap(settings,7);positionInput=field("Capital per stock (₹)",false);settings.addView(positionInput);gap(settings,16);
  settings.addView(label("EXECUTION MODE"));RadioGroup modes=new RadioGroup(this);manualRadio=new RadioButton(this);manualRadio.setText("MANUAL  •  signals / virtual trades");manualRadio.setTextColor(TEXT);manualRadio.setTextSize(15);liveRadio=new RadioButton(this);liveRadio.setText("LIVE  •  real Upstox orders");liveRadio.setTextColor(TEXT);liveRadio.setTextSize(15);manualRadio.setChecked(true);modes.addView(manualRadio);modes.addView(liveRadio);settings.addView(modes);gap(settings,14);
  settings.addView(label("STRATEGY LOCK"));gap(settings,6);LinearLayout rules=card();rules.addView(text("ENTRY",11,BLUE,true));rules.addView(text("Close > EMA200\nVolume ≥ 6× 20-bar volume MA\nClose > previous 20-bar high",13,TEXT,false));gap(rules,9);rules.addView(text("EXIT",11,AMBER,true));rules.addView(text("+1% activation  →  1% trailing stop\nNO EOD EXIT",13,TEXT,false));gap(rules,9);rules.addView(text("POSITION",11,GREEN,true));rules.addView(text("Maximum = floor(total capital / capital per stock)",13,TEXT,false));settings.addView(rules);gap(settings,16);
  LinearLayout ctl=new LinearLayout(this);TextView start=button("START ENGINE",true),stop=button("STOP ENGINE",false);start.setOnClickListener(v->startEngine());stop.setOnClickListener(v->stopEngine());ctl.addView(start,new LinearLayout.LayoutParams(0,dp(50),1));gapH(ctl,8);ctl.addView(stop,new LinearLayout.LayoutParams(0,dp(50),1));settings.addView(ctl);TextView warn=text("LIVE mode sends real orders. Verify your Upstox API/algo setup before enabling LIVE.",10,MUTED,false);warn.setPadding(dp(4),dp(12),dp(4),dp(12));settings.addView(warn);
 }
 private void loadPrefs(){SharedPreferences p=getSharedPreferences(PREFS,MODE_PRIVATE);tokenInput.setText(p.getString(TOKEN,""));totalInput.setText(p.getString(TOTAL,"5000000"));positionInput.setText(p.getString(POSITION,"200000"));boolean live=p.getBoolean(LIVE,false);liveRadio.setChecked(live);manualRadio.setChecked(!live);}
 private void savePrefs(){getSharedPreferences(PREFS,MODE_PRIVATE).edit().putString(TOKEN,tokenInput.getText().toString().trim()).putString(TOTAL,totalInput.getText().toString().trim()).putString(POSITION,positionInput.getText().toString().trim()).putBoolean(LIVE,liveRadio.isChecked()).apply();}
 private void startEngine(){savePrefs();String token=tokenInput.getText().toString().trim();if(token.isEmpty()){main(status).setText("Upstox access token is required.");Toast.makeText(this,"Enter your Upstox access token",Toast.LENGTH_SHORT).show();return;}double total,position;try{total=Double.parseDouble(totalInput.getText().toString());position=Double.parseDouble(positionInput.getText().toString());}catch(Exception e){main(status).setText("Enter valid capital amounts.");return;}if(total<=0||position<=0||position>total){main(status).setText("Per-stock capital must be >0 and ≤ total capital.");return;}Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_START);i.putExtra(TradingService.EXTRA_ACCESS_TOKEN,token);i.putExtra(TradingService.EXTRA_LIVE,liveRadio.isChecked());i.putExtra(TradingService.EXTRA_TOTAL,total);i.putExtra(TradingService.EXTRA_POSITION,position);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);main(status).setText((liveRadio.isChecked()?"LIVE":"MANUAL")+" engine start requested.");}
 private void stopEngine(){Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_STOP);startService(i);main(status).setText("Stop requested.");}
 private void refreshDashboard(){runOnUiThread(()->{try{PyObject bridge=Python.getInstance().getModule("scanner_bridge");JSONObject o=new JSONObject(bridge.callAttr("snapshot").toString());render(o);}catch(Exception e){}});}
 private String rs(double v){return money.format(v);}
 private void render(JSONObject o)throws Exception{boolean running=o.optBoolean("running",false),live=o.optBoolean("live",false);main(engine).setText((running?(live?"LIVE RUNNING":"MANUAL RUNNING"):"OFFLINE")+"\n6× ENTRY  •  "+o.optInt("max_positions",0)+" MAX POSITIONS  •  "+o.optString("last_update",""));JSONObject f=o.optJSONObject("funds");double avail=0;if(f!=null){JSONObject a=f.optJSONObject("available_to_trade");if(a!=null)avail=a.optDouble("total",0);}JSONArray ps=o.optJSONArray("positions");double used=0;if(ps!=null)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);used+=x.optDouble("entry")*x.optDouble("qty");}double total=o.optDouble("total_capital",0);main(available).setText(rs(avail));main(deployed).setText(rs(used));main(remaining).setText(rs(Math.max(0,total-used)));JSONArray tr=o.optJSONArray("trades");double day=0;int wins=0;StringBuilder tb=new StringBuilder();if(tr!=null)for(int i=0;i<tr.length();i++){JSONObject x=tr.getJSONObject(i);double pl=x.optDouble("pnl");day+=pl;if(pl>0)wins++;tb.append(x.optString("symbol")).append("   BUY ").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append("  →  SELL ").append(String.format(Locale.US,"%.2f",x.optDouble("exit"))).append("   ").append(rs(pl)).append("   ").append(x.optString("reason")).append("\n");}main(pnl).setText(rs(day));main(winrate).setText(tr==null||tr.length()==0?"—":String.format(Locale.US,"%.1f%%",100.0*wins/tr.length()));main(trades).setText(tb.length()==0?"No completed trades yet":tb.toString());StringBuilder pb=new StringBuilder();if(ps!=null&&ps.length()>0)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);pb.append(x.optString("symbol")).append("   ₹").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append("   ").append(x.optBoolean("active")?"TSL ACTIVE":"WAITING +1%").append(x.has("stop")&&!x.isNull("stop")?"   STOP ₹"+String.format(Locale.US,"%.2f",x.optDouble("stop")):"").append("\n");}main(positions).setText(pb.length()==0?"No active position":pb.toString());JSONArray ev=o.optJSONArray("events");StringBuilder eb=new StringBuilder();if(ev!=null)for(int i=0;i<Math.min(ev.length(),25);i++){JSONObject x=ev.getJSONObject(i);eb.append(x.optString("time")).append("   ").append(x.optString("type")).append(" ").append(x.optString("sym")).append(x.has("price")?" ₹"+String.format(Locale.US,"%.2f",x.optDouble("price")):"").append(x.has("text")?"   "+x.optString("text"):"").append("\n");}main(activity).setText(eb.length()==0?"No events yet":eb.toString());}
 @Override protected void onDestroy(){super.onDestroy();refresh.shutdownNow();}
}
