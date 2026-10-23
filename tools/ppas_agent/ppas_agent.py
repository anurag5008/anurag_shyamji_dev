from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from ppas_scraper import (
    start_ppas_session,
    get_available_seasons,
    extract_ppas_data_from_session,
    close_ppas_session
)

from portal_scraper import (
    start_portal_session,
    get_portal_session,
    close_portal_session
)

import os
import re
import threading
from datetime import datetime


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

# Keep keys in the order they were built: portal columns must stay in the
# website's order (Flask sorts them A-Z by default).
app.json.sort_keys = False
app.config["JSON_SORT_KEYS"] = False

CORS(app)


# ============================================================
# CONFIGURATION
# ============================================================

HOST = "127.0.0.1"
PORT = 8765

OUTPUT_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "PPAS_Output"
)

os.makedirs(
    OUTPUT_FOLDER,
    exist_ok=True
)


# ============================================================
# PPAS SESSION
# ============================================================

ppas_session = None


# ============================================================
# HELPER
# ============================================================

def safe_filename(text):

    return re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        text
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "ok",
        "service": "PPAS Agent",
        "message": "PPAS Agent is running",
        "portal": True,
        # Raise when the portal data format changes; the ERP refuses older agents.
        # 2: website column order kept, detail footer ("Total") sent apart.
        # 3: per-section document download (e.g. Transit Challan via the Action button).
        # 4: documents printed in a hidden Chrome; the user's page never changes tab.
        # 5: logout detected while saving documents.
        # 6: documents saved by clicking the row button (e.g. Transit Challan eye icon) like a user.
        # 7: pages with several tables or tabs (Table Match); table id/title/tab sent to the ERP.
        # 8: search filters on the page (e.g. KMS Year, Depot) sent to the ERP.
        # 9: row documents per tab (e.g. Lot Search "Print"), not for every table on the page.
        # 10: "Extract On Click": extra buttons/elements that start a read (e.g. DCRO Save, dvmillerhistory).
        # 11: Rows to Save limit (stop paging early) and /portal/finish (Close Session keeps rows read so far).
        # 12: several documents per row by column header (DCRO DC Transit Challan: Details, AC Note Doc); PDF or image.
        # 13: "Details > Print" (save the page's own print format); a document page must match its row.
        # 14: "> Print" alone: the agent picks the row button, then clicks Print (SCMS Transit Challan, DCRO View DC).
        # 15: WINGS: table found by a div id around it (table_ids); detail button clicked like a user
        #     when it runs a script (pop-up), found by its column header (TEC report "Delivered").
        # 16: Mill ID (dashboard / page), "Read On Page Open", one result per table of a page (WINGS e_tec).
        # 17: Mill ID read from the site's "Mill ID XPath" first (WINGS dashboard header).
        # 18: /portal/notify (message in Chrome after a save); Mill ID only from the XPath on the landing dashboard.
        # 19: only new or changed rows (known_rows fingerprints); row_sig and position sent per row.
        "portal_version": 20
    })


# ============================================================
# LOAD PPAS SEASONS
# ============================================================

@app.route("/seasons", methods=["POST"])
def seasons():

    global ppas_session

    try:

        print("\n")
        print("=" * 70)
        print("PPAS AGENT - LOAD SEASONS")
        print("=" * 70)


        # ------------------------------------------------------
        # IF SESSION ALREADY EXISTS
        # ------------------------------------------------------

        if ppas_session is not None:

            print(
                "\nExisting PPAS session found."
            )

            available_seasons = (
                get_available_seasons(
                    ppas_session
                )
            )

            return jsonify({

                "success": True,

                "message":
                    "Existing PPAS session is active.",

                "seasons": [

                    {
                        "name": season_name,

                        "configuration_id":
                            configuration_id

                    }

                    for season_name,
                    configuration_id
                    in available_seasons.items()

                ]

            })


        # ------------------------------------------------------
        # START NEW SESSION
        # ------------------------------------------------------

        print(
            "\nStarting new PPAS session..."
        )


        ppas_session = (
            start_ppas_session()
        )


        # ------------------------------------------------------
        # DISCOVER SEASONS
        # ------------------------------------------------------

        available_seasons = (
            get_available_seasons(
                ppas_session
            )
        )


        print("\nAvailable seasons:")


        for season_name, configuration_id in (
            available_seasons.items()
        ):

            print(
                f"  {season_name} -> {configuration_id}"
            )


        # ------------------------------------------------------
        # RETURN TO FRAPPE
        # ------------------------------------------------------

        return jsonify({

            "success": True,

            "message":
                "PPAS login successful and seasons loaded.",

            "seasons": [

                {
                    "name": season_name,

                    "configuration_id":
                        configuration_id

                }

                for season_name,
                configuration_id
                in available_seasons.items()

            ]

        })


    except Exception as e:

        print("\n")
        print("=" * 70)
        print("PPAS SEASON LOADING FAILED")
        print("=" * 70)

        print(
            "Error:",
            str(e)
        )


        if ppas_session is not None:

            try:

                close_ppas_session(
                    ppas_session
                )

            except Exception:

                pass


            ppas_session = None


        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500


# ============================================================
# EXTRACT DATA
# ============================================================

@app.route("/extract", methods=["POST"])
def extract():

    global ppas_session

    try:

        data = request.get_json(
            silent=True
        )


        if not data:

            return jsonify({

                "success": False,

                "error":
                    "No JSON data received."

            }), 400


        season = data.get(
            "season"
        )


        if not season:

            season = data.get(
                "season_name"
            )


        if not season:

            return jsonify({

                "success": False,

                "error":
                    "Season is required.",
                "message":
                    "Season is required.",

            }), 400

        configuration_id = (
            data.get("configuration_id")
            or data.get("season_id")
        )


        print("\n")
        print("=" * 70)
        print("PPAS AGENT - EXTRACTION")
        print("=" * 70)


        print(
            "Selected Season:",
            season
        )


        # ------------------------------------------------------
        # CHECK SESSION
        # ------------------------------------------------------

        if ppas_session is None:

            return jsonify({

                "success": False,

                "error":
                    "No active PPAS session. "
                    "Please click 'Load PPAS Seasons' "
                    "and login first."

            }), 400


        # ------------------------------------------------------
        # EXTRACT
        # ------------------------------------------------------

        print(
            "\nExtracting data..."
        )


        df = extract_ppas_data_from_session(

            ppas_session,

            season,

            configuration_id=configuration_id,

        )


        if df is None:

            raise Exception(
                "PPAS scraper returned no data."
            )


        if df.empty:

            raise Exception(
                "PPAS extraction completed "
                "but no records were found."
            )


        # ------------------------------------------------------
        # CREATE EXCEL
        # ------------------------------------------------------

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )


        filename = (

            "PPAS_Transit_Pass_"

            + safe_filename(
                season
            )

            + "_"

            + timestamp

            + ".xlsx"

        )


        file_path = os.path.join(

            OUTPUT_FOLDER,

            filename

        )


        print(
            "\nCreating Excel..."
        )


        df.to_excel(

            file_path,

            index=False

        )


        if not os.path.exists(
            file_path
        ):

            raise Exception(
                "Excel file was not created."
            )


        # ------------------------------------------------------
        # IMPORTANT:
        # DO NOT CLOSE PPAS SESSION HERE
        # ------------------------------------------------------

        print(
            "\nPPAS session remains active."
        )

        print(
            "User can extract another season."
        )


        # ------------------------------------------------------
        # SUCCESS
        # ------------------------------------------------------

        print("\n")
        print("=" * 70)
        print("EXTRACTION COMPLETED")
        print("=" * 70)


        print(
            "Season:",
            season
        )


        print(
            "Records:",
            len(df)
        )


        print(
            "Excel:",
            file_path
        )


        return jsonify({

            "success": True,

            "message":
                "PPAS data extracted successfully.",

            "season":
                season,

            "records":
                len(df),

            "filename":
                filename,

            "file_path":
                file_path,

            "download_url":
                f"http://{HOST}:{PORT}/download/{filename}"

        })


    except Exception as e:

        print("\n")
        print("=" * 70)
        print("PPAS EXTRACTION FAILED")
        print("=" * 70)


        print(
            "Error:",
            str(e)
        )


        # ------------------------------------------------------
        # DO NOT AUTOMATICALLY CLOSE SESSION
        # ------------------------------------------------------

        error_text = str(e)

        return jsonify({

            "success": False,

            "error":
                error_text,
            "message":
                error_text,

        }), 500


# ============================================================
# CLOSE PPAS SESSION
# ============================================================

@app.route("/close", methods=["POST"])
def close():

    global ppas_session

    try:

        print("\n")
        print("=" * 70)
        print("PPAS AGENT - CLOSE SESSION")
        print("=" * 70)

        if ppas_session is not None:

            print(
                "\nClosing PPAS Chrome..."
            )

            try:
                close_ppas_session(
                    ppas_session
                )
            except Exception as e:
                print(
                    "Chrome close warning:",
                    str(e)
                )

            ppas_session = None

        print(
            "\nPPAS session closed."
        )

        # Return the response to Frappe first.
        response = jsonify({
            "success": True,
            "message": "PPAS session closed successfully.",
            "agent_shutdown": True
        })

        # Stop the Agent after Frappe receives the response.
        def shutdown_agent():
            import os
            import time

            time.sleep(0.5)
            os._exit(0)

        threading.Thread(
            target=shutdown_agent,
            daemon=True
        ).start()

        return response

    except Exception as e:

        print(
            "Error closing PPAS session:",
            str(e)
        )

        ppas_session = None

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# DOWNLOAD EXCEL
# ============================================================

@app.route(
    "/download/<filename>",
    methods=["GET"]
)
def download(filename):

    try:

        safe_name = os.path.basename(
            filename
        )


        file_path = os.path.join(

            OUTPUT_FOLDER,

            safe_name

        )


        if not os.path.exists(
            file_path
        ):

            return jsonify({

                "success": False,

                "error":
                    "File not found."

            }), 404


        return send_file(

            file_path,

            as_attachment=True,

            download_name=safe_name

        )


    except Exception as e:

        return jsonify({

            "success": False,

            "error":
                str(e)

        }), 500



# ============================================================
# PORTAL EXTRACTION (SCMS / DCRO / WINGS)
# Every call after /portal/start must send the token it returned.
# ============================================================

def _portal_token():

    return (
        request.headers.get("X-Portal-Token")
        or request.args.get("token")
        or (request.get_json(silent=True) or {}).get("token")
    )


def _portal_session_or_error():

    session = get_portal_session(
        _portal_token()
    )

    if session is None:

        return None, (jsonify({
            "success": False,
            "error": "No active portal session. Click Connect Session again."
        }), 404)

    return session, None


@app.route("/portal/start", methods=["POST"])
def portal_start():

    data = request.get_json(silent=True) or {}

    try:

        session = start_portal_session(
            data,
            os.path.dirname(os.path.abspath(__file__))
        )

        return jsonify({
            "success": True,
            "token": session.token,
            **session.status()
        })

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/portal/status", methods=["GET"])
def portal_status():

    session, error = _portal_session_or_error()

    if error:
        return error

    return jsonify({
        "success": True,
        **session.status()
    })


@app.route("/portal/extract_now", methods=["POST"])
def portal_extract_now():

    session, error = _portal_session_or_error()

    if error:
        return error

    session.request_extract()

    return jsonify({
        "success": True
    })


@app.route("/portal/settings", methods=["POST"])
def portal_settings():
    """ERP form changed "Rows to Save" while the session is open."""

    session, error = _portal_session_or_error()

    if error:
        return error

    session.set_row_limit((request.get_json(silent=True) or {}).get("row_limit"))

    return jsonify({
        "success": True
    })


@app.route("/portal/finish", methods=["POST"])
def portal_finish():
    """Close Session: stop the read in progress and keep the rows read so far."""

    session, error = _portal_session_or_error()

    if error:
        return error

    session.request_finish()

    return jsonify({
        "success": True
    })


@app.route("/portal/notify", methods=["POST"])
def portal_notify():
    """Show a short message in the portal's Chrome window (e.g. "'TEC Report' saved in ERP")."""

    session, error = _portal_session_or_error()

    if error:
        return error

    body = request.get_json(silent=True) or {}
    session.notify(str(body.get("message") or "")[:300], str(body.get("color") or "green"))

    return jsonify({
        "success": True
    })


@app.route("/portal/result", methods=["GET"])
def portal_result():

    session, error = _portal_session_or_error()

    if error:
        return error

    result = session.get_result(
        request.args.get("result_id", ""),
        offset=max(int(request.args.get("offset", 0)), 0),
        limit=min(max(int(request.args.get("limit", 50)), 1), 100)
    )

    if result is None:

        return jsonify({
            "success": False,
            "error": "Result not found. Search again on the portal."
        }), 404

    return jsonify({
        "success": True,
        **result
    })


@app.route("/portal/receipt", methods=["GET"])
def portal_receipt():

    session, error = _portal_session_or_error()

    if error:
        return error

    doc = request.args.get("doc")
    receipt = session.get_receipt(
        request.args.get("result_id", ""),
        int(request.args.get("row", -1)),
        int(doc) if doc not in (None, "") else None
    )

    if receipt is None:

        return jsonify({
            "success": False,
            "error": "Receipt not found."
        }), 404

    return jsonify({
        "success": True,
        **receipt
    })


@app.route("/portal/close", methods=["POST"])
def portal_close():

    closed = close_portal_session(
        _portal_token()
    )

    return jsonify({
        "success": True,
        "closed": closed
    })


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    # Runs as a silent local background service when packaged
    # with PyInstaller --noconsole.
    app.run(
        host=HOST,
        port=PORT,
        debug=False
    )
