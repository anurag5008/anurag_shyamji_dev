const PPAS_AGENT = "http://127.0.0.1:8765";
const PPAS_PROTOCOL = "ppasagent://start";


// =========================================================
// HELPER: TEXT
// =========================================================

function text(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    return String(value).trim();
}


// =========================================================
// HELPER: NUMBER
// =========================================================

function number(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return 0;
    }

    const n = Number(
        String(value)
            .replace(/,/g, "")
            .trim()
    );

    return Number.isFinite(n) ? n : 0;
}


// =========================================================
// HELPER: GET VALUE
// =========================================================

function get_value(row, keys) {

    // Exact key first
    for (const key of keys) {

        if (
            Object.prototype.hasOwnProperty.call(
                row,
                key
            )
        ) {
            return row[key];
        }
    }


    // Normalized key fallback
    function normalize(key) {

        return String(key)
            .toLowerCase()
            .replace(/[^a-z0-9]/g, "");
    }


    const normalized_keys =
        keys.map(normalize);


    for (
        const actual_key of Object.keys(row)
    ) {

        const actual =
            normalize(actual_key);


        if (
            normalized_keys.includes(actual)
        ) {
            return row[actual_key];
        }
    }


    return null;
}


// =========================================================
// DATE + TIME SPLITTER
// =========================================================

function split_datetime(value) {

    if (
        value === null ||
        value === undefined ||
        String(value).trim() === ""
    ) {

        return {
            date: null,
            time: null
        };
    }


    const raw =
        String(value).trim();


    // PPAS FORMAT
    // 03-Mar-2026 09:40:27

    const match =
        raw.match(
            /^(\d{2})-([A-Za-z]{3})-(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?/
        );


    if (match) {

        const months = {

            Jan: "01",
            Feb: "02",
            Mar: "03",
            Apr: "04",
            May: "05",
            Jun: "06",
            Jul: "07",
            Aug: "08",
            Sep: "09",
            Oct: "10",
            Nov: "11",
            Dec: "12"

        };


        const month_name =
            match[2]
                .charAt(0)
                .toUpperCase() +
            match[2]
                .slice(1)
                .toLowerCase();


        const month =
            months[month_name];


        if (month) {

            return {

                date:
                    `${match[3]}-${month}-${match[1]}`,

                time:
                    `${match[4]}:${match[5]}:${match[6] || "00"}`
            };
        }
    }


    // ISO FORMAT

    const iso =
        raw.match(
            /^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/
        );


    if (iso) {

        return {

            date:
                `${iso[1]}-${iso[2]}-${iso[3]}`,

            time:
                `${iso[4]}:${iso[5]}:${iso[6] || "00"}`
        };
    }


    return {
        date: null,
        time: null
    };
}


// =========================================================
// PROGRESS DIALOG
// =========================================================

function create_progress_dialog() {

    const dialog =
        new frappe.ui.Dialog({

            title:
                "PPAS Extraction",

            fields: [

                {
                    fieldname:
                        "progress_html",

                    fieldtype:
                        "HTML"
                }

            ]
        });


    dialog.show();

    return dialog;
}


function update_progress(
    dialog,
    message,
    current,
    total
) {

    if (
        !dialog ||
        !dialog.fields_dict.progress_html
    ) {

        return;
    }


    const percent =
        total > 0
            ? Math.round(
                current /
                total *
                100
            )
            : 0;


    dialog
        .fields_dict.progress_html
        .$wrapper
        .html(`

            <div style="
                padding:10px 0 20px;
            ">

                <div style="
                    margin-bottom:14px;
                    font-size:14px;
                ">
                    ${message}
                </div>


                <div style="
                    width:100%;
                    height:14px;
                    background:#e9ecef;
                    border-radius:7px;
                    overflow:hidden;
                ">

                    <div style="
                        width:${percent}%;
                        height:100%;
                        background:#2490ef;
                        transition:width .15s;
                    ">
                    </div>

                </div>


                ${
                    total > 0
                        ? `
                            <div style="
                                text-align:center;
                                margin-top:10px;
                                font-size:13px;
                            ">

                                <b>
                                    ${current}
                                </b>

                                /

                                <b>
                                    ${total}
                                </b>

                                &nbsp;

                                (${percent}%)

                            </div>
                        `
                        : ""
                }

            </div>

        `);
}


function normalize_ppas_season_key(value) {
    return String(value || "")
        .trim()
        .replace(/\s+/g, "")
        .toLowerCase();
}


function store_ppas_season_catalog(frm, seasons) {
    const catalog = {
        by_key: {},
        names: [],
    };

    if (Array.isArray(seasons)) {
        for (const item of seasons) {
            if (typeof item === "string" && item.trim()) {
                const name = item.trim();
                const entry = { name };
                catalog.by_key[normalize_ppas_season_key(name)] = entry;
                catalog.names.push(name);
                continue;
            }

            if (!item || typeof item !== "object") {
                continue;
            }

            const name =
                item.name ||
                item.season ||
                item.label ||
                item.season_name;

            if (!name) {
                continue;
            }

            const entry = {
                name,
                configuration_id:
                    item.configuration_id ||
                    item.id ||
                    item.season_id ||
                    item.value,
            };

            catalog.by_key[normalize_ppas_season_key(name)] = entry;
            catalog.names.push(name);
        }
    } else if (seasons && typeof seasons === "object") {
        for (const [name, configuration_id] of Object.entries(seasons)) {
            const entry = {
                name,
                configuration_id,
            };
            catalog.by_key[normalize_ppas_season_key(name)] = entry;
            catalog.names.push(name);
        }
    }

    frm.__ppas_season_catalog = catalog;
    return catalog;
}


function resolve_ppas_season_choice(frm, season) {
    const catalog = frm.__ppas_season_catalog || { by_key: {} };
    const key = normalize_ppas_season_key(season);

    if (catalog.by_key[key]) {
        return catalog.by_key[key];
    }

    for (const entry of Object.values(catalog.by_key)) {
        if (entry.name === season) {
            return entry;
        }
    }

    return { name: season };
}


async function read_ppas_agent_error(response, fallback) {
    let detail = fallback;

    try {
        const payload = await response.json();
        detail =
            payload.error ||
            payload.message ||
            fallback;
    } catch (error) {
        // Keep fallback message.
    }

    return detail;
}


async function sync_ppas_season_catalog(frm) {
    const response = await fetch(`${PPAS_AGENT}/seasons`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(
            await read_ppas_agent_error(
                response,
                `PPAS Agent HTTP ${response.status}`
            )
        );
    }

    const result = await response.json();

    if (!result.success) {
        throw new Error(
            result.error ||
                result.message ||
                "Unable to refresh PPAS seasons."
        );
    }

    const catalog = store_ppas_season_catalog(frm, result.seasons || []);

    if (!catalog.names.length) {
        throw new Error("No PPAS seasons found.");
    }

    frm.set_df_property("season", "options", catalog.names.join("\n"));
    frm.refresh_field("season");

    return catalog;
}


function pick_ppas_row_array(payload) {
    if (!payload || typeof payload !== "object") {
        return [];
    }

    if (Array.isArray(payload.data)) {
        return payload.data;
    }

    if (Array.isArray(payload.rows)) {
        return payload.rows;
    }

    if (Array.isArray(payload.records)) {
        return payload.records;
    }

    return [];
}


function array_buffer_to_base64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunk_size = 0x8000;

    for (let i = 0; i < bytes.length; i += chunk_size) {
        binary += String.fromCharCode.apply(
            null,
            bytes.subarray(i, i + chunk_size)
        );
    }

    return btoa(binary);
}


async function fetch_ppas_json_rows(url) {
    try {
        const response = await fetch(url, { cache: "no-store" });

        if (!response.ok) {
            return [];
        }

        const payload = await response.json();
        let rows = pick_ppas_row_array(payload);

        if (!rows.length && Array.isArray(payload)) {
            rows = payload;
        }

        return rows;
    } catch (error) {
        return [];
    }
}


async function parse_ppas_excel_via_frappe(download_url) {
    const response = await fetch(download_url, { cache: "no-store" });

    if (!response.ok) {
        throw new Error(
            `PPAS Excel download failed (HTTP ${response.status})`
        );
    }

    const file_content = array_buffer_to_base64(
        await response.arrayBuffer()
    );

    const parsed = await frappe.call({
        method:
            "ivri_od.procurement.doctype.ppas_data_extraction.ppas_data_extraction.parse_ppas_excel_file",
        args: {
            file_content,
        },
        freeze: false,
    });

    return parsed.message || [];
}


async function resolve_ppas_extract_rows(result, season) {
    let rows = pick_ppas_row_array(result);

    if (rows.length) {
        return rows;
    }

    const filename =
        result.filename ||
        result.file_name ||
        result.excel_file ||
        "";

    const json_urls = [];

    if (filename) {
        json_urls.push(
            `${PPAS_AGENT}/records?filename=${encodeURIComponent(filename)}`
        );
        json_urls.push(
            `${PPAS_AGENT}/data?filename=${encodeURIComponent(filename)}`
        );
    }

    for (const url of json_urls) {
        rows = await fetch_ppas_json_rows(url);

        if (rows.length) {
            return rows;
        }
    }

    let download_url = result.download_url || "";

    if (!download_url && filename) {
        download_url = `${PPAS_AGENT}/download/${encodeURIComponent(filename)}`;
    }

    const record_count = Number(
        result.records || result.record_count || 0
    );

    if (download_url && (record_count > 0 || filename)) {
        rows = await parse_ppas_excel_via_frappe(download_url);

        if (rows.length) {
            return rows;
        }
    }

    if (!filename) {
        try {
            const response = await fetch(`${PPAS_AGENT}/extract`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    season,
                    include_data: true,
                    return_data: true,
                }),
                cache: "no-store",
            });

            if (response.ok) {
                rows = pick_ppas_row_array(await response.json());

                if (rows.length) {
                    return rows;
                }
            }
        } catch (error) {
            // No row payload available.
        }
    }

    if (record_count > 0) {
        throw new Error(
            `PPAS Agent reported ${record_count} records but no importable row data was returned.`
        );
    }

    return [];
}


// =========================================================
// CHECK IF AGENT IS RUNNING
// =========================================================

async function is_agent_running() {

    try {

        const response =
            await fetch(
                `${PPAS_AGENT}/health`,
                {
                    method: "GET",
                    cache: "no-store"
                }
            );


        return response.ok;

    }
    catch (error) {

        return false;
    }
}


// =========================================================
// LAUNCH AGENT THROUGH WINDOWS PROTOCOL
// =========================================================

function launch_agent_protocol() {

    return new Promise((resolve) => {

        try {

            const link =
                document.createElement("a");


            link.href =
                PPAS_PROTOCOL;


            link.style.display =
                "none";


            document.body.appendChild(
                link
            );


            link.click();


            setTimeout(
                () => {

                    try {
                        link.remove();
                    }
                    catch (e) {
                        // Ignore
                    }


                    resolve(true);

                },
                500
            );

        }
        catch (error) {

            console.error(
                "PPAS AGENT PROTOCOL ERROR",
                error
            );


            resolve(false);
        }
    });
}


// =========================================================
// WAIT FOR AGENT
// =========================================================

async function wait_for_agent(
    attempts = 20,
    delay_ms = 1000
) {

    for (
        let attempt = 1;
        attempt <= attempts;
        attempt++
    ) {

        if (
            await is_agent_running()
        ) {

            return true;
        }


        if (
            attempt < attempts
        ) {

            await new Promise(
                resolve =>
                    setTimeout(
                        resolve,
                        delay_ms
                    )
            );
        }
    }


    return false;
}


// =========================================================
// ENSURE AGENT IS AVAILABLE
// =========================================================

async function ensure_agent(dialog) {

    // -----------------------------------------------------
    // Agent already running
    // -----------------------------------------------------

    if (
        await is_agent_running()
    ) {

        update_progress(
            dialog,

            `
            <b>
                PPAS Agent is already running.
            </b>

            <br><br>

            Connecting to PPAS...
            `,

            0,
            0
        );


        return true;
    }


    // -----------------------------------------------------
    // Agent is not running
    // -----------------------------------------------------

    update_progress(
        dialog,

        `
        <b>
            Starting PPAS Agent...
        </b>

        <br><br>

        Windows may ask permission to open
        <b>PPAS Launcher</b>.

        <br><br>

        Please allow it if prompted.

        <br><br>

        Waiting for Agent...
        `,

        0,
        0
    );


    const started =
        await launch_agent_protocol();


    if (!started) {

        throw new Error(
            "Unable to start PPAS Agent from the browser."
        );
    }


    // Wait up to 20 seconds
    const ready =
        await wait_for_agent(
            20,
            1000
        );


    if (!ready) {

        throw new Error(
            "PPAS Agent is not running. Please make sure PPAS Agent is installed on this computer."
        );
    }


    update_progress(
        dialog,

        `
        <b style="color:green;">
            PPAS Agent started successfully.
        </b>

        <br><br>

        Connecting to PPAS Portal...
        `,

        0,
        0
    );


    return true;
}



async function load_ppas_sessions_action(frm) {

                if (frm.__ppas_loading) {
                    return;
                }


                frm.__ppas_loading =
                    true;


                let dialog = null;


                try {

                    frm.set_value(
                        "status",
                        "Connecting to PPAS Portal..."
                    );


                    frm.refresh_field(
                        "status"
                    );


                    dialog =
                        create_progress_dialog();


                    // -------------------------------------------------
                    // AUTOMATIC AGENT START
                    // -------------------------------------------------

                    await ensure_agent(
                        dialog
                    );


                    // -------------------------------------------------
                    // PPAS SESSION MESSAGE
                    // -------------------------------------------------

                    update_progress(
                        dialog,

                        `
                        <b>
                            PPAS Agent Ready
                        </b>

                        <br><br>

                        Loading PPAS session...

                        <br><br>

                        Chrome will open automatically.

                        <br><br>

                        Enter PPAS username,
                        password and CAPTCHA.

                        <br><br>

                        Waiting for login...
                        `,

                        0,
                        0
                    );

                    const response =
                        await fetch(

                            `${PPAS_AGENT}/seasons`,

                            {
                                method:
                                    "POST",

                                headers: {

                                    "Content-Type":
                                        "application/json"
                                }
                            }
                        );


                    if (!response.ok) {

                        throw new Error(
                            await read_ppas_agent_error(
                                response,
                                `PPAS Agent HTTP ${response.status}`
                            )
                        );
                    }


                    const result =
                        await response.json();


                    if (!result.success) {

                        throw new Error(
                            result.error ||
                            result.message ||
                            "Unable to connect to PPAS."
                        );
                    }


                    const catalog = store_ppas_season_catalog(
                        frm,
                        result.seasons || []
                    );

                    const names = catalog.names;

                    if (!names.length) {

                        throw new Error(
                            "No PPAS seasons found."
                        );
                    }


                    frm.set_df_property(
                        "season",
                        "options",
                        names.join("\n")
                    );


                    frm.refresh_field(
                        "season"
                    );


                    frm.set_value(
                        "status",
                        "PPAS Connected"
                    );


                    frm.refresh_field(
                        "status"
                    );


                    update_progress(
                        dialog,

                        `
                        <b style="color:green;">
                            PPAS Connected Successfully
                        </b>

                        <br><br>

                        Seasons found:
                        <b>${names.length}</b>

                        <br><br>

                        Select a season and click
                        <b>Extract Data</b>.
                        `,

                        names.length,
                        names.length
                    );


                    setTimeout(
                        () => {

                            if (dialog) {

                                dialog.hide();

                                dialog = null;
                            }

                        },
                        1000
                    );

                }

                catch (error) {

                    console.error(
                        "PPAS SESSION ERROR",
                        error
                    );


                    frm.set_value(
                        "status",
                        "PPAS Connection Failed"
                    );


                    frm.refresh_field(
                        "status"
                    );


                    if (dialog) {

                        update_progress(
                            dialog,

                            `
                            <b style="color:red;">
                                PPAS Connection Failed
                            </b>

                            <br><br>

                            ${text(error.message)}
                            `,

                            0,
                            0
                        );


                        setTimeout(
                            () => {

                                if (dialog) {

                                    dialog.hide();

                                    dialog = null;
                                }

                            },
                            2000
                        );
                    }


                    frappe.msgprint({

                        title:
                            "PPAS Connection Error",

                        message:
                            error.message,

                        indicator:
                            "red"
                    });

                }

                finally {

                    frm.__ppas_loading =
                        false;
                }
}

async function extract_data_action(frm) {

                if (frm.__ppas_extracting) {
                    return;
                }


                const season =
                    frm.doc.season;


                if (!season) {

                    frappe.msgprint({

                        title:
                            "Select Season",

                        message:
                            "Please select a season first.",

                        indicator:
                            "orange"
                    });


                    return;
                }


                frm.__ppas_extracting =
                    true;


                let dialog = null;


                try {

                    dialog =
                        create_progress_dialog();

                    await ensure_agent(dialog);

                    update_progress(
                        dialog,
                        `
                        <b>
                            Checking PPAS session...
                        </b>
                        <br><br>
                        Verifying seasons for extraction.
                        `,
                        0,
                        0
                    );

                    await sync_ppas_season_catalog(frm);

                    const season_choice = resolve_ppas_season_choice(
                        frm,
                        season
                    );

                    const season_for_agent =
                        season_choice.name || season;


                    update_progress(
                        dialog,

                        `
                        <b>
                            Extracting ${season_for_agent}...
                        </b>

                        <br><br>

                        Fetching records from PPAS...
                        `,

                        0,
                        0
                    );


                    // =================================================
                    // GET PPAS DATA
                    // =================================================

                    const extract_body = {
                        season: season_for_agent,
                    };

                    if (season_choice.configuration_id) {
                        extract_body.configuration_id =
                            season_choice.configuration_id;
                    }

                    const response =
                        await fetch(

                            `${PPAS_AGENT}/extract`,

                            {

                                method:
                                    "POST",

                                headers: {

                                    "Content-Type":
                                        "application/json"
                                },

                                body:
                                    JSON.stringify(extract_body)
                            }
                        );


                    if (!response.ok) {

                        throw new Error(
                            await read_ppas_agent_error(
                                response,
                                `PPAS Agent HTTP ${response.status}`
                            )
                        );
                    }


                    const result =
                        await response.json();


                    if (!result.success) {

                        throw new Error(
                            result.error ||
                            result.message ||
                            "PPAS extraction failed."
                        );
                    }


                    // =================================================
                    // EXCEL
                    // =================================================

                    const filename =
                        result.filename ||
                        result.file_name ||
                        result.excel_file ||
                        "";


                    let download_url =
                        result.download_url ||
                        "";


                    if (
                        !download_url &&
                        filename
                    ) {

                        download_url =
                            `${PPAS_AGENT}/download/${encodeURIComponent(filename)}`;
                    }


                    update_progress(
                        dialog,

                        `
                        <b>
                            PPAS extract finished.
                        </b>

                        <br><br>

                        Loading row data for import...
                        `,

                        0,
                        Number(result.records || result.record_count || 0)
                    );


                    const rows = await resolve_ppas_extract_rows(
                        result,
                        season_for_agent
                    );


                    const total =
                        rows.length;


                    if (!total) {

                        throw new Error(
                            "No PPAS records found."
                        );
                    }


                    frm.set_value(
                        "records_extracted",
                        total
                    );


                    frm.set_value(
                        "excel_file",
                        filename
                    );


                    frm.set_value(
                        "download_url",
                        download_url
                    );


                    frm.refresh_fields();


                    frm.set_value(
                        "status",
                        "Saving file details..."
                    );

                    await frm.save();

                    if (dialog) {
                        dialog.hide();
                        dialog = null;
                    }

                    frappe.show_progress(
                        __("Importing PPAS Data"),
                        0,
                        total,
                        __("Uploading Excel and saving PPAS Transit Pass...")
                    );

                    let file_content = null;

                    if (download_url) {
                        try {
                            const file_response = await fetch(download_url, {
                                cache: "no-store",
                            });

                            if (file_response.ok) {
                                file_content = array_buffer_to_base64(
                                    await file_response.arrayBuffer()
                                );
                            }
                        } catch (fetch_error) {
                            console.warn("PPAS excel fetch failed", fetch_error);
                        }
                    }

                    const import_response = await frappe.call({
                        method:
                            "ivri_od.procurement.doctype.ppas_transit_pass.ppas_import.run_ppas_extraction_import",
                        args: {
                            extraction_name: frm.doc.name,
                            season,
                            file_content,
                            rows_json: JSON.stringify(rows),
                        },
                        freeze: false,
                    });

                    frappe.hide_progress();

                    const summary = import_response.message || {};
                    const imported = summary.imported || 0;
                    const updated = summary.updated || 0;
                    const failed = summary.failed || 0;

                    if (summary.download_url) {
                        frm.set_value("download_url", summary.download_url);
                        frm.set_value(
                            "excel_file",
                            summary.filename || frm.doc.excel_file
                        );
                    }

                    if (imported + updated === 0) {
                        const sample_error =
                            (summary.errors && summary.errors[0] && summary.errors[0].error) ||
                            __("No records could be saved. Check Error Log for details.");
                        throw new Error(sample_error);
                    }


                    // =================================================
                    // COMPLETE
                    // =================================================

                    frm.set_value(
                        "status",
                        "Import Completed"
                    );


                    frm.refresh_field(
                        "status"
                    );


                    await frm.save();

                    const error_lines = (summary.errors || [])
                        .slice(0, 5)
                        .map((item) => `Row ${item.row}: ${item.error}`)
                        .join("<br>");

                    frappe.msgprint({
                        title: "PPAS Import Completed",
                        message: `
                            <b>Season:</b> ${season}
                            <br><br>
                            <b>Total:</b> ${total}
                            <br>
                            <b>New:</b> ${imported}
                            <br>
                            <b>Updated:</b> ${updated}
                            <br>
                            <b>Failed:</b> ${failed}
                            <br><br>
                            Saved in <b>PPAS Transit Pass</b>.
                            <a href="/app/ppas-transit-pass?season=${encodeURIComponent(season)}">Open list</a>
                            <br><br>
                            Excel: <b>Download Excel File</b>.
                            ${error_lines ? `<br><br><b>Sample errors:</b><br>${error_lines}` : ""}
                        `,
                        indicator: failed > 0 ? "orange" : "green",
                    });

                }

                catch (error) {

                    console.error(
                        "PPAS EXTRACTION ERROR",
                        error
                    );


                    frm.set_value(
                        "status",
                        "Extraction Failed"
                    );


                    frm.refresh_field(
                        "status"
                    );


                    if (dialog) {

                        update_progress(
                            dialog,

                            `
                            <b style="color:red;">
                                PPAS Process Failed
                            </b>

                            <br><br>

                            ${text(error.message)}
                            `,

                            0,
                            0
                        );


                        setTimeout(
                            () => {

                                if (dialog) {

                                    dialog.hide();

                                    dialog = null;
                                }

                            },
                            2500
                        );
                    }


                    frappe.msgprint({

                        title:
                            "PPAS Error",

                        message:
                            `${error.message}<br><br>` +
                            __("PPAS Agent could not retrieve data. You can use " +
                                "<a href=\"/app/ppas-transit-pass-import\">Manual PPAS Import</a> as a backup."),

                        indicator:
                            "red"

                    });

                }

                finally {

                    frappe.hide_progress();

                    frm.__ppas_extracting =
                        false;
                }
}

function download_excel_action(frm) {
    if (!frm.doc.download_url) {
        frappe.msgprint({
            title: "Excel Not Available",
            message: "Please extract PPAS data first.",
            indicator: "orange",
        });
        return;
    }

    let url = frm.doc.download_url.trim();

    if (url.startsWith("/")) {
        url = frappe.urllib.get_full_url(url);
    }

    if (url.includes("/files/") || url.includes("/private/files/")) {
        const link = document.createElement("a");
        link.href = url;
        link.download = frm.doc.excel_file || "PPAS_Transit_Pass.xlsx";
        link.target = "_blank";
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        return;
    }

    window.open(url, "_blank", "noopener");
}

async function close_ppas_session_action(frm) {

                if (frm.__ppas_closing) {
                    return;
                }


                frm.__ppas_closing =
                    true;


                try {

                    const response =
                        await fetch(

                            `${PPAS_AGENT}/close`,

                            {

                                method:
                                    "POST",

                                headers: {

                                    "Content-Type":
                                        "application/json"

                                }

                            }
                        );


                    if (!response.ok) {

                        throw new Error(
                            `PPAS Agent HTTP ${response.status}`
                        );
                    }


                    const result =
                        await response.json();


                    if (!result.success) {

                        throw new Error(
                            result.message ||
                            "Unable to close PPAS session."
                        );
                    }


                    frm.set_value(
                        "status",
                        "PPAS Session Closed"
                    );


                    frm.refresh_field(
                        "status"
                    );


                    frappe.show_alert({

                        message:
                            "PPAS Chrome session closed",

                        indicator:
                            "green"

                    });

                }

                catch (error) {

                    frappe.msgprint({

                        title:
                            "Close Session Error",

                        message:
                            error.message,

                        indicator:
                            "red"

                    });

                }

                finally {

                    frm.__ppas_closing =
                        false;
                }
}

async function render_ppas_column_mapping(frm) {
    if (!frm.fields_dict.column_mapping_html) {
        return;
    }

    const response = await frappe.call({
        method:
            "ivri_od.procurement.doctype.ppas_transit_pass.ppas_field_mapping.get_ppas_column_mapping",
        freeze: false,
    });

    const mapping = response.message || {};
    const rows = (mapping.excel_to_doctype || [])
        .map(
            (item) => `
            <tr>
                <td><b>${frappe.utils.escape_html(item.excel_column)}</b></td>
                <td><code>${frappe.utils.escape_html(item.fieldname)}</code></td>
                <td>${frappe.utils.escape_html(item.label)}</td>
                <td>${frappe.utils.escape_html(item.fieldtype)}</td>
            </tr>`
        )
        .join("");

    const extra = (mapping.extra_doctype_fields || [])
        .map(
            (item) => `
            <tr>
                <td><i>auto</i></td>
                <td><code>${frappe.utils.escape_html(item.fieldname)}</code></td>
                <td>${frappe.utils.escape_html(item.label)}</td>
                <td>${frappe.utils.escape_html(item.source)}</td>
            </tr>`
        )
        .join("");

    frm.fields_dict.column_mapping_html.$wrapper.html(`
        <div class="text-muted" style="margin-bottom:8px;">
            Target DocType: <b>${frappe.utils.escape_html(mapping.target_doctype || "PPAS Transit Pass")}</b>.
            Excel must include separate
            <b>Transit Pass Date</b>, <b>Transit Pass Time</b>,
            <b>Accepted Date</b>, <b>Accepted Time</b> columns.
        </div>
        <table class="table table-bordered table-sm" style="font-size:12px;">
            <thead>
                <tr>
                    <th>Excel column</th>
                    <th>DocType field</th>
                    <th>Label</th>
                    <th>Type</th>
                </tr>
            </thead>
            <tbody>${rows}${extra}</tbody>
        </table>
    `);
}

frappe.ui.form.on("PPAS Data Extraction", {
    refresh(frm) {
        render_ppas_column_mapping(frm);

        frm.toggle_display(
            [
                "actions_section",
                "load_ppas_sessions",
                "extract_data",
                "column_break_actions",
                "download_excel_file",
                "close_ppas_session",
            ],
            false
        );

        frm.remove_custom_button("Load PPAS Sessions");
        frm.remove_custom_button("Extract Data");
        frm.remove_custom_button("Download Excel File");
        frm.remove_custom_button("Close PPAS Session");

        frm.add_custom_button("Load PPAS Sessions", () =>
            load_ppas_sessions_action(frm)
        );
        frm.add_custom_button("Extract Data", () => extract_data_action(frm));
        frm.add_custom_button("Download Excel File", () =>
            download_excel_action(frm)
        );
        frm.add_custom_button("Close PPAS Session", () =>
            close_ppas_session_action(frm)
        );
    },
});
