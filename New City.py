import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from rapidfuzz import process
import re

# =========================================================
# CONFIG
# =========================================================

API_KEY = "4050a765b2d333f958c7017723bb54324a92b646"

IBAN_API_URL = "https://api.ibanapi.com/v1/validate/"

MAX_WORKERS = 20

# =========================================================
# STREAMLIT PAGE
# =========================================================

st.set_page_config(
    page_title="Global IBAN City Lookup",
    layout="wide"
)

st.title("🌍 Global IBAN → City Lookup Engine")

st.markdown("""
### Hybrid Engine

✅ IBANAPI  
✅ OpenIBAN fallback  
✅ BIC → CITY mapping  
✅ Country parsers  
✅ Fuzzy bank matching  
✅ IBANCalculator scraping  
✅ SWIFT web lookup  
✅ Cache  
✅ Multithreading  
""")

# =========================================================
# CACHE
# =========================================================

cache = {}

# =========================================================
# COUNTRY DEFAULT CITIES
# =========================================================

COUNTRY_DEFAULT_CITY = {

    "BE": "Brussels",
    "NL": "Amsterdam",
    "DK": "Copenhagen",
    "FI": "Helsinki",
    "NO": "Oslo",
    "SE": "Stockholm",
    "FR": "Paris",
    "GB": "London",
    "PL": "Warsaw",
    "AT": "Vienna",
    "CZ": "Prague",
    "HU": "Budapest",
    "RO": "Bucharest",
    "IT": "Rome",
    "ES": "Madrid"
}

# =========================================================
# BIC MAP
# =========================================================

BIC_CITY_MAP = {

    "KREDBE": "Brussels",
    "GEBABE": "Brussels",
    "BBRUBE": "Brussels",
    "GKCCBE": "Brussels",
    "BPOTBE": "Brussels",
    "NICABE": "Brussels",

    "INGBNL": "Amsterdam",
    "ABNANL": "Amsterdam",
    "RABONL": "Utrecht",

    "DEUTDE": "Frankfurt",
    "COBADE": "Frankfurt",
    "DRESDE": "Frankfurt",
    "HYVEDE": "Munich",
    "BELADE": "Berlin",

    "BNPAFR": "Paris",
    "AGRIFR": "Paris",

    "BARCGB": "London",
    "HSBCGB": "London",
    "LOYDGB": "London",
    "RBOSGB": "Edinburgh",

    "PKOPPL": "Warsaw",
    "INGBPL": "Katowice",
    "BREXPL": "Warsaw",

    "UNCRIT": "Milan",

    "HANDSE": "Stockholm",
    "DNBANOK": "Oslo",
    "DABADK": "Copenhagen",

    "UBSWCH": "Zurich",

    "BOFAUS": "Charlotte",
    "CITIUS": "New York",
    "CHASUS": "New York",

    "DBSSSG": "Singapore",
    "BOTKJP": "Tokyo",

    "ANZBAU": "Sydney"
}

# =========================================================
# BANK MAP
# =========================================================

BANK_CITY_MAP = {

    "KBC": "Brussels",
    "BNP": "Paris",
    "ING": "Amsterdam",
    "DEUTSCHE": "Frankfurt",
    "SPARKASSE": "Berlin",
    "AXA": "Brussels",
    "BELFIUS": "Brussels",
    "UNICREDIT": "Milan",
    "INTESA": "Milan",
    "SANTANDER": "Madrid",
    "BARCLAYS": "London",
    "COMMERZBANK": "Frankfurt",
    "RABOBANK": "Utrecht",
    "ABN AMRO": "Amsterdam",
    "NORDEA": "Stockholm",
    "DANSKE": "Copenhagen",
    "HSBC": "London",
    "LLOYDS": "London",
    "BANK OF AMERICA": "Charlotte",
    "UBS": "Zurich",
    "RAIFFEISEN": "Vienna",
    "CREDIT SUISSE": "Zurich",
    "MIZUHO": "Tokyo",
    "SEB": "Stockholm",
    "SWEDBANK": "Stockholm",
    "OTP": "Budapest",
    "CAIXABANK": "Barcelona",
    "INTESA SANPAOLO": "Milan",
    "MEDIOBANCA": "Milan",
    "BPOST": "Brussels",
    "JP MORGAN": "New York"
}

# =========================================================
# COUNTRY PARSERS
# =========================================================

def detect_polish_bank_city(iban):

    mappings = {

        "1010": "Warsaw",
        "1020": "Warsaw",
        "1050": "Katowice",
        "1090": "Warsaw",
        "1140": "Warsaw",
        "1240": "Warsaw"
    }

    return mappings.get(iban[4:8])

def detect_italian_bank_city(iban):

    mappings = {

        "03069": "Milan",
        "02008": "Milan",
        "05034": "Bologna",
        "01030": "Turin"
    }

    return mappings.get(iban[5:10])

def detect_spanish_bank_city(iban):

    mappings = {

        "2100": "Madrid",
        "0049": "Madrid",
        "1465": "Barcelona"
    }

    return mappings.get(iban[4:8])

def detect_french_bank_city(iban):

    mappings = {

        "30004": "Paris",
        "20041": "Paris"
    }

    return mappings.get(iban[4:9])

def detect_german_bank_city(iban):

    mappings = {

        "37040044": "Frankfurt",
        "10070000": "Berlin"
    }

    return mappings.get(iban[4:12])

def detect_uk_bank_city(iban):

    mappings = {

        "NWBK": "London",
        "BARC": "London",
        "LOYD": "London",
        "HSBC": "London"
    }

    return mappings.get(iban[4:8])

# =========================================================
# COUNTRY ROUTER
# =========================================================

def detect_country_city(iban):

    country = iban[:2]

    try:

        if country == "PL":
            return detect_polish_bank_city(iban)

        elif country == "IT":
            return detect_italian_bank_city(iban)

        elif country == "ES":
            return detect_spanish_bank_city(iban)

        elif country == "FR":
            return detect_french_bank_city(iban)

        elif country == "DE":
            return detect_german_bank_city(iban)

        elif country == "GB":
            return detect_uk_bank_city(iban)

        elif country == "DK":
            return "Copenhagen"

        elif country == "FI":
            return "Helsinki"

        elif country == "NO":
            return "Oslo"

        elif country == "SE":
            return "Stockholm"

    except:
        pass

    return None

# =========================================================
# BIC PARSER
# =========================================================

def detect_city_from_bic(bic):

    if not bic:
        return None

    return BIC_CITY_MAP.get(
        bic[:6].upper()
    )

# =========================================================
# FUZZY BANK MATCHING
# =========================================================

def advanced_bank_parser(bank_name):

    if not bank_name:
        return None

    try:

        match = process.extractOne(
            bank_name.upper(),
            BANK_CITY_MAP.keys()
        )

        if match and match[1] >= 70:

            return BANK_CITY_MAP.get(match[0])

    except:
        pass

    return None

# =========================================================
# IBANCALCULATOR SCRAPER
# =========================================================

def search_ibancalculator(iban):

    try:

        url = (
            "https://www.ibancalculator.com/"
            f"iban_validieren.html?iban={iban}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        text = soup.get_text(
            " ",
            strip=True
        )

        patterns = [

            r"City[:\s]+([A-Z][A-Za-z\s\-]+)",
            r"Ort[:\s]+([A-Z][A-Za-z\s\-]+)",
            r"Location[:\s]+([A-Z][A-Za-z\s\-]+)"
        ]

        for pattern in patterns:

            match = re.search(pattern, text)

            if match:

                city = (
                    match
                    .group(1)
                    .strip()
                )

                if len(city) < 40:

                    return city.title()

    except:
        pass

    return None

# =========================================================
# WEB LOOKUP
# =========================================================

def search_city_from_web(bic):

    if not bic:
        return None

    urls = [

        f"https://bank.codes/swift-code/{bic.lower()}/",
        f"https://www.theswiftcodes.com/{bic.lower()}/"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for url in urls:

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            text = soup.get_text(
                " ",
                strip=True
            )

            patterns = [

                r"City\s+([A-Z][A-Za-z\s\-]+)",
                r"Location\s+([A-Z][A-Za-z\s\-]+)",
                r"Branch\s+([A-Z][A-Za-z\s\-]+)"
            ]

            for pattern in patterns:

                match = re.search(pattern, text)

                if match:

                    city = (
                        match.group(1)
                        .strip()
                    )

                    if len(city) < 40:

                        return city.title()

        except:
            continue

    return None

# =========================================================
# MAIN FUNCTION
# =========================================================

def get_iban_data(iban):

    original_iban = str(iban)

    iban = (
        str(iban)
        .replace(" ", "")
        .strip()
        .upper()
    )

    iban = re.sub(
        r"[^A-Z0-9]",
        "",
        iban
    )

    # CACHE

    if iban in cache:
        return cache[iban]

    # VALIDATION

    if len(iban) < 15:

        result = {

            "IBAN": original_iban,
            "CITY": None,
            "BANK": None,
            "BIC": None,
            "ADDRESS": None,
            "RESULT": "INVALID_IBAN"
        }

        cache[iban] = result

        return result

    try:

        city = None
        bank_name = None
        bic = None
        address = None

        # =================================================
        # PRIMARY API
        # =================================================

        response = requests.get(

            IBAN_API_URL + iban,

            params={
                "api_key": API_KEY
            },

            headers={
                "Accept": "application/json"
            },

            timeout=20
        )

        # =================================================
        # OPENIBAN
        # =================================================

        if response.status_code != 200:

            fallback = requests.get(

                f"https://openiban.com/validate/{iban}",

                params={
                    "getBIC": "true",
                    "validateBankCode": "true"
                },

                timeout=15
            )

            data = fallback.json()

            bank_data = data.get(
                "bankData",
                {}
            )

            bank_name = bank_data.get("name")

            bic = bank_data.get("bic")

        else:

            data = response.json()

            bank = (
                data
                .get("data", {})
                .get("bank", {})
            )

            city = bank.get("city")

            bank_name = bank.get("bank_name")

            bic = bank.get("bic")

            address = bank.get("address")

        # =================================================
        # BIC → CITY
        # =================================================

        if not city:

            city = detect_city_from_bic(bic)

        # =================================================
        # COUNTRY PARSER
        # =================================================

        if not city:

            city = detect_country_city(iban)

        # =================================================
        # FUZZY BANK MATCH
        # =================================================

        if not city:

            city = advanced_bank_parser(bank_name)

        # =================================================
        # IBANCALCULATOR
        # =================================================

        if not city:

            city = search_ibancalculator(iban)

        # =================================================
        # COUNTRY DEFAULT
        # =================================================

        if not city:

            city = COUNTRY_DEFAULT_CITY.get(
                iban[:2]
            )

        # =================================================
        # SWIFT WEB LOOKUP
        # =================================================

        if not city:

            city = search_city_from_web(bic)

        # =================================================
        # FINAL RESULT
        # =================================================

        result_value = (

            city
            or address
            or bank_name
            or bic
            or "REVIEW"
        )

        result = {

            "IBAN": iban,
            "CITY": city,
            "BANK": bank_name,
            "BIC": bic,
            "ADDRESS": address,
            "RESULT": result_value
        }

        cache[iban] = result

        return result

    except Exception:

        result = {

            "IBAN": iban,
            "CITY": None,
            "BANK": None,
            "BIC": None,
            "ADDRESS": None,
            "RESULT": "ERROR"
        }

        cache[iban] = result

        return result

# =========================================================
# FILE UPLOAD
# =========================================================

uploaded_file = st.file_uploader(
    "Upload Excel file",
    type=["xlsx"]
)

# =========================================================
# MAIN APP
# =========================================================

if uploaded_file:

    try:

        df = pd.read_excel(
            uploaded_file,
            engine="openpyxl"
        )

        st.subheader("Preview")

        st.dataframe(df.head())

        suggested_columns = [

            col for col in df.columns

            if "account" in col.lower()
            or "iban" in col.lower()
        ]

        if suggested_columns:

            default_index = list(df.columns).index(
                suggested_columns[0]
            )

        else:

            default_index = 0

        iban_column = st.selectbox(

            "Select IBAN column",

            df.columns,

            index=default_index
        )

        st.success(
            f"Selected column: {iban_column}"
        )

        # =================================================
        # PROCESS
        # =================================================

        if st.button("Process IBANs"):

            clean_series = (

                df[iban_column]
                .dropna()
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.upper()
            )

            clean_series = clean_series[
                clean_series.str.len() >= 15
            ]

            unique_ibans = (
                clean_series
                .unique()
                .tolist()
            )

            st.info(
                f"Unique valid IBANs: {len(unique_ibans)}"
            )

            progress = st.progress(0)

            results = []

            with ThreadPoolExecutor(
                max_workers=MAX_WORKERS
            ) as executor:

                futures = [

                    executor.submit(
                        get_iban_data,
                        iban
                    )

                    for iban in unique_ibans
                ]

                for i, future in enumerate(futures):

                    results.append(
                        future.result()
                    )

                    progress.progress(
                        (i + 1) / len(futures)
                    )

            result_df = pd.DataFrame(results)

            df[iban_column] = (

                df[iban_column]
                .astype(str)
                .str.replace(" ", "", regex=False)
                .str.upper()
            )

            final_df = df.merge(

                result_df,

                left_on=iban_column,

                right_on="IBAN",

                how="left"
            )

            # =================================================
            # STATS
            # =================================================

            st.subheader("Statistics")

            total_rows = len(final_df)

            cities_found = (
                final_df["CITY"]
                .notna()
                .sum()
            )

            review = (
                final_df["RESULT"]
                .eq("REVIEW")
                .sum()
            )

            errors = (
                final_df["RESULT"]
                .eq("ERROR")
                .sum()
            )

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Rows", total_rows)

            col2.metric("Cities Found", cities_found)

            col3.metric("Review Needed", review)

            col4.metric("Errors", errors)

            # =================================================
            # RESULTS
            # =================================================

            st.subheader("Results")

            st.dataframe(final_df)

            # =================================================
            # EXPORT
            # =================================================

            output = BytesIO()

            with pd.ExcelWriter(
                output,
                engine="openpyxl"
            ) as writer:

                final_df.to_excel(
                    writer,
                    sheet_name="Results",
                    index=False
                )

            output.seek(0)

            st.download_button(

                label="⬇ Download Excel",

                data=output,

                file_name="iban_city_results.xlsx",

                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:

        st.error(str(e))