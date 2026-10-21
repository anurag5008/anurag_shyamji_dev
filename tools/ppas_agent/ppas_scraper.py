import time
import re
import requests
import pandas as pd

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# ============================================================
# PPAS CONFIGURATION
# ============================================================

LOGIN_URL = "https://ppas.pdsodisha.gov.in"
DATA_URL = "https://ppas.pdsodisha.gov.in/viewTPDetailsByMiller"


# ============================================================
# MILLER CONFIGURATION
# ============================================================

MILLER_ID = "12358"


# ============================================================
# OTHER FILTERS
# ============================================================

# 0 = all PACS
PACS_CODE = "0"

# 0 = all PPC
PPC_ID = "0"

# Blank = all vehicles
VEHICLE_NO = ""


# ============================================================
# LOGIN SETTINGS
# ============================================================

LOGIN_TIMEOUT = 300


def _normalize_season_key(season):
	text = re.sub(r"\s+", "", (season or "").strip().lower())
	return text


def _resolve_season_configuration(available_seasons, season, configuration_id=None):
	if configuration_id:
		return str(configuration_id).strip()

	if not season:
		raise ValueError("Season is required.")

	if season in available_seasons:
		return available_seasons[season]

	normalized = _normalize_season_key(season)
	for season_name, config_id in available_seasons.items():
		if _normalize_season_key(season_name) == normalized:
			return config_id

	available = ", ".join(available_seasons.keys())
	raise ValueError(
		f"Season '{season}' was not found in PPAS. Available seasons: {available}"
	)


def _cookies_from_driver(driver):
	cookies = {}
	for cookie in driver.get_cookies():
		cookies[cookie["name"]] = cookie["value"]
	return cookies


def refresh_session_cookies(session):
	"""Refresh HTTP cookies from the live Chrome session before POSTing."""
	if not session:
		return

	driver = session.get("driver")
	if not driver:
		return

	try:
		session["cookies"] = _cookies_from_driver(driver)
	except Exception as exc:
		print("Cookie refresh warning:", exc)


def read_miller_id_from_page(driver):
	"""Read millerId for the logged-in PPAS user from the Transit Pass page."""
	driver.get(DATA_URL)
	time.sleep(2)

	page_source = driver.page_source or ""
	soup = BeautifulSoup(page_source, "html.parser")

	for selector in (
		{"id": "millerId"},
		{"name": "millerId"},
	):
		inp = soup.find("input", selector)
		if inp and (inp.get("value") or "").strip():
			return inp.get("value").strip()

	match = re.search(
		r"var\s+millerid\s*=\s*['\"](\d+)['\"]",
		page_source,
		flags=re.IGNORECASE,
	)
	if match:
		return match.group(1).strip()

	match = re.search(
		r'name=["\']millerId["\'][^>]*value=["\'](\d+)["\']',
		page_source,
		flags=re.IGNORECASE,
	)
	if match:
		return match.group(1).strip()

	return ""


def get_session_miller_id(session):
	miller_id = (session or {}).get("miller_id") or ""
	if miller_id:
		return miller_id

	driver = (session or {}).get("driver")
	if driver:
		miller_id = read_miller_id_from_page(driver)
		if miller_id:
			session["miller_id"] = miller_id
			return miller_id

	return MILLER_ID


# ============================================================
# DYNAMIC SEASON DISCOVERY
# ============================================================

def discover_seasons(driver):
    """
    Read available PPAS seasons and their configuration IDs
    from the authenticated Transit Pass page.

    Returns:
        dict
        Example:
        {
            "Kharif(2025)": "142",
            "Rabi(2025)": "143",
            "Kharif(2026)": "156"
        }
    """

    print("\n")
    print("=" * 70)
    print("DISCOVERING PPAS SEASONS")
    print("=" * 70)

    driver.get(DATA_URL)
    time.sleep(2)

    soup = BeautifulSoup(
        driver.page_source,
        "html.parser"
    )

    discovered = {}

    # --------------------------------------------------------
    # PRIMARY METHOD: READ <option> ELEMENTS
    # --------------------------------------------------------

    for option in soup.find_all("option"):

        value = (
            option.get("value") or ""
        ).strip()

        text = option.get_text(
            " ",
            strip=True
        )

        if not value or not text:
            continue

        match = re.search(
            r"\b(Kharif|Rabi)\s*\(\s*(20\d{2})\s*\)",
            text,
            flags=re.IGNORECASE
        )

        if match:

            season_type = (
                match.group(1).capitalize()
            )

            year = match.group(2)

            season_name = (
                f"{season_type}({year})"
            )

            discovered[
                season_name
            ] = value


    # --------------------------------------------------------
    # FALLBACK METHOD
    # --------------------------------------------------------

    if not discovered:

        html = driver.page_source

        pattern = re.compile(
            r"value\s*=\s*[\"']([^\"']+)[\"']"
            r"[^>]*>\s*"
            r"(Kharif|Rabi)"
            r"\s*\(\s*(20\d{2})\s*\)",
            flags=re.IGNORECASE
        )

        for match in pattern.finditer(html):

            value = match.group(1).strip()

            season_type = (
                match.group(2).capitalize()
            )

            year = match.group(3)

            season_name = (
                f"{season_type}({year})"
            )

            if value:

                discovered[
                    season_name
                ] = value


    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not discovered:

        raise Exception(
            "Could not dynamically discover PPAS "
            "seasons/configuration IDs from the "
            "logged-in Transit Pass page."
        )


    print("\nAvailable seasons discovered from PPAS:")

    for season_name, configuration_id in discovered.items():

        print(
            f"  {season_name} -> {configuration_id}"
        )


    return discovered


# ============================================================
# START PPAS SESSION
# ============================================================

def start_ppas_session():
    """
    Start Chrome, open PPAS login page and wait for the user
    to complete username/password/CAPTCHA login.

    Chrome remains open after this function returns so the same
    authenticated browser session can be used for extraction.

    Returns:
        dict containing:
            driver
            cookies
            available_seasons
    """

    print("\n")
    print("=" * 70)
    print("STARTING PPAS SESSION")
    print("=" * 70)


    options = Options()

    options.add_argument(
        "--start-maximized"
    )


    # close_fds: on Windows chromedriver would otherwise inherit the agent's
    # port 8765 and keep it blocked after the agent exits.
    driver = webdriver.Chrome(
        options=options,
        service=Service(popen_kw={"close_fds": True})
    )


    try:

        # ----------------------------------------------------
        # OPEN LOGIN PAGE
        # ----------------------------------------------------

        print(
            "\nOpening PPAS login page..."
        )

        driver.get(
            LOGIN_URL
        )


        print("\n")
        print("=" * 70)
        print("MANUAL PPAS LOGIN REQUIRED")
        print("=" * 70)

        print("""
Chrome has been opened.

Please do the following:

1. Enter your PPAS username.
2. Enter your PPAS password.
3. Solve the CAPTCHA.
4. Click SIGN IN.

IMPORTANT:
You do NOT need to return to VS Code.

After successful login, the program will automatically
detect the login and continue.
        """)


        # ----------------------------------------------------
        # AUTOMATIC LOGIN DETECTION
        # ----------------------------------------------------

        print(
            "\nWaiting for successful PPAS login..."
        )


        login_detected = False

        start_time = time.time()


        while (
            time.time() - start_time
            < LOGIN_TIMEOUT
        ):

            try:

                current_url = (
                    driver.current_url
                )

                page_source = (
                    driver.page_source
                )


                # URL changed from login page
                url_changed = (
                    current_url.rstrip("/")
                    != LOGIN_URL.rstrip("/")
                )


                # Common logged-in indicators
                logged_in_indicator = (
                    "Logout" in page_source
                    or "Dashboard" in page_source
                    or "Transit Pass" in page_source
                    or "viewTPDetailsByMiller" in page_source
                )


                if (
                    url_changed
                    or logged_in_indicator
                ):

                    login_detected = True

                    print("\n")
                    print("=" * 70)
                    print("PPAS LOGIN DETECTED")
                    print("=" * 70)

                    print(
                        "Current URL:",
                        current_url
                    )

                    break


            except Exception as e:

                print(
                    "Login detection warning:",
                    e
                )


            time.sleep(2)


        # ----------------------------------------------------
        # LOGIN FAILED / TIMEOUT
        # ----------------------------------------------------

        if not login_detected:

            raise Exception(
                "PPAS login was not detected within "
                f"{LOGIN_TIMEOUT} seconds."
            )


        print(
            "\nLogin successful!"
        )


        # ----------------------------------------------------
        # DISCOVER SEASONS
        # ----------------------------------------------------

        available_seasons = (
            discover_seasons(driver)
        )

        miller_id = read_miller_id_from_page(driver)
        if not miller_id:
            miller_id = MILLER_ID
            print(
                "\nWARNING: Could not read millerId from PPAS page. "
                f"Using fallback MILLER_ID={MILLER_ID}"
            )
        else:
            print("\nMiller ID from PPAS session:", miller_id)


        # ----------------------------------------------------
        # GET BROWSER COOKIES
        # ----------------------------------------------------

        print("\n")
        print("=" * 70)
        print("GETTING BROWSER COOKIES")
        print("=" * 70)


        selenium_cookies = (
            driver.get_cookies()
        )


        print(
            "Cookies obtained:",
            len(selenium_cookies)
        )


        if not selenium_cookies:

            raise Exception(
                "No cookies were obtained from PPAS."
            )


        cookies = {}


        for cookie in selenium_cookies:

            cookies[
                cookie["name"]
            ] = cookie["value"]


        print("\nCookie names:")

        for cookie_name in cookies:

            print(
                "  ",
                cookie_name
            )


        # ----------------------------------------------------
        # RETURN SESSION
        # ----------------------------------------------------

        return {

            "driver": driver,

            "cookies": cookies,

            "available_seasons":
                available_seasons,

            "miller_id": miller_id,

        }


    except Exception:

        # If session creation fails, do not leave Chrome open.

        try:

            driver.quit()

        except Exception:

            pass

        raise


# ============================================================
# GET AVAILABLE SEASONS
# ============================================================

def get_available_seasons(session):
    """
    Return seasons already discovered during login.

    If they are not available, discover them again using the
    existing browser session.
    """

    if not session:

        raise Exception(
            "PPAS session is not available."
        )


    available_seasons = (
        session.get(
            "available_seasons"
        )
    )


    if not available_seasons:

        driver = session.get(
            "driver"
        )

        available_seasons = (
            discover_seasons(driver)
        )

        session[
            "available_seasons"
        ] = available_seasons


    return available_seasons


# ============================================================
# EXTRACT DATA FROM EXISTING SESSION
# ============================================================

def extract_ppas_data_from_session(
    session,
    season,
    configuration_id=None,
):
    """
    Extract Transit Pass data using an already authenticated
    PPAS browser session.

    The browser is NOT closed here.

    Args:
        session: session returned by start_ppas_session()
        season: e.g. "Kharif(2025)"

    Returns:
        pandas.DataFrame
    """

    print("\n")
    print("=" * 70)
    print("PPAS TRANSIT PASS DATA EXTRACTION")
    print("=" * 70)


    if not session:

        raise Exception(
            "PPAS session is not available."
        )

    refresh_session_cookies(session)

    # --------------------------------------------------------
    # GET AVAILABLE SEASONS
    # --------------------------------------------------------

    available_seasons = (
        get_available_seasons(
            session
        )
    )

    state_configuration_id = _resolve_season_configuration(
        available_seasons,
        season,
        configuration_id=configuration_id,
    )

    miller_id = get_session_miller_id(session)

    print(
        "\nSelected Season:",
        season
    )

    print(
        "Configuration ID:",
        state_configuration_id
    )

    print(
        "Miller ID:",
        miller_id
    )


    # --------------------------------------------------------
    # GET COOKIES
    # --------------------------------------------------------

    cookies = session.get(
        "cookies"
    )


    if not cookies:

        raise Exception(
            "PPAS session cookies are not available."
        )


    # --------------------------------------------------------
    # CREATE REQUEST SESSION
    # --------------------------------------------------------

    http_session = (
        requests.Session()
    )


    for name, value in cookies.items():

        http_session.cookies.set(
            name,
            value
        )


    # --------------------------------------------------------
    # REQUEST HEADERS
    # --------------------------------------------------------

    request_headers = {

        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;"
            "v=b3;q=0.7"
        ),

        "Accept-Language": (
            "en-IN,en-GB;q=0.9,"
            "en-US;q=0.8,en;q=0.7"
        ),

        "Cache-Control":
            "max-age=0",

        "Content-Type":
            "application/x-www-form-urlencoded",

        "Origin":
            "https://ppas.pdsodisha.gov.in",

        "Referer":
            DATA_URL,

        "Upgrade-Insecure-Requests":
            "1",

        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        )
    }


    # --------------------------------------------------------
    # POST DATA
    # --------------------------------------------------------

    post_data = {

        "hdn_PageNo": "",

        "hdn_RecNo": "",

        "hdn_IsPaging": "",

        "data": "",

        "millerId":
            miller_id,

        # IMPORTANT:
        # PPAS field name is intentionally "intSate..."
        "intSateConfigurationId":
            state_configuration_id,

        "pacsCode":
            PACS_CODE,

        "ppcId":
            PPC_ID,

        "vehicleRegdNo":
            VEHICLE_NO
    }


    print("\n")
    print("=" * 70)
    print("SENDING PPAS DATA REQUEST")
    print("=" * 70)


    print(
        "\nRequest URL:",
        DATA_URL
    )

    print(
        "\nSeason:",
        season
    )

    print(
        "\nConfiguration ID:",
        state_configuration_id
    )


    print(
        "\nPOST parameters:"
    )


    for key, value in post_data.items():

        print(
            f"  {key} = {value}"
        )


    # --------------------------------------------------------
    # SEND REQUEST
    # --------------------------------------------------------

    print(
        "\nSending request..."
    )


    try:

        response = http_session.post(

            DATA_URL,

            headers=request_headers,

            data=post_data,

            timeout=60

        )


    except requests.RequestException as e:

        raise Exception(
            f"PPAS request failed: {e}"
        )


    # --------------------------------------------------------
    # RESPONSE INFORMATION
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("PPAS RESPONSE")
    print("=" * 70)


    print(
        "\nHTTP Status:",
        response.status_code
    )


    print(
        "Response length:",
        len(response.text)
    )


    print(
        "Content-Type:",
        response.headers.get(
            "Content-Type"
        )
    )


    if response.status_code != 200:

        raise Exception(
            "PPAS returned HTTP status "
            f"{response.status_code}"
        )


    # --------------------------------------------------------
    # SAVE RAW HTML - OPTIONAL DEBUG ONLY
    # --------------------------------------------------------

    # Raw HTML is useful for debugging, but it must NEVER
    # cause the actual PPAS extraction to fail.

    try:

        import os
        from datetime import datetime

        output_dir = os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)
            ),
            "PPAS_Output"
        )

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        safe_season = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            season
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        html_file = os.path.join(
            output_dir,
            f"ppas_response_{safe_season}_{timestamp}.html"
        )

        with open(
            html_file,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                response.text
            )

        print(
            "\nRaw HTML saved:",
            html_file
        )

    except Exception as e:

        # HTML is only a debug file.
        # Never fail the PPAS extraction because
        # this optional file could not be written.

        print(
            "\nWARNING: Could not save raw PPAS HTML:"
        )

        print(
            str(e)
        )

        print(
            "Continuing PPAS extraction..."
        )


    # --------------------------------------------------------
    # BASIC CHECK
    # --------------------------------------------------------

    if "Transit Pass" in response.text:

        print(
            "SUCCESS: Transit Pass text found."
        )

    else:

        print(
            "WARNING: Transit Pass text not found."
        )


    # --------------------------------------------------------
    # PARSE HTML
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("PARSING HTML")
    print("=" * 70)


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    tables = soup.find_all(
        "table"
    )


    print(
        "\nBeautifulSoup tables found:",
        len(tables)
    )


    if not tables:

        raise Exception(
            "No HTML tables found in PPAS response."
        )


    # --------------------------------------------------------
    # FIND TRANSIT PASS TABLE
    # --------------------------------------------------------

    target_table = None

    target_table_index = None


    for index, table in enumerate(
        tables
    ):

        table_text = table.get_text(
            " ",
            strip=True
        )


        if (
            "Transit Pass No." in table_text
            and
            "Vehicle No" in table_text
            and
            "Quantity" in table_text
        ):

            target_table = table

            target_table_index = index

            break


    if target_table is None:

        print("\n")
        print("=" * 70)
        print(
            "TRANSIT PASS TABLE NOT FOUND"
        )
        print("=" * 70)


        print(
            "\nAvailable tables:"
        )


        for index, table in enumerate(
            tables
        ):

            rows = table.find_all(
                "tr"
            )


            print(
                f"\nTABLE {index}"
            )


            print(
                "Rows:",
                len(rows)
            )


            if rows:

                first_row = (
                    rows[0].find_all(
                        ["th", "td"]
                    )
                )


                print(
                    "First row:",
                    [
                        cell.get_text(
                            " ",
                            strip=True
                        )
                        for cell in first_row
                    ]
                )


        raise Exception(
            "Transit Pass table could not be identified."
        )


    print(
        "\nTransit Pass table found!"
    )


    print(
        "Table number:",
        target_table_index
    )


    # --------------------------------------------------------
    # EXTRACT TABLE ROWS
    # --------------------------------------------------------

    rows = []


    for tr in target_table.find_all(
        "tr"
    ):

        cells = tr.find_all(
            ["th", "td"]
        )


        row = [

            cell.get_text(
                " ",
                strip=True
            )

            for cell in cells

        ]


        if row:

            rows.append(row)


    print(
        "\nTotal HTML rows:",
        len(rows)
    )


    if len(rows) < 2:

        raise Exception(
            "Transit Pass table does not contain "
            "enough rows."
        )


    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    columns = rows[0]

    data_rows = rows[1:]


    print(
        "\nColumns found:",
        len(columns)
    )


    print(
        "\nColumn names:"
    )


    for column in columns:

        print(
            "  ",
            column
        )


    # --------------------------------------------------------
    # HANDLE DIFFERENT COLUMN LENGTHS
    # --------------------------------------------------------

    cleaned_rows = []


    for row in data_rows:

        if len(row) < len(columns):

            row = (
                row
                + [""] * (
                    len(columns) - len(row)
                )
            )


        elif len(row) > len(columns):

            row = row[
                :len(columns)
            ]


        cleaned_rows.append(
            row
        )


    # --------------------------------------------------------
    # CREATE DATAFRAME
    # --------------------------------------------------------

    df = pd.DataFrame(

        cleaned_rows,

        columns=columns

    )


    print("\n")
    print("=" * 70)
    print("DATAFRAME CREATED")
    print("=" * 70)


    print(
        "\nRows:",
        len(df)
    )


    print(
        "Columns:",
        len(df.columns)
    )


    # --------------------------------------------------------
    # CLEAN DATA
    # --------------------------------------------------------

    df = df.dropna(
        how="all"
    )


    for column in df.columns:

        df[column] = (

            df[column]

            .astype(str)

            .str.strip()

        )


    # --------------------------------------------------------
    # NUMERIC COLUMNS
    # --------------------------------------------------------

    if "Sl#" in df.columns:

        df["Sl#"] = pd.to_numeric(
            df["Sl#"],
            errors="coerce"
        )


    if "Bag" in df.columns:

        df["Bag"] = pd.to_numeric(
            df["Bag"],
            errors="coerce"
        )


    if "Quantity" in df.columns:

        df["Quantity"] = pd.to_numeric(
            df["Quantity"],
            errors="coerce"
        )


    if "Delay(In Days)" in df.columns:

        df["Delay(In Days)"] = pd.to_numeric(
            df["Delay(In Days)"],
            errors="coerce"
        )


    # --------------------------------------------------------
    # ADD SEASON
    # --------------------------------------------------------

    df.insert(
        0,
        "Season",
        season
    )


    # --------------------------------------------------------
    # SHOW SAMPLE
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("FIRST 5 RECORDS")
    print("=" * 70)


    print(
        df.head(5).to_string(
            index=False
        )
    )


    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("EXTRACTION SUCCESSFUL")
    print("=" * 70)


    print(
        "\nSeason:",
        season
    )


    print(
        "Records:",
        len(df)
    )


    return df


# ============================================================
# CLOSE PPAS SESSION
# ============================================================

def close_ppas_session(session):
    """
    Close the Selenium browser session.
    """

    if not session:

        return


    driver = session.get(
        "driver"
    )


    if driver is None:

        return


    print("\n")
    print("=" * 70)
    print("CLOSING CHROME")
    print("=" * 70)


    try:

        driver.quit()

        print(
            "Chrome closed successfully."
        )


    except Exception as e:

        print(
            "Chrome close warning:",
            e
        )


# ============================================================
# BACKWARD-COMPATIBLE ONE-SHOT FUNCTION
# ============================================================

def extract_ppas_data(season):
    """
    Convenience function for standalone use.

    It opens Chrome, waits for manual login/CAPTCHA,
    discovers seasons dynamically, extracts the selected
    season and closes Chrome automatically.

    This keeps the original function interface working.
    """

    session = None


    try:

        session = (
            start_ppas_session()
        )


        return extract_ppas_data_from_session(

            session,

            season

        )


    finally:

        if session is not None:

            close_ppas_session(
                session
            )


# ============================================================
# TEST MODE
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 70)
    print("PPAS SCRAPER TEST MODE")
    print("=" * 70)


    print("""
This module now supports dynamic PPAS seasons.

The normal workflow is:

1. start_ppas_session()
2. get_available_seasons(session)
3. extract_ppas_data_from_session(session, season)
4. close_ppas_session(session)

For standalone testing, use:

extract_ppas_data("Kharif(2025)")
    """)

    print(
        "\nNo season/configuration IDs are hard-coded."
    )
