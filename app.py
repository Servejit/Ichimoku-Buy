# ============================================================
# NIFTY 200 — ICHIMOKU + VOLUME + MACD BULLISH SCANNER
# STREAMLIT VERSION
# ============================================================
#
# SAME CORE LOGIC AS COLAB VERSION
#
# 5M  = intraday momentum + fresh MACD signal
# 15M = intraday Ichimoku confirmation
# 1H  = major trend confirmation
#
# Ranking:
#   1H Ichimoku       45%
#   15M Ichimoku      35%
#   5M Ichimoku       20%
#   Volume bonus
#   Fresh MACD bonus
#
# Excel:
#   Highest Bullish Score on top
#   Fresh MACD BUY/SELL shown
#   MACD cross time shown
#   Excel filters enabled
#   Freeze panes enabled
#   IST timezone handled
# ============================================================

import streamlit as st

# ------------------------------------------------------------
# INSTALLATION IS NOT NEEDED IN STREAMLIT CLOUD
# requirements.txt should contain:
#
# streamlit
# yfinance
# pandas
# numpy
# requests
# openpyxl
# ------------------------------------------------------------

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import warnings
import time
import io

from concurrent.futures import ThreadPoolExecutor, as_completed

from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter

warnings.filterwarnings("ignore")


# ============================================================
# STREAMLIT PAGE
# ============================================================

st.set_page_config(
    page_title="6thSense — NIFTY 200 Bullish Scanner",
    page_icon="📈",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 4px;
    }

    .sub-title {
        font-size: 16px;
        color: #666666;
        margin-bottom: 20px;
    }

    .metric-box {
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #dddddd;
        text-align: center;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# TITLE
# ============================================================

st.markdown(
    '<div class="main-title">Welcome to 6thSense Trading</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">'
    'NIFTY 200 — Ichimoku + Volume + MACD Bullish Scanner'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# SETTINGS
# ============================================================

MAX_WORKERS = 3

PERIOD_5M = "5d"
PERIOD_15M = "5d"
PERIOD_1H = "30d"

MIN_BULLISH_SCORE = 45

MAX_MACD_SIGNAL_AGE = 3

TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_PERIOD = 52

VOLUME_PERIOD = 20

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

IST = "Asia/Kolkata"


# ============================================================
# SESSION STATE
# ============================================================

if "scan_results" not in st.session_state:

    st.session_state.scan_results = None

if "last_scan_time" not in st.session_state:

    st.session_state.last_scan_time = None

if "scan_error" not in st.session_state:

    st.session_state.scan_error = None


# ============================================================
# TOP CONTROLS
# ============================================================

col1, col2, col3 = st.columns(
    [1.2, 1.2, 2.5]
)

with col1:

    scan_button = st.button(
        "🔄 Scan NIFTY 200",
        use_container_width=True,
        type="primary"
    )

with col2:

    clear_button = st.button(
        "🗑️ Clear",
        use_container_width=True
    )

with col3:

    st.info(
        "5M + 15M + 1H | "
        "Ichimoku + Volume + Fresh MACD"
    )


if clear_button:

    st.session_state.scan_results = None
    st.session_state.last_scan_time = None
    st.session_state.scan_error = None

    st.rerun()


# ============================================================
# NIFTY 200
# ============================================================

NIFTY_URL = (
    "https://www.niftyindices.com/"
    "IndexConstituent/ind_nifty200list.csv"
)


def get_nifty200():

    headers = {

        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36",

        "Accept":
            "text/csv,application/csv,text/plain,*/*",

        "Referer":
            "https://www.niftyindices.com/"
    }

    response = requests.get(
        NIFTY_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    df = pd.read_csv(
        io.BytesIO(
            response.content
        )
    )

    if "Symbol" not in df.columns:

        raise Exception(
            "NIFTY 200 CSV does not contain Symbol column."
        )

    symbols = (

        df["Symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
        .replace("NAN", np.nan)
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    return symbols


# ============================================================
# BULK DOWNLOAD
# ============================================================

def download_data(
    tickers,
    interval,
    period
):

    try:

        data = yf.download(

            tickers=tickers,

            period=period,

            interval=interval,

            auto_adjust=False,

            group_by="ticker",

            threads=True,

            progress=False
        )

        return data

    except Exception:

        return pd.DataFrame()


# ============================================================
# EXTRACT STOCK
# ============================================================

def get_stock_data(
    df,
    ticker
):

    if df is None or df.empty:

        return pd.DataFrame()

    try:

        if isinstance(
            df.columns,
            pd.MultiIndex
        ):

            level0 = [
                str(x)
                for x in
                df.columns.get_level_values(0)
            ]

            level1 = [
                str(x)
                for x in
                df.columns.get_level_values(1)
            ]

            if ticker in level0:

                out = df[ticker].copy()

            elif ticker in level1:

                out = df.xs(
                    ticker,
                    axis=1,
                    level=1
                ).copy()

            else:

                return pd.DataFrame()

        else:

            out = df.copy()

        rename = {}

        for c in out.columns:

            name = str(
                c
            ).strip().lower()

            if name == "open":
                rename[c] = "Open"

            elif name == "high":
                rename[c] = "High"

            elif name == "low":
                rename[c] = "Low"

            elif name == "close":
                rename[c] = "Close"

            elif name == "volume":
                rename[c] = "Volume"

        out = out.rename(
            columns=rename
        )

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        if not all(
            c in out.columns
            for c in required
        ):

            return pd.DataFrame()

        out = out[
            required
        ].copy()

        for c in required:

            out[c] = pd.to_numeric(
                out[c],
                errors="coerce"
            )

        out = out.dropna(
            subset=[
                "High",
                "Low",
                "Close"
            ]
        )

        if isinstance(
            out.index,
            pd.DatetimeIndex
        ):

            if out.index.tz is not None:

                out.index = (

                    out.index
                    .tz_convert(IST)
                    .tz_localize(None)
                )

            else:

                out.index = pd.to_datetime(
                    out.index
                )

        out = out.sort_index()

        out = out[
            ~out.index.duplicated(
                keep="last"
            )
        ]

        return out

    except Exception:

        return pd.DataFrame()


# ============================================================
# REMOVE INCOMPLETE CANDLE
# ============================================================

def remove_incomplete_last_candle(
    df,
    interval_minutes
):

    if df is None or df.empty:

        return df

    try:

        last_time = df.index[-1]

        now = pd.Timestamp.now(
            tz=IST
        ).tz_localize(None)

        expected_end = (

            last_time
            +
            pd.Timedelta(
                minutes=interval_minutes
            )
        )

        if expected_end > now:

            df = df.iloc[:-1].copy()

        return df

    except Exception:

        return df


# ============================================================
# ADD INDICATORS
# ============================================================

def add_indicators(df):

    df = df.copy()

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # --------------------------------------------------------
    # ICHIMOKU
    # --------------------------------------------------------

    df["Tenkan"] = (

        high.rolling(
            TENKAN_PERIOD
        ).max()

        +

        low.rolling(
            TENKAN_PERIOD
        ).min()

    ) / 2

    df["Kijun"] = (

        high.rolling(
            KIJUN_PERIOD
        ).max()

        +

        low.rolling(
            KIJUN_PERIOD
        ).min()

    ) / 2

    df["Span_A"] = (

        df["Tenkan"]
        +
        df["Kijun"]

    ) / 2

    df["Span_B"] = (

        high.rolling(
            SENKOU_PERIOD
        ).max()

        +

        low.rolling(
            SENKOU_PERIOD
        ).min()

    ) / 2

    df["Cloud_Top"] = df[
        [
            "Span_A",
            "Span_B"
        ]
    ].max(axis=1)

    df["Cloud_Bottom"] = df[
        [
            "Span_A",
            "Span_B"
        ]
    ].min(axis=1)

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    df["Volume_Avg20"] = (

        df["Volume"]
        .rolling(
            VOLUME_PERIOD
        )
        .mean()
    )

    df["Volume_Ratio"] = np.where(

        df["Volume_Avg20"] > 0,

        df["Volume"]
        /
        df["Volume_Avg20"],

        np.nan
    )

    df["Volume_Avg5"] = (

        df["Volume"]
        .rolling(5)
        .mean()
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema_fast = (

        close
        .ewm(
            span=MACD_FAST,
            adjust=False
        )
        .mean()
    )

    ema_slow = (

        close
        .ewm(
            span=MACD_SLOW,
            adjust=False
        )
        .mean()
    )

    df["MACD"] = (

        ema_fast
        -
        ema_slow
    )

    df["MACD_Signal"] = (

        df["MACD"]
        .ewm(
            span=MACD_SIGNAL,
            adjust=False
        )
        .mean()
    )

    df["MACD_Histogram"] = (

        df["MACD"]
        -
        df["MACD_Signal"]
    )

    # --------------------------------------------------------
    # MACD CROSS
    # --------------------------------------------------------

    df["MACD_Buy_Cross"] = (

        (
            df["MACD"].shift(1)
            <=
            df["MACD_Signal"].shift(1)
        )

        &

        (
            df["MACD"]
            >
            df["MACD_Signal"]
        )
    )

    df["MACD_Sell_Cross"] = (

        (
            df["MACD"].shift(1)
            >=
            df["MACD_Signal"].shift(1)
        )

        &

        (
            df["MACD"]
            <
            df["MACD_Signal"]
        )
    )

    return df


# ============================================================
# VOLUME SCORE
# ============================================================

def volume_score(value):

    if pd.isna(value):
        return 0

    if value >= 2:
        return 10

    elif value >= 1.5:
        return 8

    elif value >= 1.2:
        return 6

    elif value >= 1:
        return 3

    return 0


def volume_score_1h(value):

    if pd.isna(value):
        return 0

    if value >= 2:
        return 15

    elif value >= 1.5:
        return 12

    elif value >= 1.2:
        return 9

    elif value >= 1:
        return 5

    return 0


# ============================================================
# 5M ANALYSIS
# ============================================================

def analyze_5m(df):

    if df.empty:
        return None

    if len(df) < 80:
        return None

    df = remove_incomplete_last_candle(
        df,
        5
    )

    if len(df) < 80:
        return None

    df = add_indicators(df)

    df = df.dropna(
        subset=[
            "Tenkan",
            "Kijun",
            "Span_A",
            "Span_B",
            "MACD",
            "MACD_Signal"
        ]
    )

    if len(df) < 10:
        return None

    cur = df.iloc[-1]

    prev = df.iloc[-2]

    score = 0

    # --------------------------------------------------------
    # ICHIMOKU
    # --------------------------------------------------------

    if cur["Close"] > cur["Tenkan"]:
        score += 10

    if cur["Close"] > cur["Kijun"]:
        score += 10

    if cur["Tenkan"] > cur["Kijun"]:
        score += 15

    if cur["Close"] > cur["Cloud_Top"]:
        score += 10

    if cur["Span_A"] > cur["Span_B"]:
        score += 5

    if cur["Tenkan"] > prev["Tenkan"]:
        score += 5

    # --------------------------------------------------------
    # VOLUME
    # --------------------------------------------------------

    score += volume_score(
        cur["Volume_Ratio"]
    )

    # --------------------------------------------------------
    # ICHIMOKU CROSS
    # --------------------------------------------------------

    cross_condition = (

        (
            df["Tenkan"].shift(1)
            <=
            df["Kijun"].shift(1)
        )

        &

        (
            df["Tenkan"]
            >
            df["Kijun"]
        )
    )

    cross_positions = np.where(
        cross_condition.fillna(False)
    )[0]

    cross_age = ""

    cross_time = ""

    if len(cross_positions):

        pos = cross_positions[-1]

        cross_age = (
            len(df)
            -
            1
            -
            pos
        )

        cross_time = df.index[pos]

    # --------------------------------------------------------
    # MACD CROSS
    # --------------------------------------------------------

    macd_signal = "NONE"

    macd_cross_time = ""

    macd_cross_age = ""

    buy_positions = np.where(
        df["MACD_Buy_Cross"]
        .fillna(False)
    )[0]

    sell_positions = np.where(
        df["MACD_Sell_Cross"]
        .fillna(False)
    )[0]

    all_crosses = []

    for p in buy_positions:

        all_crosses.append(
            (
                p,
                "BUY"
            )
        )

    for p in sell_positions:

        all_crosses.append(
            (
                p,
                "SELL"
            )
        )

    if all_crosses:

        all_crosses.sort(
            key=lambda x: x[0]
        )

        p, signal = all_crosses[-1]

        age = (
            len(df)
            -
            1
            -
            p
        )

        macd_cross_age = age

        macd_cross_time = df.index[p]

        if age <= MAX_MACD_SIGNAL_AGE:

            macd_signal = signal

            if signal == "BUY":

                if age == 0:
                    score += 12

                elif age == 1:
                    score += 10

                elif age == 2:
                    score += 8

                elif age == 3:
                    score += 5

    return {

        "score": score,

        "close": cur["Close"],

        "tenkan": cur["Tenkan"],

        "kijun": cur["Kijun"],

        "span_a": cur["Span_A"],

        "span_b": cur["Span_B"],

        "cloud_top": cur["Cloud_Top"],

        "volume": cur["Volume"],

        "volume_avg20": cur["Volume_Avg20"],

        "volume_ratio": cur["Volume_Ratio"],

        "cross_age": cross_age,

        "cross_time": cross_time,

        "macd": cur["MACD"],

        "macd_signal_value":
            cur["MACD_Signal"],

        "macd_histogram":
            cur["MACD_Histogram"],

        "macd_just_signal":
            macd_signal,

        "macd_cross_time":
            macd_cross_time,

        "macd_cross_age":
            macd_cross_age
    }


# ============================================================
# 15M ANALYSIS
# ============================================================

def analyze_15m(df):

    if df.empty:
        return None

    if len(df) < 80:
        return None

    df = remove_incomplete_last_candle(
        df,
        15
    )

    if len(df) < 80:
        return None

    df = add_indicators(df)

    df = df.dropna(
        subset=[
            "Tenkan",
            "Kijun",
            "Span_A",
            "Span_B"
        ]
    )

    if len(df) < 3:
        return None

    cur = df.iloc[-1]

    prev = df.iloc[-2]

    score = 0

    if cur["Close"] > cur["Tenkan"]:
        score += 10

    if cur["Close"] > cur["Kijun"]:
        score += 10

    if cur["Tenkan"] > cur["Kijun"]:
        score += 15

    if cur["Close"] > cur["Cloud_Top"]:
        score += 15

    if cur["Span_A"] > cur["Span_B"]:
        score += 10

    if cur["Tenkan"] > prev["Tenkan"]:
        score += 5

    if cur["Kijun"] > prev["Kijun"]:
        score += 5

    score += volume_score(
        cur["Volume_Ratio"]
    )

    return {

        "score": score,

        "close": cur["Close"],

        "tenkan": cur["Tenkan"],

        "kijun": cur["Kijun"],

        "span_a": cur["Span_A"],

        "span_b": cur["Span_B"],

        "cloud_top": cur["Cloud_Top"],

        "volume_ratio":
            cur["Volume_Ratio"]
    }


# ============================================================
# 1H ANALYSIS
# ============================================================

def analyze_1h(df):

    if df.empty:
        return None

    if len(df) < 80:
        return None

    df = remove_incomplete_last_candle(
        df,
        60
    )

    if len(df) < 80:
        return None

    df = add_indicators(df)

    df = df.dropna(
        subset=[
            "Tenkan",
            "Kijun",
            "Span_A",
            "Span_B"
        ]
    )

    if len(df) < 3:
        return None

    cur = df.iloc[-1]

    prev = df.iloc[-2]

    score = 0

    if cur["Close"] > cur["Tenkan"]:
        score += 10

    if cur["Close"] > cur["Kijun"]:
        score += 10

    if cur["Tenkan"] > cur["Kijun"]:
        score += 10

    if cur["Close"] > cur["Cloud_Top"]:
        score += 15

    if cur["Span_A"] > cur["Span_B"]:
        score += 10

    if cur["Tenkan"] > prev["Tenkan"]:
        score += 5

    if cur["Kijun"] > prev["Kijun"]:
        score += 5

    score += volume_score_1h(
        cur["Volume_Ratio"]
    )

    return {

        "score": score,

        "close": cur["Close"],

        "tenkan": cur["Tenkan"],

        "kijun": cur["Kijun"],

        "span_a": cur["Span_A"],

        "span_b": cur["Span_B"],

        "cloud_top": cur["Cloud_Top"],

        "volume": cur["Volume"],

        "volume_avg20":
            cur["Volume_Avg20"],

        "volume_ratio":
            cur["Volume_Ratio"]
    }


# ============================================================
# FORMAT TIME
# ============================================================

def format_time(value):

    if value is None:
        return ""

    if value == "":
        return ""

    try:

        ts = pd.Timestamp(value)

        if ts.tzinfo is not None:

            ts = (
                ts
                .tz_convert(IST)
                .tz_localize(None)
            )

        return ts.strftime(
            "%d-%b-%Y %H:%M"
        )

    except Exception:

        return ""


# ============================================================
# COMPLETE STOCK ANALYSIS
# ============================================================

def analyze_stock(
    symbol,
    data_5m,
    data_15m,
    data_1h
):

    ticker = symbol + ".NS"

    try:

        d5 = get_stock_data(
            data_5m,
            ticker
        )

        d15 = get_stock_data(
            data_15m,
            ticker
        )

        d1h = get_stock_data(
            data_1h,
            ticker
        )

        if (
            d5.empty
            or d15.empty
            or d1h.empty
        ):

            return None

        r5 = analyze_5m(d5)

        r15 = analyze_15m(d15)

        r1h = analyze_1h(d1h)

        if (
            r5 is None
            or r15 is None
            or r1h is None
        ):

            return None

        # ====================================================
        # STRONG BULLISH STRUCTURE
        # ====================================================

        bullish_structure = (

            r1h["close"]
            >
            r1h["tenkan"]

            and

            r1h["tenkan"]
            >
            r1h["kijun"]

            and

            r15["close"]
            >
            r15["tenkan"]

            and

            r15["tenkan"]
            >
            r15["kijun"]

            and

            r5["close"]
            >
            r5["tenkan"]
        )

        if not bullish_structure:

            return None

        # ====================================================
        # WEIGHTED FINAL SCORE
        # ====================================================

        final_score = (

            r1h["score"]
            *
            0.45

            +

            r15["score"]
            *
            0.35

            +

            r5["score"]
            *
            0.20
        )

        # ====================================================
        # EXTRA VOLUME
        # ====================================================

        volume_values = [

            r1h["volume_ratio"],
            r15["volume_ratio"],
            r5["volume_ratio"]

        ]

        volume_values = [

            x
            for x in volume_values
            if pd.notna(x)
        ]

        avg_volume_ratio = np.nan

        volume_bonus = 0

        if volume_values:

            avg_volume_ratio = np.mean(
                volume_values
            )

            if avg_volume_ratio >= 2:

                volume_bonus = 5

            elif avg_volume_ratio >= 1.5:

                volume_bonus = 3

            elif avg_volume_ratio >= 1.2:

                volume_bonus = 2

        final_score += volume_bonus

        # ====================================================
        # MACD BONUS
        # ====================================================

        macd_bonus = 0

        if r5["macd_just_signal"] == "BUY":

            age = r5["macd_cross_age"]

            if age == 0:

                macd_bonus = 5

            elif age == 1:

                macd_bonus = 4

            elif age == 2:

                macd_bonus = 3

            elif age == 3:

                macd_bonus = 2

        final_score += macd_bonus

        # ====================================================
        # SCORE FILTER
        # ====================================================

        if final_score < MIN_BULLISH_SCORE:

            return None

        # ====================================================
        # MACD STATUS
        # ====================================================

        if r5["macd_just_signal"] == "BUY":

            macd_status = "FRESH BUY"

        elif r5["macd_just_signal"] == "SELL":

            macd_status = "FRESH SELL"

        else:

            macd_status = "NONE"

        # ====================================================
        # RATING
        # ====================================================

        if final_score >= 85:

            rating = "VERY STRONG"

        elif final_score >= 70:

            rating = "STRONG"

        elif final_score >= 55:

            rating = "MODERATE"

        else:

            rating = "BULLISH"

        # ====================================================
        # CLOUD DISTANCE
        # ====================================================

        cloud_distance = np.nan

        if r5["cloud_top"] != 0:

            cloud_distance = (

                (
                    r5["close"]
                    -
                    r5["cloud_top"]
                )

                /

                r5["cloud_top"]

            ) * 100

        # ====================================================
        # RESULT
        # ====================================================

        return {

            "Stock": symbol,

            "Final Bullish Score":
                round(final_score, 2),

            "Rating":
                rating,

            "MACD Signal":
                macd_status,

            "MACD Cross Time":
                format_time(
                    r5["macd_cross_time"]
                ),

            "MACD Cross Age":
                r5["macd_cross_age"],

            "Price":
                round(
                    r5["close"],
                    2
                ),

            "5M Score":
                r5["score"],

            "15M Score":
                r15["score"],

            "1H Score":
                r1h["score"],

            "5M Volume Ratio":
                round(
                    r5["volume_ratio"],
                    2
                )
                if pd.notna(
                    r5["volume_ratio"]
                )
                else np.nan,

            "15M Volume Ratio":
                round(
                    r15["volume_ratio"],
                    2
                )
                if pd.notna(
                    r15["volume_ratio"]
                )
                else np.nan,

            "1H Volume Ratio":
                round(
                    r1h["volume_ratio"],
                    2
                )
                if pd.notna(
                    r1h["volume_ratio"]
                )
                else np.nan,

            "Average Volume Ratio":
                round(
                    avg_volume_ratio,
                    2
                )
                if pd.notna(
                    avg_volume_ratio
                )
                else np.nan,

            "Volume Bonus":
                volume_bonus,

            "MACD Bonus":
                macd_bonus,

            "MACD":
                round(
                    r5["macd"],
                    4
                ),

            "MACD Signal Value":
                round(
                    r5["macd_signal_value"],
                    4
                ),

            "MACD Histogram":
                round(
                    r5["macd_histogram"],
                    4
                ),

            "5M Tenkan":
                round(
                    r5["tenkan"],
                    2
                ),

            "5M Kijun":
                round(
                    r5["kijun"],
                    2
                ),

            "5M Cloud Top":
                round(
                    r5["cloud_top"],
                    2
                ),

            "5M Cloud Distance %":
                round(
                    cloud_distance,
                    2
                )
                if pd.notna(
                    cloud_distance
                )
                else np.nan,

            "15M Tenkan":
                round(
                    r15["tenkan"],
                    2
                ),

            "15M Kijun":
                round(
                    r15["kijun"],
                    2
                ),

            "1H Tenkan":
                round(
                    r1h["tenkan"],
                    2
                ),

            "1H Kijun":
                round(
                    r1h["kijun"],
                    2
                ),

            "5M Ichimoku Cross Time":
                format_time(
                    r5["cross_time"]
                ),

            "5M Ichimoku Cross Age":
                r5["cross_age"]
        }

    except Exception:

        return None


# ============================================================
# CREATE EXCEL
# ============================================================

def create_excel(result_df):

    output_file = (
        "NIFTY200_Ichimoku_Volume_MACD_Bullish.xlsx"
    )

    # --------------------------------------------------------
    # WRITE DATA
    # --------------------------------------------------------

    with pd.ExcelWriter(
        output_file,
        engine="openpyxl"
    ) as writer:

        result_df.to_excel(
            writer,
            sheet_name="Bullish Stocks",
            index=False
        )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    wb = load_workbook(
        output_file
    )

    ws = wb[
        "Bullish Stocks"
    ]

    # --------------------------------------------------------
    # FREEZE
    # --------------------------------------------------------

    ws.freeze_panes = "A2"

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    if ws.max_column >= 1:

        ws.auto_filter.ref = (
            ws.dimensions
        )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    for cell in ws[1]:

        cell.font = Font(
            bold=True
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )

    # --------------------------------------------------------
    # STOCK
    # --------------------------------------------------------

    for cell in ws["B"]:

        if cell.row > 1:

            cell.font = Font(
                bold=True
            )

    # --------------------------------------------------------
    # HEADER MAP
    # --------------------------------------------------------

    header_map = {}

    for cell in ws[1]:

        header_map[
            cell.value
        ] = cell.column

    # --------------------------------------------------------
    # DECIMAL COLUMNS
    # --------------------------------------------------------

    decimal_columns = [

        "Final Bullish Score",

        "Price",

        "5M Volume Ratio",

        "15M Volume Ratio",

        "1H Volume Ratio",

        "Average Volume Ratio",

        "MACD",

        "MACD Signal Value",

        "MACD Histogram",

        "5M Tenkan",

        "5M Kijun",

        "5M Cloud Top",

        "5M Cloud Distance %",

        "15M Tenkan",

        "15M Kijun",

        "1H Tenkan",

        "1H Kijun"
    ]

    for name in decimal_columns:

        if name not in header_map:

            continue

        col_num = header_map[name]

        for row in range(
            2,
            ws.max_row + 1
        ):

            ws.cell(
                row=row,
                column=col_num
            ).number_format = "0.00"

    # --------------------------------------------------------
    # SCORE COLOR SCALE
    # --------------------------------------------------------

    if (
        "Final Bullish Score"
        in header_map
    ):

        col_num = header_map[
            "Final Bullish Score"
        ]

        col_letter = (
            get_column_letter(
                col_num
            )
        )

        if ws.max_row >= 2:

            ws.conditional_formatting.add(

                f"{col_letter}2:"
                f"{col_letter}{ws.max_row}",

                ColorScaleRule(

                    start_type="min",
                    start_color="F8696B",

                    mid_type="percentile",
                    mid_value=50,
                    mid_color="FFEB84",

                    end_type="max",
                    end_color="63BE7B"
                )
            )

    # --------------------------------------------------------
    # MACD SIGNAL FONT
    # --------------------------------------------------------

    if "MACD Signal" in header_map:

        col_num = header_map[
            "MACD Signal"
        ]

        for row in range(
            2,
            ws.max_row + 1
        ):

            cell = ws.cell(
                row=row,
                column=col_num
            )

            value = str(
                cell.value
            ).upper()

            if value == "FRESH BUY":

                cell.font = Font(
                    bold=True,
                    color="008000"
                )

            elif value == "FRESH SELL":

                cell.font = Font(
                    bold=True,
                    color="FF0000"
                )

    # --------------------------------------------------------
    # AUTO WIDTH
    # --------------------------------------------------------

    for column_cells in ws.columns:

        max_length = 0

        column_letter = (
            get_column_letter(
                column_cells[0].column
            )
        )

        for cell in column_cells:

            try:

                value_length = len(
                    str(cell.value)
                )

                max_length = max(
                    max_length,
                    value_length
                )

            except Exception:

                pass

        width = min(
            max(
                max_length + 2,
                10
            ),
            28
        )

        ws.column_dimensions[
            column_letter
        ].width = width

    ws.row_dimensions[1].height = 25

    wb.save(
        output_file
    )

    return output_file


# ============================================================
# MAIN SCAN
# ============================================================

if scan_button:

    st.session_state.scan_error = None

    progress_bar = st.progress(
        0
    )

    status_text = st.empty()

    try:

        # ====================================================
        # STEP 1
        # ====================================================

        status_text.info(
            "Step 1/4 — Downloading NIFTY 200 list..."
        )

        symbols = get_nifty200()

        progress_bar.progress(
            10
        )

        tickers = [
            symbol + ".NS"
            for symbol in symbols
        ]

        # ====================================================
        # STEP 2
        # ====================================================

        status_text.info(
            "Step 2/4 — Downloading 5M, 15M and 1H data..."
        )

        download_start = time.time()

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            f5 = executor.submit(
                download_data,
                tickers,
                "5m",
                PERIOD_5M
            )

            f15 = executor.submit(
                download_data,
                tickers,
                "15m",
                PERIOD_15M
            )

            f1h = executor.submit(
                download_data,
                tickers,
                "60m",
                PERIOD_1H
            )

            data_5m = f5.result()

            progress_bar.progress(
                25
            )

            data_15m = f15.result()

            progress_bar.progress(
                40
            )

            data_1h = f1h.result()

        download_seconds = (
            time.time()
            -
            download_start
        )

        # ====================================================
        # STEP 3
        # ====================================================

        status_text.info(
            "Step 3/4 — Analysing NIFTY 200..."
        )

        results = []

        total = len(symbols)

        completed = 0

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            futures = {

                executor.submit(
                    analyze_stock,

                    symbol,

                    data_5m,

                    data_15m,

                    data_1h

                ): symbol

                for symbol in symbols
            }

            for future in as_completed(
                futures
            ):

                completed += 1

                try:

                    result = future.result()

                    if result is not None:

                        results.append(
                            result
                        )

                except Exception:

                    pass

                scan_progress = (

                    40

                    +

                    int(
                        50
                        *
                        completed
                        /
                        total
                    )
                )

                progress_bar.progress(
                    min(
                        scan_progress,
                        90
                    )
                )

                status_text.info(
                    f"Step 3/4 — Analysing "
                    f"{completed}/{total} stocks | "
                    f"Bullish signals: "
                    f"{len(results)}"
                )

        # ====================================================
        # STEP 4
        # ====================================================

        if not results:

            raise Exception(
                "No bullish stocks matched "
                "the current conditions."
            )

        result_df = pd.DataFrame(
            results
        )

        # ----------------------------------------------------
        # SORT
        # ----------------------------------------------------

        result_df = (
            result_df
            .sort_values(
                by=[
                    "Final Bullish Score",
                    "1H Score",
                    "15M Score",
                    "5M Score"
                ],
                ascending=[
                    False,
                    False,
                    False,
                    False
                ]
            )
            .reset_index(
                drop=True
            )
        )

        # ----------------------------------------------------
        # RANK
        # ----------------------------------------------------

        result_df.insert(
            0,
            "Rank",
            np.arange(
                1,
                len(result_df) + 1
            )
        )

        # ----------------------------------------------------
        # EXCEL
        # ----------------------------------------------------

        status_text.info(
            "Step 4/4 — Creating Excel output..."
        )

        excel_file = create_excel(
            result_df
        )

        progress_bar.progress(
            100
        )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        st.session_state.scan_results = (
            result_df
        )

        st.session_state.last_scan_time = (
            pd.Timestamp.now(
                tz=IST
            ).strftime(
                "%d-%b-%Y %H:%M:%S"
            )
        )

        status_text.success(
            "Scan completed successfully."
        )

        st.session_state.excel_file = (
            excel_file
        )

        # ----------------------------------------------------
        # DOWNLOAD DATA IN MEMORY
        # ----------------------------------------------------

        with open(
            excel_file,
            "rb"
        ) as f:

            excel_bytes = f.read()

        st.session_state.excel_bytes = (
            excel_bytes
        )

        st.session_state.scan_error = None

    except Exception as e:

        st.session_state.scan_error = str(
            e
        )

        progress_bar.empty()

        status_text.empty()


# ============================================================
# ERROR
# ============================================================

if st.session_state.scan_error:

    st.error(
        "Scanner error: "
        +
        st.session_state.scan_error
    )


# ============================================================
# DISPLAY RESULTS
# ============================================================

if (
    st.session_state.scan_results
    is not None
):

    result_df = (
        st.session_state.scan_results
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    st.markdown(
        "### 📊 Scan Summary"
    )

    fresh_buy_count = (

        result_df[
            "MACD Signal"
        ]
        .eq("FRESH BUY")
        .sum()
    )

    fresh_sell_count = (

        result_df[
            "MACD Signal"
        ]
        .eq("FRESH SELL")
        .sum()
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.metric(
            "NIFTY 200 Scanned",
            200
        )

    with c2:

        st.metric(
            "Bullish Stocks",
            len(result_df)
        )

    with c3:

        st.metric(
            "Fresh MACD BUY",
            int(fresh_buy_count)
        )

    with c4:

        st.metric(
            "Fresh MACD SELL",
            int(fresh_sell_count)
        )

    if st.session_state.last_scan_time:

        st.caption(
            "Last scan: "
            +
            st.session_state.last_scan_time
            +
            " IST"
        )

    # ========================================================
    # TOP RESULT
    # ========================================================

    if not result_df.empty:

        top_stock = result_df.iloc[0]

        st.success(
            f"Top Bullish Stock: "
            f"{top_stock['Stock']} | "
            f"Score: "
            f"{top_stock['Final Bullish Score']}"
        )

    # ========================================================
    # MACD FILTER
    # ========================================================

    st.markdown(
        "### 🔎 Results"
    )

    filter_col1, filter_col2 = st.columns(
        [1, 3]
    )

    with filter_col1:

        macd_filter = st.selectbox(
            "MACD Signal",
            [
                "ALL",
                "FRESH BUY",
                "FRESH SELL",
                "NONE"
            ]
        )

    with filter_col2:

        min_score_filter = st.slider(
            "Minimum Bullish Score",
            min_value=0,
            max_value=100,
            value=MIN_BULLISH_SCORE,
            step=1
        )

    display_df = result_df.copy()

    if macd_filter != "ALL":

        display_df = display_df[
            display_df[
                "MACD Signal"
            ]
            ==
            macd_filter
        ]

    display_df = display_df[
        display_df[
            "Final Bullish Score"
        ]
        >=
        min_score_filter
    ]

    # ========================================================
    # TABLE
    # ========================================================

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=650
    )

    # ========================================================
    # EXCEL DOWNLOAD
    # ========================================================

    st.markdown(
        "### 📥 Download"
    )

    if (
        "excel_bytes"
        in st.session_state
    ):

        st.download_button(

            label="⬇️ Download Exact Excel Output",

            data=st.session_state.excel_bytes,

            file_name=(
                "NIFTY200_Ichimoku_"
                "Volume_MACD_Bullish.xlsx"
            ),

            mime=(
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),

            use_container_width=True
        )


# ============================================================
# INFORMATION
# ============================================================

with st.expander(
    "ℹ️ Scanner Logic"
):

    st.markdown(
        """
### Timeframes

- **5M:** Intraday momentum + fresh MACD crossover
- **15M:** Ichimoku confirmation
- **1H:** Major trend confirmation

### Required bullish structure

**1H**
- Close > Tenkan
- Tenkan > Kijun

**15M**
- Close > Tenkan
- Tenkan > Kijun

**5M**
- Close > Tenkan

### Weighted score

- 1H = **45%**
- 15M = **35%**
- 5M = **20%**

### Fresh MACD

A MACD crossover within the latest **3 completed 5-minute candles** is treated as fresh.

- Fresh BUY gets additional bullish scoring.
- Fresh SELL is displayed but does not receive a bullish bonus.

### Volume

Volume is compared with the 20-period average.

### Excel

The downloaded Excel file contains:

- Rank
- Stock
- Final Bullish Score
- Rating
- MACD Signal
- MACD Cross Time
- MACD Cross Age
- Price
- 5M / 15M / 1H Scores
- Volume Ratios
- MACD values
- Ichimoku values
- Ichimoku cross time and age

The Excel sheet is named **Bullish Stocks**, with filters and frozen headers.
        """
    )
