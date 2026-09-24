package com.bestintraday;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
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
    private static final String PREFS = "best_intraday_upstox";
    private static final String TOKEN = "upstox_token";
    private static final String TOTAL = "total_capital";
    private static final String POSITION = "position_capital";
    private static final String LIVE = "live_mode";

    private EditText tokenInput, totalInput, positionInput;
    private RadioButton liveRadio, manualRadio;
    private LinearLayout root, dashboard, settings;
    private TextView status, headline, fundsCard, positionsCard, tradesCard, eventsCard;
    private final ScheduledExecutorService refresh = Executors.newSingleThreadScheduledExecutor();
    private final NumberFormat money = NumberFormat.getCurrencyInstance(new Locale("en", "IN"));

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 44);
        buildUi(); loadPrefs(); refresh.scheduleAtFixedRate(this::refreshDashboard, 1, 5, TimeUnit.SECONDS);
    }
    private TextView label(String text){TextView t=new TextView(this);t.setText(text);t.setTextSize(13);t.setTypeface(Typeface.DEFAULT,Typeface.BOLD);t.setPadding(0,14,0,6);return t;}
    private TextView card(String title){TextView t=new TextView(this);t.setText(title);t.setTextSize(15);t.setPadding(20,18,20,18);t.setBackgroundResource(android.R.drawable.dialog_holo_light_frame);return t;}
    private EditText field(String hint,boolean secret){EditText e=new EditText(this);e.setHint(hint);e.setSingleLine(true);e.setPadding(0,10,0,10);e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_DECIMAL);return e;}
    private Button nav(String text){Button b=new Button(this);b.setText(text);return b;}

    private void buildUi(){
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(22,18,22,18);
        TextView title=new TextView(this);title.setText("BEST INTRADAY  •  UPSTOX");title.setTextSize(24);title.setTypeface(Typeface.DEFAULT,Typeface.BOLD);root.addView(title);
        TextView sub=new TextView(this);sub.setText("6× LIVE ENGINE  |  EMA200 + 20-bar breakout + 20-bar volume MA");sub.setTextSize(13);root.addView(sub);
        LinearLayout navs=new LinearLayout(this);navs.setGravity(Gravity.CENTER);Button db=nav("DASHBOARD"),st=nav("SETTINGS");navs.addView(db,new LinearLayout.LayoutParams(0,-2,1));navs.addView(st,new LinearLayout.LayoutParams(0,-2,1));root.addView(navs);
        dashboard=new LinearLayout(this);dashboard.setOrientation(LinearLayout.VERTICAL);
        headline=card("ENGINE: OFFLINE");dashboard.addView(headline);fundsCard=card("FUNDS\nLoading...");dashboard.addView(fundsCard);positionsCard=card("OPEN POSITIONS\nNone");dashboard.addView(positionsCard);tradesCard=card("TODAY'S TRADES\nNone");dashboard.addView(tradesCard);eventsCard=card("LIVE ACTIVITY\nNo events yet");dashboard.addView(eventsCard);status=card("Ready");dashboard.addView(status);
        settings=new LinearLayout(this);settings.setOrientation(LinearLayout.VERTICAL);settings.setVisibility(View.GONE);
        settings.addView(label("UPSTOX ACCESS TOKEN"));tokenInput=field("Paste today's Upstox access token",true);settings.addView(tokenInput);
        TextView note=new TextView(this);note.setText("Token is stored locally on this phone. Upstox access tokens expire according to Upstox's token policy; refresh it in this screen when needed.");note.setTextSize(12);settings.addView(note);
        settings.addView(label("TOTAL CAPITAL (₹)"));totalInput=field("Total capital",false);settings.addView(totalInput);settings.addView(label("CAPITAL PER STOCK (₹)"));positionInput=field("Capital per stock",false);settings.addView(positionInput);
        settings.addView(label("START MODE"));RadioGroup modes=new RadioGroup(this);manualRadio=new RadioButton(this);manualRadio.setText("MANUAL — scan/virtual trades only");liveRadio=new RadioButton(this);liveRadio.setText("LIVE — place real Upstox orders");manualRadio.setChecked(true);modes.addView(manualRadio);modes.addView(liveRadio);settings.addView(modes);
        settings.addView(card("LOCKED 6× RULE\nBUY: close > EMA200 AND volume ≥ 6× 20-bar volume MA AND close > previous 20-bar high.\nEXIT: +1% activation, then 1% trailing stop. NO EOD EXIT.\nPosition limit = floor(total capital / per-stock capital)."));
        LinearLayout controls=new LinearLayout(this);Button start=new Button(this);start.setText("START BACKGROUND ENGINE");start.setOnClickListener(v->startEngine());Button stop=new Button(this);stop.setText("STOP");stop.setOnClickListener(v->stopEngine());controls.addView(start,new LinearLayout.LayoutParams(0,-2,1));controls.addView(stop,new LinearLayout.LayoutParams(0,-2,1));settings.addView(controls);
        TextView liveWarn=new TextView(this);liveWarn.setText("LIVE mode sends real orders. Test in MANUAL first. Upstox currently documents static-IP/algo controls for API order placement; LIVE orders can be rejected if your Upstox app/account setup is not compliant.");liveWarn.setTextSize(12);settings.addView(liveWarn);
        db.setOnClickListener(v->{dashboard.setVisibility(View.VISIBLE);settings.setVisibility(View.GONE);});st.setOnClickListener(v->{dashboard.setVisibility(View.GONE);settings.setVisibility(View.VISIBLE);});
        ScrollView scroll=new ScrollView(this);LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.addView(dashboard);body.addView(settings);scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);
    }
    private void loadPrefs(){SharedPreferences p=getSharedPreferences(PREFS,MODE_PRIVATE);tokenInput.setText(p.getString(TOKEN,""));totalInput.setText(p.getString(TOTAL,"5000000"));positionInput.setText(p.getString(POSITION,"200000"));boolean live=p.getBoolean(LIVE,false);liveRadio.setChecked(live);manualRadio.setChecked(!live);}
    private void savePrefs(){getSharedPreferences(PREFS,MODE_PRIVATE).edit().putString(TOKEN,tokenInput.getText().toString().trim()).putString(TOTAL,totalInput.getText().toString().trim()).putString(POSITION,positionInput.getText().toString().trim()).putBoolean(LIVE,liveRadio.isChecked()).apply();}
    private void startEngine(){savePrefs();String token=tokenInput.getText().toString().trim();if(token.isEmpty()){status.setText("ERROR: Upstox access token is required.");return;}double total,position;try{total=Double.parseDouble(totalInput.getText().toString());position=Double.parseDouble(positionInput.getText().toString());}catch(Exception e){status.setText("ERROR: enter valid capital amounts.");return;}if(total<=0||position<=0||position>total){status.setText("ERROR: per-stock capital must be >0 and <= total capital.");return;}boolean live=liveRadio.isChecked();Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_START);i.putExtra(TradingService.EXTRA_ACCESS_TOKEN,token);i.putExtra(TradingService.EXTRA_LIVE,live);i.putExtra(TradingService.EXTRA_TOTAL,total);i.putExtra(TradingService.EXTRA_POSITION,position);if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);status.setText((live?"LIVE":"MANUAL")+" engine start requested.");}
    private void stopEngine(){Intent i=new Intent(this,TradingService.class);i.setAction(TradingService.ACTION_STOP);startService(i);status.setText("Stop requested.");}
    private void refreshDashboard(){runOnUiThread(()->{try{PyObject bridge=Python.getInstance().getModule("scanner_bridge");JSONObject o=new JSONObject(bridge.callAttr("snapshot").toString());render(o);}catch(Exception e){headline.setText("ENGINE: OFFLINE");}});}
    private String rs(double v){return money.format(v).replace("₹","₹");}
    private void render(JSONObject o)throws Exception{
        boolean running=o.optBoolean("running",false),live=o.optBoolean("live",false);headline.setText("ENGINE: "+(running?(live?"LIVE RUNNING":"MANUAL RUNNING"):"OFFLINE")+"\n6× • "+o.optInt("max_positions",0)+" max positions • Updated "+o.optString("last_update",""));
        JSONObject f=o.optJSONObject("funds");double avail=0,cash=0;if(f!=null){JSONObject a=f.optJSONObject("available_to_trade");if(a!=null){avail=a.optDouble("total",0);JSONObject ca=a.optJSONObject("cash_available_to_trade");if(ca!=null)cash=ca.optDouble("total",0);}}
        JSONArray ps=o.optJSONArray("positions");double used=0;if(ps!=null)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);used+=x.optDouble("entry")*x.optDouble("qty");}
        double total=o.optDouble("total_capital",0);fundsCard.setText("FUNDS\nBroker available to trade: "+rs(avail)+"\nCash available: "+rs(cash)+"\nStrategy capital: "+rs(total)+"\nCapital deployed: "+rs(used)+"\nCapital remaining: "+rs(Math.max(0,total-used))+"\nPer stock: "+rs(o.optDouble("position_capital",0)));
        StringBuilder p=new StringBuilder("OPEN POSITIONS ("+(ps==null?0:ps.length())+")\n");if(ps!=null)for(int i=0;i<ps.length();i++){JSONObject x=ps.getJSONObject(i);p.append(x.optString("symbol")).append("  ₹").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append("  ").append(x.optBoolean("active")?"TSL ON":"waiting +1%").append(x.has("stop")&&!x.isNull("stop")?"  stop ₹"+String.format(Locale.US,"%.2f",x.optDouble("stop")):"").append("\n");}positionsCard.setText(p.toString());
        JSONArray tr=o.optJSONArray("trades");StringBuilder t=new StringBuilder("TODAY'S TRADES\n");if(tr!=null)for(int i=0;i<Math.min(tr.length(),50);i++){JSONObject x=tr.getJSONObject(i);t.append(x.optString("symbol")).append("  BUY ₹").append(String.format(Locale.US,"%.2f",x.optDouble("entry"))).append(" → SELL ₹").append(String.format(Locale.US,"%.2f",x.optDouble("exit"))).append("  ").append(rs(x.optDouble("pnl"))).append("  ").append(x.optString("reason")).append("\n");}if(tr==null||tr.length()==0)t.append("No completed trades yet.");tradesCard.setText(t.toString());
        JSONArray ev=o.optJSONArray("events");StringBuilder e=new StringBuilder("LIVE ACTIVITY\n");if(ev!=null)for(int i=0;i<Math.min(ev.length(),30);i++){JSONObject x=ev.getJSONObject(i);e.append(x.optString("time")).append("  ").append(x.optString("type")).append(" ").append(x.optString("sym")).append(x.has("price")?" ₹"+String.format(Locale.US,"%.2f",x.optDouble("price")):"").append(x.has("text")?"  "+x.optString("text"):"").append("\n");}eventsCard.setText(e.toString());
    }
    @Override protected void onDestroy(){super.onDestroy();refresh.shutdownNow();}
}
