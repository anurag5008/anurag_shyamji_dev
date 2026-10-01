from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from ppas_scraper import (
    start_ppas_session,
    get_available_seasons,
    extract_ppas_data_from_session,
    close_ppas_session
)

import os
import re
import threading
from datetime import datetime


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

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
        "message": "PPAS Agent is running"
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
