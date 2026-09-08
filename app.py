
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests, io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from copy import copy

st.set_page_config(page_title="Nifty 200 Bullish Scanner", layout="wide")
st.title("Nifty 200 Bullish â€” Ichimoku + Volume + MACD")
st.caption("Same 1H + 15M + 5M scoring logic as the Colab version.")

INDEX_URL="https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
MAX_MACD_SIGNAL_AGE=3
MACD_FAST,MACD_SLOW,MACD_SIGNAL=12,26,9
MAX_WORKERS=8

@st.cache_data(ttl=900, show_spinner=False)
def nifty200():
    h={"User-Agent":"Mozilla/5.0"}
    r=requests.get(INDEX_URL,headers=h,timeout=20); r.raise_for_status()
    d=pd.read_csv(io.StringIO(r.text))
    c=next((x for x in d.columns if str(x).strip().lower() in ["symbol","symbol name"]),d.columns[0])
    return [x for x in d[c].astype(str).str.strip().str.upper() if x and x!="NAN"]

@st.cache_data(ttl=300, show_spinner=False)
def downloads():
    sy=[x+".NS" for x in nifty200()]
    out={}
    for tf,period in [("5m","5d"),("15m","5d"),("1h","30d")]:
        out[tf]=yf.download(sy,period=period,interval=("60m" if tf=="1h" else tf),
                            group_by="ticker",auto_adjust=False,progress=False,threads=True)
    return out

def stock(bulk,t):
    try:
        if isinstance(bulk.columns,pd.MultiIndex):
            if t in bulk.columns.get_level_values(0): d=bulk[t].copy()
            elif t in bulk.columns.get_level_values(1): d=bulk.xs(t,level=1,axis=1).copy()
            else:return None
        else:d=bulk.copy()
        d=d[["Open","High","Low","Close","Volume"]].apply(pd.to_numeric,errors="coerce").dropna()
        if getattr(d.index,"tz",None) is not None:d.index=d.index.tz_convert("Asia/Kolkata").tz_localize(None)
        return d
    except:return None

def ichi(d):
    d=d.copy(); h,l=d.High,d.Low
    d["Tenkan"]=(h.rolling(9).max()+l.rolling(9).min())/2
    d["Kijun"]=(h.rolling(26).max()+l.rolling(26).min())/2
    d["Span_A"]=(d.Tenkan+d.Kijun)/2
    d["Span_B"]=(h.rolling(52).max()+l.rolling(52).min())/2
    d["Cloud_Top"]=d[["Span_A","Span_B"]].max(axis=1)
    d["Cloud_Bottom"]=d[["Span_A","Span_B"]].min(axis=1)
    return d

def volume(d):
    d=d.copy(); d["Volume_Avg20"]=d.Volume.rolling(20).mean()
    d["Volume_Ratio"]=d.Volume/d.Volume_Avg20
    d["Volume_Avg5"]=d.Volume.rolling(5).mean()
    return d

def macd(d):
    d=d.copy(); a=d.Close.ewm(span=12,adjust=False).mean(); b=d.Close.ewm(span=26,adjust=False).mean()
    d["MACD"]=a-b; d["MACD_Signal"]=d.MACD.ewm(span=9,adjust=False).mean(); d["MACD_Hist"]=d.MACD-d.MACD_Signal
    return d

def cross(d,bull=True):
    a,b=d.Tenkan,d.Kijun; ix=[]
    for i in range(1,len(d)):
        if pd.notna(a.iloc[i-1]) and pd.notna(b.iloc[i-1]) and pd.notna(a.iloc[i]) and pd.notna(b.iloc[i]):
            if bull and a.iloc[i-1]<=b.iloc[i-1] and a.iloc[i]>b.iloc[i]:ix.append(i)
            if not bull and a.iloc[i-1]>=b.iloc[i-1] and a.iloc[i]<b.iloc[i]:ix.append(i)
    if not ix:return None,None
    i=ix[-1]; return len(d)-1-i,d.index[i]

def msig(d):
    m,s=d.MACD,d.MACD_Signal; ix=[]
    for i in range(1,len(d)):
        if pd.notna(m.iloc[i-1]) and pd.notna(s.iloc[i-1]) and pd.notna(m.iloc[i]) and pd.notna(s.iloc[i]):
            if m.iloc[i-1]<=s.iloc[i-1] and m.iloc[i]>s.iloc[i]:ix.append((i,"BUY"))
            elif m.iloc[i-1]>=s.iloc[i-1] and m.iloc[i]<s.iloc[i]:ix.append((i,"SELL"))
    if not ix:return "NONE",None,None
    i,x=ix[-1]; age=len(d)-1-i
    return (x if age<=MAX_MACD_SIGNAL_AGE else "NONE"),d.index[i],age

def score5(d):
    if d is None or len(d)<60:return None
    d=volume(macd(ichi(d))); r=d.iloc[-1]; s=0
    for c,p in [("Tenkan",10),("Kijun",10)]:
        if r.Close>r[c]:s+=p
    if r.Tenkan>r.Kijun:s+=15
    if r.Close>r.Cloud_Top:s+=10
    if r.Span_A>r.Span_B:s+=5
    if d.Tenkan.iloc[-1]>d.Tenkan.iloc[-2]:s+=5
    vr=r.Volume_Ratio
    if pd.notna(vr):s += 10 if vr>=2 else 8 if vr>=1.5 else 6 if vr>=1.2 else 4 if vr>=1 else 0
    ca,ct=cross(d,True); s += 15 if ca is not None and ca<=3 else 12 if ca is not None and ca<=6 else 8 if ca is not None and ca<=10 else 4 if ca is not None and ca<=15 else 0
    sig,mt,ma=msig(d); mb=12 if sig=="BUY" else -5 if sig=="SELL" else 0; s=max(0,min(100,s+mb))
    return dict(score=s,close=r.Close,tenkan=r.Tenkan,kijun=r.Kijun,span_a=r.Span_A,span_b=r.Span_B,cloud_top=r.Cloud_Top,cloud_bottom=r.Cloud_Bottom,volume=r.Volume,volume_avg20=r.Volume_Avg20,volume_ratio=vr,cross_age=ca,cross_time=ct,macd=r.MACD,macd_signal=r.MACD_Signal,macd_hist=r.MACD_Hist,macd_just_signal=sig,macd_cross_time=mt,macd_cross_age=ma,macd_bonus=mb)

def score15(d):
    if d is None or len(d)<60:return None
    d=volume(ichi(d)); r=d.iloc[-1]; s=0
    if r.Close>r.Tenkan:s+=10
    if r.Close>r.Kijun:s+=10
    if r.Tenkan>r.Kijun:s+=15
    if r.Close>r.Cloud_Top:s+=15
    if r.Span_A>r.Span_B:s+=10
    if d.Tenkan.iloc[-1]>d.Tenkan.iloc[-2]:s+=5
    vr=r.Volume_Ratio
    if pd.notna(vr):s+=10 if vr>=2 else 8 if vr>=1.5 else 6 if vr>=1.2 else 4 if vr>=1 else 0
    ca,ct=cross(d,True);s+=15 if ca is not None and ca<=2 else 12 if ca is not None and ca<=4 else 8 if ca is not None and ca<=8 else 4 if ca is not None and ca<=12 else 0
    return dict(score=max(0,min(100,s)),close=r.Close,tenkan=r.Tenkan,kijun=r.Kijun,span_a=r.Span_A,span_b=r.Span_B,cloud_top=r.Cloud_Top,cloud_bottom=r.Cloud_Bottom,volume_ratio=vr,cross_age=ca,cross_time=ct)

def score1(d):
    if d is None or len(d)<60:return None
    d=volume(ichi(d));r=d.iloc[-1];s=0
    if r.Close>r.Tenkan:s+=10
    if r.Close>r.Kijun:s+=10
    if r.Tenkan>r.Kijun:s+=10
    if r.Close>r.Cloud_Top:s+=15
    if r.Span_A>r.Span_B:s+=10
    if d.Tenkan.iloc[-1]>d.Tenkan.iloc[-2]:s+=5
    if d.Kijun.iloc[-1]>d.Kijun.iloc[-2]:s+=5
    vr=r.Volume_Ratio
    if pd.notna(vr):s+=15 if vr>=2 else 12 if vr>=1.5 else 9 if vr>=1.2 else 6 if vr>=1 else 3 if vr>=.8 else 0
    return dict(score=max(0,min(100,s)),close=r.Close,tenkan=r.Tenkan,kijun=r.Kijun,span_a=r.Span_A,span_b=r.Span_B,cloud_top=r.Cloud_Top,cloud_bottom=r.Cloud_Bottom,volume=r.Volume,volume_avg20=r.Volume_Avg20,volume_ratio=vr)

def process(t,ds):
    a,b,c=score5(stock(ds["5m"],t)),score15(stock(ds["15m"],t)),score1(stock(ds["1h"],t))
    if not all([a,b,c]):return None
    if not(c["close"]>c["tenkan"] and c["tenkan"]>c["kijun"] and b["close"]>b["tenkan"] and b["tenkan"]>b["kijun"] and a["close"]>a["tenkan"]):return None
    ratios=[x["volume_ratio"] for x in [a,b,c] if pd.notna(x["volume_ratio"])]
    av=np.mean(ratios) if ratios else 0
    vb=5 if av>=2 else 4 if av>=1.5 else 3 if av>=1.2 else 2 if av>=1 else 0
    fs=a["score"]*.20+b["score"]*.35+c["score"]*.45+vb+a["macd_bonus"];fs=max(0,min(100,fs))
    strength="VERY STRONG BULLISH" if fs>=85 else "STRONG BULLISH" if fs>=75 else "BULLISH" if fs>=65 else "MODERATE BULLISH" if fs>=55 else "WEAK BULLISH"
    rev="RECENT BULLISH ICHIMOKU REVERSAL" if a["cross_age"] is not None and a["cross_age"]<=10 else "RECENT MACD BULLISH REVERSAL" if a["macd_just_signal"]=="BUY" else "NONE"
    return {"Symbol":t.replace(".NS",""),"Bullish_Score":round(fs,2),"Strength":strength,"Signal":"BULLISH","Reversal":rev,
    "1H_Score":round(c["score"],2),"15M_Score":round(b["score"],2),"5M_Score":round(a["score"],2),"Price":round(a["close"],2),
    "1H_Tenkan":round(c["tenkan"],2),"1H_Kijun":round(c["kijun"],2),"1H_Span_A":round(c["span_a"],2),"1H_Span_B":round(c["span_b"],2),"1H_Cloud_Top":round(c["cloud_top"],2),"1H_Cloud_Bottom":round(c["cloud_bottom"],2),
    "15M_Tenkan":round(b["tenkan"],2),"15M_Kijun":round(b["kijun"],2),"15M_Span_A":round(b["span_a"],2),"15M_Span_B":round(b["span_b"],2),"15M_Cloud_Top":round(b["cloud_top"],2),"15M_Cloud_Bottom":round(b["cloud_bottom"],2),
    "5M_Tenkan":round(a["tenkan"],2),"5M_Kijun":round(a["kijun"],2),"5M_Span_A":round(a["span_a"],2),"5M_Span_B":round(a["span_b"],2),"5M_Cloud_Top":round(a["cloud_top"],2),"5M_Cloud_Bottom":round(a["cloud_bottom"],2),
    "Ichimoku_Bullish_Cross_Age_5M":a["cross_age"],"Ichimoku_Bullish_Cross_Time":a["cross_time"],
    "1H_Volume":c["volume"],"1H_Avg_Volume20":round(c["volume_avg20"],0),"1H_Volume_Ratio":round(c["volume_ratio"],2),"15M_Volume_Ratio":round(b["volume_ratio"],2),"5M_Volume":a["volume"],"5M_Avg_Volume20":round(a["volume_avg20"],0),"5M_Volume_Ratio":round(a["volume_ratio"],2),"Volume_Bonus":vb,
    "5M_MACD":round(a["macd"],4),"5M_MACD_Signal":round(a["macd_signal"],4),"5M_MACD_Hist":round(a["macd_hist"],4),"MACD_Just_Signal":a["macd_just_signal"],"MACD_Cross_Time":a["macd_cross_time"],"MACD_Cross_Age":a["macd_cross_age"],"MACD_Bonus":a["macd_bonus"]}

def scan():
    ds=downloads(); sy=[x+".NS" for x in nifty200()]; out=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs=[ex.submit(process,t,ds) for t in sy]
        for f in as_completed(fs):
            try:
                x=f.result()
                if x:out.append(x)
            except:pass
    d=pd.DataFrame(out)
    if d.empty:return d
    d=d.sort_values(["Bullish_Score","1H_Score","15M_Score","5M_Score","5M_Volume_Ratio"],ascending=False).reset_index(drop=True)
    d.insert(0,"Rank",range(1,len(d)+1));return d

if st.button("Scan Nifty 200",type="primary"):
    with st.spinner("Downloading 1H, 15M and 5M data and scanning..."):
        df=scan()
    if df.empty:st.warning("No bullish stocks matched the current structure.")
    else:
        st.success(f"{len(df)} bullish stocks found")
        st.dataframe(df,use_container_width=True,hide_index=True)
        bio=io.BytesIO()
        with pd.ExcelWriter(bio,engine="openpyxl") as w:
            df.to_excel(w,sheet_name="Bullish Stocks",index=False)
            ws=w.book["Bullish Stocks"];ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:
                f=copy(cell.font);f.bold=True;cell.font=f
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width=min(max(max(len(str(x.value)) if x.value is not None else 0 for x in col)+2,10),28)
        st.download_button("Download Excel",data=bio.getvalue(),file_name="Nifty200_Ichimoku_Volume_MACD.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
