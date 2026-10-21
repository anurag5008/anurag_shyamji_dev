"""
Portal scraper for SCMS, DCRO, WINGS and similar government portals.

How it works:
1. Chrome opens the portal login page. The user logs in by hand
   (username, password, CAPTCHA). No credentials pass through this code.
2. The user opens any page from the portal's own menu (the agent never
   opens pages itself: deep links end the portal session), sets filters
   and clicks Search.
3. The agent notices the Search click, waits for the result table,
   reads every page of it and, if asked, saves the receipt PDF of each row.
   It also records the page URL and heading so the ERP can name the section.
4. Frappe polls the agent and pulls the rows and receipts.

The PPAS scraper (ppas_scraper.py) is not touched by this module.
"""

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import uuid
from urllib.parse import urljoin, urlparse

import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException, UnexpectedAlertPresentException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys


# ============================================================
# SETTINGS
# ============================================================

POLL_SECONDS = 1.5
PAGE_WAIT_SECONDS = 30
RESULT_WAIT_SECONDS = 45
RECEIPT_WAIT_SECONDS = 25
DETAIL_WAIT_SECONDS = 15
MAX_PAGES = 300
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
KEEP_RESULTS = 10

RECEIPT_LINK_PATTERN = re.compile(
    r"pdf|receipt|print|download|challan|slip|ack|view|report",
    re.IGNORECASE,
)
SKIP_LINK_PATTERN = re.compile(
    r"page\$|delete|remove|edit|update|cancel|logout|sign ?out",
    re.IGNORECASE,
)


# ============================================================
# BROWSER SCRIPTS
# ============================================================

# Marks a click on a Search-like button. sessionStorage survives the full
# page reload of an ASP.NET postback, so the click is not lost.
# arguments[0]: the section's "Extract On Click" texts for this page (letters and
# digits, lower case), e.g. "save" or "dvmillerhistory": a click on an element
# (or inside one) whose id or button label contains one also counts. A text box
# (e.g. the DataTables search box of DCRO DC Transit Challan, gvDCDetails_filter)
# counts when the user types a value in it and presses Enter, not when clicked.
JS_INSTALL_CLICK_HOOK = r"""
window.__pdeTriggers = (arguments.length && arguments[0]) || [];
if (!window.__pdeHooked) {
    window.__pdeHooked = true;
    var pdeTextBox = function (el) {
        return !!el && (/^(TEXTAREA|SELECT)$/.test(el.tagName) || (el.tagName === 'INPUT'
            && !/^(submit|button|image|checkbox|radio|reset)$/i.test(el.type || '')));
    };
    var pdeTriggerHit = function (target) {
        var triggers = window.__pdeTriggers || [];
        for (var node = target, up = 0; triggers.length && node && node.nodeType === 1 && up < 8; node = node.parentElement, up++) {
            var own = /^(INPUT|BUTTON|A)$/.test(node.tagName) ? [node.value, node.innerText, node.name, node.title].join(' ') : '';
            var key = ((node.id || '') + ' ' + (own || '')).toLowerCase().replace(/[^a-z0-9]/g, '');
            if (triggers.some(function (t) { return t && key.indexOf(t) !== -1; })) { return true; }
        }
        return false;
    };
    document.addEventListener('keydown', function (ev) {
        try {
            if (ev.key !== 'Enter' || sessionStorage.getItem('__pde_agent_busy') === '1') { return; }
            var el = ev.target;
            if (pdeTextBox(el) && (el.value || '').trim() && pdeTriggerHit(el)) {
                sessionStorage.setItem('__pde_search_ts', Date.now() + '|t|' + location.pathname);
            }
        } catch (e) {}
    }, true);
    document.addEventListener('click', function (ev) {
        try {
            if (sessionStorage.getItem('__pde_agent_busy') === '1') { return; }
            // Clicking into a text box only starts typing; Enter in it is the trigger (see keydown).
            if (!pdeTextBox(ev.target) && pdeTriggerHit(ev.target)) {
                // "t": a section's own Extract On Click button, and the page it was clicked on.
                sessionStorage.setItem('__pde_search_ts', Date.now() + '|t|' + location.pathname);
                return;
            }
            var el = ev.target && ev.target.closest
                ? ev.target.closest('input[type=submit],input[type=button],input[type=image],button,a')
                : null;
            if (!el) { return; }
            var href = (el.getAttribute('href') || '');
            if (el.tagName === 'A' && href.indexOf('__doPostBack') === -1) { return; }
            if (/Page\$/.test(href)) { return; }
            var label = [el.value, el.innerText, el.id, el.name, el.title]
                .join(' ').toLowerCase();
            if (/logout|log out|sign out|reset|clear|cancel|export|excel|print/.test(label)) { return; }
            var pattern = el.tagName === 'A'
                ? /search|submit|\bgo\b|find/
                : /search|show|view|submit|get|find|\bgo\b|report|display/;
            if (pattern.test(label)) {
                sessionStorage.setItem('__pde_search_ts', Date.now() + '|g|' + location.pathname);
            }
        } catch (e) {}
    }, true);
}
try { return sessionStorage.getItem('__pde_search_ts') || ''; } catch (e) { return ''; }
"""

JS_SET_BUSY = "try { sessionStorage.setItem('__pde_agent_busy', arguments[0] ? '1' : '0'); } catch (e) {}"

JS_PAGE_READY = r"""
if (document.readyState !== 'complete') { return false; }
try {
    if (window.Sys && Sys.WebForms && Sys.WebForms.PageRequestManager) {
        var prm = Sys.WebForms.PageRequestManager.getInstance();
        if (prm && prm.get_isInAsyncPostBack()) { return false; }
    }
} catch (e) {}
return true;
"""

# Logged in = no visible password box, and either the URL moved away from
# the login page or the page offers a Logout link.
JS_LOGIN_STATE = r"""
var inputs = document.querySelectorAll('input[type=password]');
for (var i = 0; i < inputs.length; i++) {
    if (inputs[i].offsetParent !== null) { return {password: true, logout: false}; }
}
var text = (document.body && document.body.innerText) || '';
return {password: false, logout: /log ?out|sign ?out/i.test(text)};
"""

# Shared helpers for the table scripts below.
JS_TABLE_HELPERS = r"""
function pdeText(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); }
function pdeHash(s) { var x = 5381; for (var i = 0; i < s.length; i++) { x = ((x << 5) + x + s.charCodeAt(i)) | 0; } return String(x); }
// Visible tables with at least a header and one data row, with their header text.
function pdeDataTables() {
    var out = [];
    var tables = document.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
        var t = tables[i];
        if (t.offsetParent === null) { continue; }
        var dataRows = 0, maxCells = 0, header = null;
        for (var r = 0; r < t.rows.length; r++) {
            var row = t.rows[r];
            if (row.querySelector('table')) { continue; }
            if (row.cells.length >= 2) {
                dataRows++;
                if (row.cells.length > maxCells) { maxCells = row.cells.length; }
                if (header === null) { header = Array.prototype.map.call(row.cells, pdeText).join('|'); }
            }
        }
        if (dataRows < 2) { continue; }
        out.push({table: t, score: dataRows * maxCells, header: header || ''});
    }
    return out;
}
function pdeKey(s) { return (s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
// Label of the open tab (AJAX Toolkit, Bootstrap, ARIA or ASP.NET Menu tabs), or ''.
function pdeActiveTab() {
    var sel = ['.ajax__tab_active .ajax__tab_tab', '.ajax__tab_active', '.nav-tabs .active > a', '.nav-tabs .nav-link.active',
               '[role=tab][aria-selected=true]', 'a.selected', 'a.static.selected', 'li.active > a', '.tab.active', '.tabs .active'];
    for (var i = 0; i < sel.length; i++) {
        var els = document.querySelectorAll(sel[i]);
        for (var j = 0; j < els.length; j++) {
            var t = pdeText(els[j]);
            if (els[j].offsetParent !== null && t && t.length <= 80) { return t; }
        }
    }
    return '';
}
// id and title (caption, or the nearest short text above it) of a table.
function pdeTableInfo(t) {
    var title = t.caption ? pdeText(t.caption) : '';
    for (var node = t, up = 0; node && !title && up < 5; node = node.parentElement, up++) {
        for (var prev = node.previousElementSibling, n = 0; prev && n < 3; prev = prev.previousElementSibling, n++) {
            var text = pdeText(prev);
            if (text && text.length <= 120 && !prev.querySelector('table')) { title = text; break; }
        }
    }
    var id = t.id || '';
    for (var a = t.parentElement, k = 0; a && !id && k < 3; a = a.parentElement, k++) { id = a.id || ''; }
    // Every id around the table (e.g. WINGS: the table inside div#report_div has its own id).
    var ids = [];
    for (var b = t; b && b !== document.body; b = b.parentElement) { if (b.id) { ids.push(b.id); } }
    return {table_id: id, table_title: title, table_ids: ids.join(' ')};
}
"""

# Marks the result table with data-pde-grid and returns its text so Python can
# tell when it changes. With a header (arguments[0]) only a table with that
# exact header row counts; otherwise the biggest visible data table wins.
JS_FIND_GRID = JS_TABLE_HELPERS + r"""
var expected = arguments.length ? arguments[0] : null;
var matches = (arguments.length > 1 && arguments[1]) || [];
// strict: only a table named by matches counts (one table of a page with several, e.g. WINGS e_tec).
var strict = arguments.length > 2 && arguments[2];
var best = null;
var all = document.querySelectorAll('table[data-pde-grid]');
for (var i = 0; i < all.length; i++) { all[i].removeAttribute('data-pde-grid'); }
var candidates = pdeDataTables().filter(function (c) { return !expected || c.header === expected; });
if (matches.length) {
    // Page with several tables or tabs: keep the table named by the section's "Table Match".
    var tab = pdeKey(pdeActiveTab());
    var matched = candidates.filter(function (c) {
        var info = pdeTableInfo(c.table);
        var text = pdeKey(info.table_id) + ' ' + pdeKey(info.table_title) + ' ' + tab + ' ' +
            info.table_ids.split(' ').map(pdeKey).join(' ');
        return matches.some(function (m) { return m && text.indexOf(m) !== -1; });
    });
    if (matched.length || strict) { candidates = matched; }
}
candidates.forEach(function (c) {
    if (!best || c.score > best.score) { best = c; }
});
if (!best) { return null; }
best.table.setAttribute('data-pde-grid', '1');
best.table.setAttribute('data-pde-header', best.header);
return pdeText(best.table);
"""

JS_GRID_HEADER = "var t = document.querySelector('table[data-pde-grid=\"1\"]'); return t ? t.getAttribute('data-pde-header') : null;"

# The request a row button would send, without clicking it: the page's form
# fields (filters, __VIEWSTATE, ...) plus that button. Replaying this request
# over HTTP reads the detail page while the Chrome page (and its filters) stays as it is.
JS_BUTTON_REQUEST = r"""
var el = document.querySelector('[data-pde-link="' + arguments[0] + '"]');
if (!el) { return null; }
var code = (el.getAttribute('href') || '') + ' ' + (el.getAttribute('onclick') || '');
var open = code.match(/(?:window\.open|location\.href\s*=|location\s*=)\s*\(?\s*['"]([^'"]+)['"]/);
if (open && !/__doPostBack|WebForm_DoPostBack/.test(code)) {
    return {get_url: new URL(open[1], location.href).href};
}
// A plain link to the detail page (no script): read it with a GET.
var rawHref = el.getAttribute('href') || '';
if (el.tagName === 'A' && rawHref && rawHref.charAt(0) !== '#' && !/^javascript:/i.test(rawHref) && !el.getAttribute('onclick')) {
    return {get_url: el.href};
}
var form = el.form || el.closest('form') || document.forms[0];
if (!form) { return null; }
var fields = [];
for (var i = 0; i < form.elements.length; i++) {
    var f = form.elements[i];
    var type = (f.type || '').toLowerCase();
    if (!f.name || f.disabled || ['submit', 'button', 'image', 'reset', 'file'].indexOf(type) !== -1) { continue; }
    if ((type === 'checkbox' || type === 'radio') && !f.checked) { continue; }
    if (f.tagName === 'SELECT' && f.multiple) {
        for (var o = 0; o < f.options.length; o++) { if (f.options[o].selected) { fields.push([f.name, f.options[o].value]); } }
        continue;
    }
    fields.push([f.name, f.value]);
}
function setField(name, value) {
    for (var k = 0; k < fields.length; k++) { if (fields[k][0] === name) { fields[k][1] = value; return; } }
    fields.push([name, value]);
}
var m = code.match(/__doPostBack\(\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]/);
var m2 = code.match(/WebForm_PostBackOptions\(\s*["']([^"']*)["']\s*,\s*["']([^"']*)["']/);
if (el.tagName === 'A' && (m || m2)) {
    setField('__EVENTTARGET', (m || m2)[1]);
    setField('__EVENTARGUMENT', (m || m2)[2]);
} else if (el.name) {
    if ((el.type || '').toLowerCase() === 'image') {
        fields.push([el.name + '.x', '1'], [el.name + '.y', '1']);
    } else {
        fields.push([el.name, el.value || '']);
    }
} else if (m) {
    setField('__EVENTTARGET', m[1]);
    setField('__EVENTARGUMENT', m[2]);
} else {
    return null;
}
return {
    action: new URL(form.getAttribute('action') || location.href, location.href).href,
    method: (form.method || 'post').toLowerCase(),
    fields: fields
};
"""

# Where the table came from: URL, browser title and the page heading.
JS_PAGE_INFO = JS_TABLE_HELPERS + r"""
function txt(el) { return (el && (el.innerText || el.textContent) || '').replace(/\s+/g, ' ').trim(); }
var heading = '';
var selectors = [
    '[id*="lblHead" i]', '[id*="lblTitle" i]', '[id*="PageTitle" i]', '[id*="lblHeader" i]',
    '[class*="page-title" i]', '[class*="pagetitle" i]', '[class*="panel-heading" i]', 'h1', 'h2', 'h3', 'h4'
];
for (var i = 0; i < selectors.length && !heading; i++) {
    var els = document.querySelectorAll(selectors[i]);
    for (var j = 0; j < els.length; j++) {
        var t = txt(els[j]);
        if (els[j].offsetParent !== null && t && t.length <= 120) { heading = t; break; }
    }
}
var grid = document.querySelector('table[data-pde-grid="1"]');
var info = grid ? pdeTableInfo(grid) : {table_id: '', table_title: '', table_ids: ''};
// Search filters (e.g. KMS Year, Depot): visible drop-downs and text boxes outside the result table.
function pdeFilterLabel(el) {
    var label = '';
    if (el.id) {
        var lab = document.querySelector('label[for="' + el.id.replace(/"/g, '') + '"]');
        if (lab) { label = txt(lab); }
    }
    var td = el.closest('td');
    for (var p = td && td.previousElementSibling; !label && p; p = p.previousElementSibling) {
        if (!p.querySelector('select, input, textarea')) { label = txt(p); }
        else { break; }
    }
    for (var s = el.previousElementSibling; !label && s; s = s.previousElementSibling) {
        if (!s.querySelector('select, input, textarea') && !/^(SELECT|INPUT|TEXTAREA)$/.test(s.tagName)) { label = txt(s); }
    }
    return (label || el.getAttribute('placeholder') || el.getAttribute('title') || '').slice(0, 80);
}
var filters = [];
var fields = document.querySelectorAll('select, input[type=text], input[type=date], input:not([type])');
for (var f = 0; f < fields.length && filters.length < 30; f++) {
    var el = fields[f];
    if (el.offsetParent === null || (grid && grid.contains(el))) { continue; }
    var value = el.tagName === 'SELECT'
        ? (el.selectedIndex >= 0 ? txt(el.options[el.selectedIndex]) : '')
        : (el.value || '').trim();
    if (!value) { continue; }
    filters.push({label: pdeFilterLabel(el), id: el.id || el.name || '', value: value.slice(0, 140)});
}
// Values in the page address (e.g. WINGS e_tec?cyear=2025-26) count as filters too.
try {
    new URL(location.href).searchParams.forEach(function (value, name) {
        if (value && filters.length < 30) { filters.push({label: name, id: name, value: value.slice(0, 140)}); }
    });
} catch (e) {}
return {url: location.href, title: (document.title || '').trim(), heading: heading,
        table_id: info.table_id, table_title: info.table_title, table_ids: info.table_ids,
        active_tab: pdeActiveTab(), filters: filters};
"""

# Expands jQuery DataTables (client-side paging) to show all rows.
JS_SHOW_ALL_DATATABLE = r"""
var t = document.querySelector('table[data-pde-grid="1"]');
if (!t || !window.jQuery) { return false; }
try {
    var $t = window.jQuery(t);
    if (window.jQuery.fn.dataTable && window.jQuery.fn.dataTable.isDataTable(t)) {
        if ($t.DataTable().page.len() === -1) { return false; }
        $t.DataTable().page.len(-1).draw();
        return true;
    }
} catch (e) {}
return false;
"""

# Reads a table as raw rows: every cell as [text, rowspan, colspan, is_th, nested]
# where nested is the rows of a table inside the cell (e.g. "BRL Lot Details")
# or null, plus the links in the row. grid_to_table() turns this into headers +
# data, expanding merged cells and spreading nested tables over their sub-columns.
JS_ROW_READER = r"""
function pdeTxt(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); }
function pdeReadRows(t, markLinks) {
    var out = [];
    for (var r = 0; r < t.rows.length; r++) {
        var row = t.rows[r];
        if (!row.cells.length || row.querySelector('a[href*="Page$"]')) { continue; }
        var cells = [];
        for (var c = 0; c < row.cells.length; c++) {
            var cell = row.cells[c];
            var inner = cell.querySelector('table');
            var nested = null;
            if (inner) {
                nested = [];
                for (var n = 0; n < inner.rows.length; n++) {
                    var nr = inner.rows[n];
                    if (nr.querySelector('table')) { continue; }
                    var vals = [], allTh = nr.cells.length > 0;
                    for (var m = 0; m < nr.cells.length; m++) {
                        vals.push(pdeTxt(nr.cells[m]));
                        if (nr.cells[m].tagName !== 'TH') { allTh = false; }
                    }
                    if (!allTh && vals.some(function (v) { return v; })) { nested.push(vals); }
                }
            }
            cells.push([inner ? '' : pdeTxt(cell), cell.rowSpan || 1, cell.colSpan || 1, cell.tagName === 'TH', nested]);
        }
        var links = [];
        if (markLinks) {
            var els = row.querySelectorAll('a, input[type=image], input[type=submit], input[type=button], button');
            for (var k = 0; k < els.length; k++) {
                var el = els[k];
                var ref = 'r' + out.length + '-l' + k;
                el.setAttribute('data-pde-link', ref);
                var raw = el.getAttribute('href') || '';
                // Column of the button (sum of the colspans before its cell), so a
                // document can be picked by its column header (e.g. "AC Note Doc").
                var col = 0;
                for (var q = 0; q < row.cells.length; q++) {
                    if (row.cells[q].contains(el)) { break; }
                    col += row.cells[q].colSpan || 1;
                }
                links.push({
                    ref: ref,
                    col: col,
                    text: [pdeTxt(el), el.value || '', el.title || '', el.id || '', el.getAttribute('alt') || ''].join(' ').trim(),
                    label: (pdeTxt(el) || el.value || el.title || el.getAttribute('alt') || '').trim(),
                    href: el.tagName === 'A' && raw && raw.indexOf('javascript:') !== 0 ? el.href : '',
                    raw_href: raw,
                    is_postback: el.tagName !== 'A' || raw.indexOf('javascript:') === 0
                });
            }
        }
        out.push({cells: cells, links: links});
    }
    return out;
}
"""

# Reads the marked result table of the page.
JS_READ_GRID = JS_ROW_READER + r"""
var t = document.querySelector('table[data-pde-grid="1"]');
if (!t) { return null; }
// Link refs restart at r0-l0 for every table read; clear old ones so a click never hits a stale ref.
var stale = document.querySelectorAll('[data-pde-link]');
for (var s = 0; s < stale.length; s++) { stale[s].removeAttribute('data-pde-link'); }
return {rows: pdeReadRows(t, true)};
"""

# Reads the detail table out of the HTML reply of a View button. Chrome's own
# parser (DOMParser) builds the document in memory: nothing is shown, no script
# runs, and the page in the window is not touched. arguments: html, table id,
# result-table header (a table with that header is not the detail).
JS_READ_DETAIL_HTML = JS_ROW_READER + r"""
var doc = new DOMParser().parseFromString(arguments[0] || '', 'text/html');
var wanted = arguments[1], mainHeader = arguments[2] || '', strict = !!arguments[3];
function pdeHeaderOf(tab) {
    for (var r = 0; r < tab.rows.length; r++) {
        var row = tab.rows[r];
        if (row.querySelector('table')) { continue; }
        if (row.cells.length >= 2) { return Array.prototype.map.call(row.cells, pdeTxt).join('|'); }
    }
    return '';
}
// The same id may be used by the result table and the detail table (SCMS
// DC Monitoring: both are gdvGetPassRegister). Take the one that is not the result table.
var t = null;
var hits = wanted ? doc.querySelectorAll('[id="' + wanted.replace(/["\\]/g, '') + '"]') : [];
for (var h = 0; h < hits.length && !t; h++) {
    // The id may sit on the table, on a part of it (e.g. the tbody of DCRO View DC's
    // grdDepotFCIbody) or on a box around it.
    var el = hits[h], tag = el.tagName;
    var tab = tag === 'TABLE' ? el : (/^(TBODY|THEAD|TFOOT|TR|TD|TH)$/.test(tag) ? el.closest('table') : el.querySelector('table'));
    if (tab && !(mainHeader && pdeHeaderOf(tab) === mainHeader)) { t = tab; }
}
if (!t && !strict) {
    var best = null, bestScore = 0, tables = doc.querySelectorAll('table');
    for (var i = 0; i < tables.length; i++) {
        var cand = tables[i], dataRows = 0, maxCells = 0, header = null;
        for (var r = 0; r < cand.rows.length; r++) {
            var row = cand.rows[r];
            if (row.cells.length < 2) { continue; }
            dataRows++;
            if (row.cells.length > maxCells) { maxCells = row.cells.length; }
            if (header === null) { header = Array.prototype.map.call(row.cells, pdeTxt).join('|'); }
        }
        if (dataRows < 2 || header === mainHeader) { continue; }
        if (dataRows * maxCells > bestScore) { best = cand; bestScore = dataRows * maxCells; }
    }
    t = best;
}
return t ? {rows: pdeReadRows(t, false)} : null;
"""

# Reads one cell of every row of the elements with the given ids, like the XPath
# //*[@id="grdDepotFCIbody"]/tr/td[4]. arguments[0]: [[id, column number (1 = first td)], ...].
# Returns [{id, value, row: [cell texts]}], or null when none of the ids is on the page.
JS_READ_PAGE_COLUMNS = r"""
function txt(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); }
var out = [], found = false, specs = arguments[0] || [];
for (var i = 0; i < specs.length; i++) {
    var el = document.getElementById(specs[i][0]);
    if (!el) { continue; }
    found = true;
    var rows = /^(TABLE|TBODY|THEAD|TFOOT)$/.test(el.tagName) ? el.rows : el.querySelectorAll('tr');
    for (var r = 0; r < rows.length; r++) {
        var tds = [];
        for (var c = 0; c < rows[r].children.length; c++) {
            if (rows[r].children[c].tagName === 'TD') { tds.push(rows[r].children[c]); }
        }
        var td = tds[specs[i][1] - 1];
        if (!td) { continue; }
        out.push({id: specs[i][0], value: txt(td), row: tds.map(txt)});
    }
}
return found ? out : null;
"""

# Clicks a row's document button. arguments: link ref, the row's id values
# (row_tokens), the button's column and label. The list may have changed
# since it was read (e.g. after Back from a Details page), so the row must still
# hold all its id values; if not, the row that does is found and its button in
# the same column is clicked. Returns 'ok', 'moved' or 'missing'.
JS_CLICK_ROW_LINK = r"""
var ref = arguments[0], tokens = arguments[1] || [], col = arguments[2], label = arguments[3] || '';
function sq(el) { return (el.innerText || el.textContent || '').toLowerCase().replace(/\s+/g, ''); }
function found(tr) { var t = tr ? sq(tr) : ''; return tokens.filter(function (k) { return t.indexOf(k) !== -1; }).length; }
function rowOk(tr) { return found(tr) === tokens.length; }
function labelOf(el) { return (sq(el) || (el.value || el.title || el.getAttribute('alt') || '').toLowerCase().replace(/\s+/g, '')); }
var el = document.querySelector('[data-pde-link="' + ref + '"]');
if (el && (!tokens.length || rowOk(el.closest('tr')))) { el.click(); return 'ok'; }
var t = document.querySelector('table[data-pde-grid="1"]');
if (!t || !tokens.length) { return 'missing'; }
for (var r = 0; r < t.rows.length; r++) {
    var row = t.rows[r];
    if (row.querySelector('table') || !rowOk(row)) { continue; }
    var els = row.querySelectorAll('a, input[type=image], input[type=submit], input[type=button], button');
    for (var k = 0; k < els.length; k++) {
        var at = 0;
        for (var q = 0; q < row.cells.length; q++) {
            if (row.cells[q].contains(els[k])) { break; }
            at += row.cells[q].colSpan || 1;
        }
        if (at === col && (!label || labelOf(els[k]) === label)) { els[k].click(); return 'moved'; }
    }
}
// No row holds every value (merged cells hide some): the original row still counts if it holds most.
if (el && found(el.closest('tr')) * 2 > tokens.length) { el.click(); return 'ok'; }
return 'missing';
"""

JS_PAGE_TEXT = "return (document.body && (document.body.innerText || document.body.textContent)) || '';"

# Clicks the visible button whose label, title, tooltip or id contains
# arguments[0] (letters and digits, lower case), e.g. the "Print" icon of the
# DCRO Transit Challan page. An exact label or tooltip ("Print") wins over a
# partial one ("Print Report").
JS_CLICK_PRINT = r"""
var key = arguments[0];
function k(s) { return (s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
var els = document.querySelectorAll('a, button, input[type=button], input[type=submit], input[type=image], [onclick]');
var exact = null, part = null;
for (var i = 0; i < els.length; i++) {
    var el = els[i];
    if (!el.getClientRects().length || el.disabled) { continue; }
    var names = [k(el.innerText || el.value), k(el.title), k(el.getAttribute('data-original-title')),
                 k(el.getAttribute('aria-label')), k(el.getAttribute('alt'))];
    if (names.indexOf(key) !== -1 && !exact) { exact = el; }
    else if ((names.join(' ') + ' ' + k(el.id)).indexOf(key) !== -1 && !part) { part = el; }
}
var target = exact || part;
if (!target) { return false; }
target.click();
return true;
"""

# Before a detail button is clicked by hand: note every table's text (visible
# or not), so the table the click fills (pop-up, panel) can be told apart.
JS_MARK_TABLES = r"""
function pdeTxt(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); }
function pdeHash(s) { var x = 5381; for (var i = 0; i < s.length; i++) { x = ((x << 5) + x + s.charCodeAt(i)) | 0; } return String(x); }
var tables = document.querySelectorAll('table');
for (var i = 0; i < tables.length; i++) {
    tables[i].setAttribute('data-pde-seen', pdeHash(pdeTxt(tables[i])) + '|' + (tables[i].getClientRects().length ? 1 : 0));
}
"""

# After the click: the visible table, other than the result table, that is new,
# has new text, or was hidden before (a pop-up showing again). arguments[0]: the
# section's Detail Table ID (optional). Returns {rows, sig, changed} or null.
JS_READ_NEW_TABLE = JS_ROW_READER + r"""
function pdeHash(s) { var x = 5381; for (var i = 0; i < s.length; i++) { x = ((x << 5) + x + s.charCodeAt(i)) | 0; } return String(x); }
var wanted = (arguments[0] || '').toLowerCase().replace(/[^a-z0-9]/g, '');
var grid = document.querySelector('table[data-pde-grid="1"]');
var best = null, bestScore = -1;
var tables = document.querySelectorAll('table');
for (var i = 0; i < tables.length; i++) {
    var t = tables[i];
    if (!t.getClientRects().length || t === grid || (grid && (grid.contains(t) || t.contains(grid)))) { continue; }
    var rows = 0;
    for (var r = 0; r < t.rows.length; r++) { if (t.rows[r].cells.length >= 2) { rows++; } }
    if (rows < 2) { continue; }
    var sig = pdeHash(pdeTxt(t));
    var seen = (t.getAttribute('data-pde-seen') || '').split('|');
    var changed = !seen[0] || seen[0] !== sig;
    if (!changed && seen[1] === '1') { continue; }  // shown before the click, unchanged: not the detail
    var ids = '';
    for (var b = t; b && b !== document.body; b = b.parentElement) { ids += ' ' + (b.id || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
    var score = rows + (wanted && ids.indexOf(wanted) !== -1 ? 100000 : 0) + (changed ? 1000 : 0);
    if (score > bestScore) { best = {table: t, sig: sig, changed: changed}; bestScore = score; }
}
if (!best) { return null; }
return {rows: pdeReadRows(best.table, false), sig: best.sig, changed: best.changed};
"""

# Closes the open pop-up (Bootstrap, jQuery UI or a plain dialog). Returns true when a close button was clicked.
JS_CLOSE_POPUP = r"""
var boxes = document.querySelectorAll('.modal.show, .modal.in, .modal[style*="block"], [role=dialog], .ui-dialog, .popup, .swal2-popup');
for (var i = 0; i < boxes.length; i++) {
    var box = boxes[i];
    if (!box.getClientRects().length) { continue; }
    var close = box.querySelector('[data-dismiss=modal], [data-bs-dismiss=modal], .btn-close, button.close, .ui-dialog-titlebar-close');
    if (!close) {
        var buttons = box.querySelectorAll('button, a, input[type=button]');
        for (var j = 0; j < buttons.length && !close; j++) {
            if (/^(close|cancel|ok|x|\u00d7)$/i.test((buttons[j].innerText || buttons[j].value || '').trim())) { close = buttons[j]; }
        }
    }
    if (close) { close.click(); return true; }
}
return false;
"""

# The mill the logged-in user works for (e.g. "Mill ID : 123", or the hidden
# field hdnmillercode). arguments[0]: the site's "Mill ID Labels" (letters and
# digits, lower case), e.g. ["millid", "millcode", "millercode"]. Returns "" if not found.
JS_FIND_MILL_ID = r"""
var keys = arguments[0] || [];
function k(s) { return (s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
// 0. The site's "Mill ID XPath" (arguments[2]), e.g. the WINGS dashboard header line.
//    Its text may be "Mill ID : 41498", "NAME - 41498" or just "41498".
if (arguments[2]) {
    try {
        var node = document.evaluate(arguments[2], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        var own = node ? (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim() : '';
        // A label inside it wins, e.g. WINGS "NAME-41498 [State Code : M051007 ]" with label "State Code".
        var named = arguments[1] || [];
        for (var q = 0; q < named.length; q++) {
            var w = named[q].replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s*');
            var hit = own.match(new RegExp(w + '\\s*[:\\-\u2013]?\\s*([A-Za-z0-9][A-Za-z0-9/_-]{1,29})', 'i'));
            if (hit && /\d/.test(hit[1])) { return hit[1]; }
        }
        var tokens = own.split(/[\s:,()\-\u2013|#]+/).filter(function (t) { return /\d/.test(t) && /^[A-Za-z0-9/_]{3,30}$/.test(t); });
        if (tokens.length) { return tokens[tokens.length - 1]; }
    } catch (e) {}
}
function good(v) { v = (v || '').trim(); return /^[A-Za-z0-9][A-Za-z0-9\/_-]{1,29}$/.test(v) && /\d/.test(v) ? v : ''; }
// 1. A field (often hidden) named after a label, e.g. hdnmillercode, txtMillId.
var inputs = document.querySelectorAll('input, select');
for (var i = 0; i < inputs.length; i++) {
    var name = k(inputs[i].id) + ' ' + k(inputs[i].name);
    if (keys.some(function (key) { return key && name.indexOf(key) !== -1; })) {
        var v = good(inputs[i].value);
        if (v) { return v; }
    }
}
// 2. Text such as "Mill ID : 123" or "Miller Code M051007" (also label and value in two cells).
var text = (document.body && document.body.innerText) || '';
var labels = arguments[1] || [];
for (var j = 0; j < labels.length; j++) {
    var words = labels[j].replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s*');
    var re = new RegExp(words + '\\s*(?:no\\.?|number)?\\s*[:\\-\u2013]?\\s*\\(?([A-Za-z0-9][A-Za-z0-9/_-]{1,29})', 'gi');
    for (var m = re.exec(text), n = 0; m && n < 50; m = re.exec(text), n++) {
        if (good(m[1])) { return m[1]; }  // e.g. skips the header "Miller Code  Miller Name"
    }
}
return '';
"""

JS_DOC_KEY = "return String(performance.timeOrigin) + ' ' + location.href;"

# A message in the corner of the portal page (not an alert: that would stop the
# portal's own scripts). arguments: text, color (green, orange, red, blue).
JS_TOAST = r"""
var colors = {green: '#0f5c5c', orange: '#b45309', red: '#b91c1c', blue: '#1e40af'};
var old = document.getElementById('pde-toast');
if (old) { old.remove(); }
var box = document.createElement('div');
box.id = 'pde-toast';
box.setAttribute('role', 'status');
box.style.cssText = 'position:fixed;top:16px;right:16px;z-index:2147483647;max-width:420px;padding:12px 40px 12px 16px;' +
    'border-radius:8px;color:#fff;font:14px/1.4 Arial,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.25);background:' +
    (colors[arguments[1]] || colors.green);
box.textContent = 'ERP: ' + arguments[0];
var x = document.createElement('span');
x.textContent = '\u00d7';
x.style.cssText = 'position:absolute;top:6px;right:12px;cursor:pointer;font-size:20px';
x.onclick = function () { box.remove(); };
box.appendChild(x);
document.body.appendChild(box);
setTimeout(function () { if (box.parentNode) { box.remove(); } }, 12000);
"""

# Finds the next-page link of an ASP.NET GridView pager (Page$N) or a
# generic "Next" button, and clicks it. Returns false when there is none.
JS_CLICK_NEXT_PAGE = r"""
var t = document.querySelector('table[data-pde-grid="1"]');
if (!t) { return false; }
var current = 1;
var anchors = t.querySelectorAll('a[href*="Page$"]');
if (anchors.length) {
    // The current page is the plain number (not a link) in the pager row.
    var pagerRow = anchors[0].closest('tr');
    while (pagerRow && pagerRow.parentElement && pagerRow.parentElement.closest('tr')
           && t.contains(pagerRow.parentElement.closest('tr'))) {
        pagerRow = pagerRow.parentElement.closest('tr');
    }
    var spans = pagerRow ? pagerRow.querySelectorAll('span') : [];
    for (var i = 0; i < spans.length; i++) {
        var n = parseInt((spans[i].innerText || '').trim(), 10);
        if (!isNaN(n) && !spans[i].closest('a')) { current = n; break; }
    }
}
var target = null, forward = null;
for (var j = 0; j < anchors.length; j++) {
    var m = (anchors[j].getAttribute('href') || '').match(/Page\$(\w+)/);
    if (!m) { continue; }
    if (m[1] === String(current + 1) || m[1] === 'Next') { target = anchors[j]; break; }
    var num = parseInt(m[1], 10);
    if (!isNaN(num) && num > current && (anchors[j].innerText || '').trim() === '...') { forward = anchors[j]; }
}
target = target || forward;
if (!target) {
    var box = t.parentElement || document.body;
    var cands = box.querySelectorAll('a, button, input[type=button], input[type=submit], li');
    for (var k = 0; k < cands.length; k++) {
        var el = cands[k];
        var label = (el.innerText || el.value || '').trim();
        var cls = (el.className || '') + ' ' + ((el.parentElement && el.parentElement.className) || '');
        if (/^(next|›|»|>)$/i.test(label) && !/disabled/i.test(cls) && !el.disabled) { target = el; break; }
    }
}
if (!target) { return false; }
target.click();
return true;
"""


# ============================================================
# HELPERS
# ============================================================


def unique_headers(headers):
    """Blank headers become 'Column N'; repeated headers get ' 2', ' 3'."""
    seen = {}
    out = []
    for idx, header in enumerate(headers, start=1):
        header = re.sub(r"\s+", " ", header or "").strip() or f"Column {idx}"
        count = seen.get(header.lower(), 0) + 1
        seen[header.lower()] = count
        out.append(header if count == 1 else f"{header} {count}")
    return out


MAX_SPAN = 50


def expand_rows(raw_rows, group_widths=None):
    """Lay raw rows out on a grid, expanding rowspan/colspan.

    Each grid cell is (text, is_th, kind): kind "cell" for the cell itself,
    "colspan" for the extra columns it covers, "rowspan" for the rows below it.
    Single-cell rows with nothing carried down are titles or "no record" lines
    and are skipped.

    A cell holding a nested table (e.g. "BRL Lot Details") is spread over the
    sub-columns of its header group (``group_widths``: first column -> width)
    when the widths match; each sub-column gets the nested values joined with
    ", ". Otherwise the nested rows go into the one column as text.

    A header row is one made only of <th> cells. A rowspan started in a header
    row ends at the first data row: some portals (SCMS DC lots) give header
    cells a larger rowspan than the header has rows, which would otherwise
    push the first data row to the right."""
    group_widths = group_widths or {}
    pending = {}  # column -> [text, rows_left, is_th, from_header]
    grid = []
    for row in raw_rows:
        cells = list(row.get("cells") or [])
        is_header = bool(cells) and all(len(c) > 3 and c[3] for c in cells)
        if not is_header:
            pending = {c: p for c, p in pending.items() if not p[3]}
        if len(cells) <= 1 and not pending:
            continue
        expanded = {}
        col = 0
        while cells or any(c >= col for c in pending):
            if col in pending:
                text, left, is_th, from_header = pending[col]
                expanded[col] = (text, is_th, "rowspan")
                if left > 1:
                    pending[col] = [text, left - 1, is_th, from_header]
                else:
                    del pending[col]
                col += 1
                continue
            if not cells:
                col += 1  # gap before a column still carried down from above
                continue
            text, rowspan, colspan, is_th, nested = (list(cells.pop(0)) + [None])[:5]
            rowspan, colspan = _span(rowspan), _span(colspan)
            values = None
            if nested:
                width = max(len(r) for r in nested)
                if colspan == 1 and width > 1 and group_widths.get(col) == width:
                    colspan = width
                if colspan == width:
                    values = [
                        ", ".join(r[j] for r in nested if j < len(r) and r[j]) for j in range(width)
                    ]
                else:
                    text = " | ".join(" / ".join(v for v in r if v) for r in nested if any(r))
            for k in range(colspan):
                value = values[k] if values is not None else text
                kind = "cell" if values is not None or k == 0 else "colspan"
                expanded[col] = (value, bool(is_th), kind)
                if rowspan > 1:
                    pending[col] = [value, rowspan - 1, bool(is_th), is_header]
                col += 1
        width = max(expanded) + 1 if expanded else 0
        grid.append((row, [expanded.get(i, ("", False, "gap")) for i in range(width)]))
    return grid


def _span(value):
    try:
        return min(max(int(value or 1), 1), MAX_SPAN)
    except (TypeError, ValueError):
        return 1


def grid_to_table(raw_rows):
    """Headers and data rows of a raw table (see JS_READ_GRID).

    Header rows are the leading rows made only of <th> cells (or the first row
    when the table has no <th>). A two-level header gives names such as
    "Receipt - No Of Bag". Data cells covered by a rowspan repeat the value, so
    every lot line is complete; cells covered by a colspan stay blank."""
    grid = expand_rows(raw_rows)
    if not grid:
        return [], []

    header_rows = 0
    for _row, cells in grid:
        real = [c for c in cells if c[2] != "gap"]
        if real and all(c[1] for c in real):
            header_rows += 1
        else:
            break
    if header_rows == 0:
        header_rows = 1
    header_rows = min(header_rows, max(len(grid) - 1, 1))

    # Header groups (a top header cell spanning sub-columns) tell where a nested
    # table in a data cell should be spread; lay the rows out again with them.
    group_widths = {}
    top = grid[0][1]
    i = 0
    while i < len(top):
        j = i + 1
        while j < len(top) and top[j][2] == "colspan":
            j += 1
        if j - i > 1:
            group_widths[i] = j - i
        i = j
    if group_widths and any(len(c) > 4 and c[4] for r in raw_rows for c in (r.get("cells") or [])):
        grid = expand_rows(raw_rows, group_widths)
    width = max(len(cells) for _row, cells in grid)

    headers = []
    for i in range(width):
        parts = []
        for _row, cells in grid[:header_rows]:
            text = cells[i][0] if i < len(cells) else ""
            if text and text not in parts:
                parts.append(text)
        headers.append(" - ".join(parts))

    data = []
    for row, cells in grid[header_rows:]:
        values = [c[0] if c[2] in ("cell", "rowspan") else "" for c in cells]
        values += [""] * (width - len(values))
        if any(values):
            data.append({"cells": values, "links": row.get("links") or []})
    return unique_headers(headers), data


TOTAL_CELL = re.compile(r"^(grand |sub ?)?total\s*:?$", re.IGNORECASE)


def split_total_rows(rows):
    """(record rows, footer rows): footer lines such as "Total" are a sum, not a record."""
    records, totals = [], []
    for row in rows:
        is_total = any(TOTAL_CELL.match((v or "").strip()) for v in row.get("cells") or [])
        (totals if is_total else records).append(row)
    return records, totals


def rows_to_cells(headers, rows):
    """Turn [cells...] lists into {header: value} maps; extra cells get their own column."""
    result = []
    for row in rows:
        values = row.get("cells") or []
        cells = {}
        for idx, value in enumerate(values):
            header = headers[idx] if idx < len(headers) else f"Column {idx + 1}"
            cells[header] = value
        result.append(cells)
    return result


def pick_receipt_link(links, skip_label="", wanted_label=""):
    """The row link most likely to be the receipt, or None. ``skip_label`` is the
    detail link (e.g. "View"), which opens a table, not a receipt. ``wanted_label``
    (the section's Receipt Link Text) picks the button whose label or id contains it."""
    if wanted_label:
        # Letters and digits only: the setting "AC Note Doc" must find the DCRO column "Acnote Doc".
        wanted = _key(wanted_label)
        # The column header first ("AC Note Doc" holds a plain "Download" button), then the button text.
        for link in links or []:
            if wanted in _key(link.get("column")):
                return link
        for link in links or []:
            if wanted in _key(link.get("label")) or wanted in _key(link.get("text")):
                return link
        return None
    for link in links or []:
        if skip_label and link_matches(link, skip_label):
            continue
        label = f"{link.get('text', '')} {link.get('raw_href', '')}"
        if SKIP_LINK_PATTERN.search(label):
            continue
        href = (link.get("href") or "").lower()
        if href.split("?")[0].endswith(".pdf") or RECEIPT_LINK_PATTERN.search(label):
            return link
    return None


def _key(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def document_steps(receipt_text):
    """The section's Receipt Link Text as [(button, print button)]. "Details > Print,
    AC Note Doc" -> two documents per row: click Details, then the Print button on
    the page that opens (the portal's real print format); and AC Note Doc as it comes.
    "> Print": the agent picks the row's print/view button itself (e.g. the SCMS
    Transit Challan eye icon), then clicks Print on the page that opens."""
    steps = []
    for part in (receipt_text or "").split(","):
        button, _, then = part.partition(">")
        if button.strip() or then.strip():
            steps.append((button.strip(), then.strip()))
    return steps


def document_labels(receipt_text):
    """Document names of the section's Receipt Link Text: "Details > Print, AC Note Doc" -> Details, AC Note Doc."""
    return [button for button, _then in document_steps(receipt_text)]


def row_tokens(cells):
    """The id-like values of a row (DC No., vehicle no., contract no., phone no.),
    lower case without spaces. Used to check that a document page belongs to
    this row. Dates, amounts and words are left out: other rows share them."""
    tokens = []
    for value in (cells or {}).values():
        value = re.sub(r"\s+", "", str(value or "")).lower()
        if len(value) < 6 or DATE_CELL.match(value) or not re.search(r"\d", value):
            continue
        if re.search(r"[a-z]", value) or (value.isdigit() and len(value) >= 8):
            if value not in tokens:
                tokens.append(value)
    return tokens


def page_matches_row(tokens, page_text):
    """True when more than half of the row's id values appear on the page (always
    True without ids). A document page shows the row's own DC, vehicle and
    contract; a page of another row shares only the depot and miller codes."""
    if not tokens:
        return True
    text = re.sub(r"\s+", "", page_text or "").lower()
    found = sum(1 for t in tokens if t in text)
    return found * 2 > len(tokens)


# Files kept from a row's document button, by their first bytes.
FILE_KINDS = ((b"%PDF", ".pdf"), (b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"))


def file_extension(content):
    """".pdf", ".png" or ".jpg" for a document the ERP keeps, else None."""
    for magic, ext in FILE_KINDS:
        if (content or b"").startswith(magic):
            return ext
    return None


def detail_link(links, label):
    """The row's detail button: by its label (e.g. "View"), else by its column
    header (WINGS TEC report: the button in the "Delivered" column)."""
    link = next((l for l in links or [] if link_matches(l, label)), None)
    if link:
        return link
    key = _key(label)
    return next((l for l in links or [] if key and key in _key(l.get("column"))), None)


def link_matches(link, label):
    return (link.get("label") or "").strip().lower() == (label or "").strip().lower()


def receipt_config_for(receipt_links, url, table_match=""):
    """(download?, button label) configured for the page at ``url``. On a page
    with several tables or tabs (e.g. LotSearch.aspx), an entry with a Table Match
    applies only to that table (``table_match``, see table_match_for), so the
    Lot Search "Print" setting is not used on the Rejected Lot tab."""
    url = (url or "").lower()
    fallback = (False, "")
    for item in receipt_links or []:
        match = (item.get("page_match") or "").strip().lower()
        if not match or match not in url:
            continue
        item_table = re.sub(r"[^a-z0-9]", "", (item.get("table_match") or "").lower())
        if not item_table:
            fallback = fallback if fallback[0] else (True, (item.get("link_text") or "").strip())
        elif item_table == table_match:
            return True, (item.get("link_text") or "").strip()
    return fallback


def table_match_for(grid_matches, url, page):
    """The Table Match of the table read, as the ERP decides it: the open tab
    first, then the table id, then the text above the table (which can be the
    whole tab bar, naming every tab). "" when none matches."""
    keys = grid_matches_for(grid_matches, url)
    for source in ("active_tab", "table_id", "table_title"):
        text = re.sub(r"[^a-z0-9]", "", ((page or {}).get(source) or "").lower())
        for key in keys:
            if key and text and key in text:
                return key
    # Last: the ids around the table, one by one (WINGS div#report_div / div#rept_div).
    ids = [re.sub(r"[^a-z0-9]", "", i.lower()) for i in ((page or {}).get("table_ids") or "").split()]
    for key in keys:
        if key and any(key in i for i in ids):
            return key
    return ""


def grid_matches_for(grid_matches, url):
    """"Table Match" texts (letters and digits, lower case) configured for the page at ``url``."""
    url = (url or "").lower()
    return [
        re.sub(r"[^a-z0-9]", "", (item.get("table_match") or "").lower())
        for item in grid_matches or []
        if (item.get("page_match") or "").strip().lower() in url and (item.get("page_match") or "").strip()
    ]


def open_read_for(open_reads, url):
    """True when the page at ``url`` is read as soon as it opens ("Read On Page Open", e.g. WINGS e_tec)."""
    url = (url or "").lower()
    return any((m or "").strip().lower() in url for m in open_reads or [] if (m or "").strip())


def mill_label_keys(labels):
    """The site's "Mill ID Labels" ("Mill ID, Miller Code") as [labels], [keys]."""
    labels = [t.strip() for t in re.split(r"[,\n]", labels or "") if t.strip()]
    return labels, [_key(t) for t in labels]


def click_triggers_for(click_triggers, url):
    """"Extract On Click" texts (letters and digits, lower case) configured for the page at ``url``."""
    url = (url or "").lower()
    out = []
    for item in click_triggers or []:
        match = (item.get("page_match") or "").strip().lower()
        if match and match in url:
            for text in str(item.get("triggers") or "").split(","):
                key = re.sub(r"[^a-z0-9]", "", text.lower())
                if key:
                    out.append(key)
    return out


def only_clicks_for(click_triggers, url):
    """True when the page at ``url`` is read only after its own "Extract On Click"
    buttons ("Only On These Clicks", e.g. DCRO DC Transit Challan: Show), not after
    any Search/Show/View-like click (such as the menu button that opened the page)."""
    url = (url or "").lower()
    return any(
        item.get("only") and (item.get("page_match") or "").strip().lower() in url
        for item in click_triggers or []
        if (item.get("page_match") or "").strip()
    )


def click_starts_read(marker, url, only=False):
    """Whether the click noted by JS_INSTALL_CLICK_HOOK ("time|kind|page path") starts
    a read on the page at ``url``. With ``only``, just an Extract On Click button
    ("t") clicked on this same page counts."""
    if not only:
        return True
    _ts, kind, path = (str(marker or "").split("|", 2) + ["", ""])[:3]
    return kind == "t" and bool(path) and path.lower() in (url or "").lower()


def waits_for_own_trigger(click_triggers, marker, url):
    """True when the page at ``url`` is read only after its own Extract On Click
    ("Only On These Clicks") and the click ``marker`` is not one of them, e.g. the menu
    click that opened DCRO DC Transit Challan, noticed while the old page was still shown."""
    return only_clicks_for(click_triggers, url) and not click_starts_read(marker, url, True)


PAGE_COLUMN = re.compile(r"^\s*([\w:.-]+)\s*\[\s*(\d+)\s*\]\s*$")


def page_columns(table_id):
    """``table_id`` as [(id, column)] when every part names a column, e.g.
    "grdDepotFCIbody[4], grdDepotRRCbody[4]" (DCRO View DC number of lots, like
    //*[@id="grdDepotFCIbody"]/tr/td[4]); else None (a whole table is read)."""
    parts = [p for p in (table_id or "").split(",") if p.strip()]
    found = [PAGE_COLUMN.match(p) for p in parts]
    if not parts or not all(found):
        return None
    return [(m.group(1), int(m.group(2))) for m in found]


def dc_type(element_id):
    """"FCI" / "RRC" from an id such as grdDepotFCIbody, else the id itself."""
    hit = re.search(r"FCI|RRC", element_id or "", re.IGNORECASE)
    return hit.group(0).upper() if hit else element_id


def lots_from_column(items, label="Lots"):
    """(detail rows, footer rows) from JS_READ_PAGE_COLUMNS: one detail row per lot
    {"DC Type", label}; a "Total" line goes to the footer."""
    lots, totals = [], []
    for item in items or []:
        value = (item.get("value") or "").strip()
        line = {"DC Type": dc_type(item.get("id")), label: value}
        if any(TOTAL_CELL.match((v or "").strip()) for v in item.get("row") or []):
            totals.append(line)
        elif value:
            lots.append(line)
    return lots, totals


def detail_config_for(detail_links, url):
    """(link text, detail table id) configured for the page at ``url``, or ("", "")."""
    url = (url or "").lower()
    for item in detail_links or []:
        match = (item.get("page_match") or "").strip().lower()
        if match and match in url:
            return (item.get("link_text") or "").strip(), (item.get("table_id") or "").strip()
    return "", ""


DATE_CELL = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})")


def date_column(rows):
    """The first column where most cells are dd/mm/yyyy (or dd-mm-yyyy) dates, or None."""
    if not rows:
        return None
    for header in rows[0]:
        dated = sum(1 for r in rows if DATE_CELL.match(str(r.get(header) or "").strip()))
        if dated >= len(rows) * 0.8:
            return header
    return None


def oldest_first(rows):
    """True when the table lists older dates first, so the newest rows are on the last pages."""
    header = date_column(rows)
    if not header:
        return False
    dates = []
    for r in rows:
        m = DATE_CELL.match(str(r.get(header) or "").strip())
        if m:
            dates.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    return len(dates) > 1 and dates[-1] > dates[0]


# Columns that change without the row changing (serial numbers, button columns):
# left out of a row's fingerprint. Same list as NOISE_HEADER in the ERP (portal_sync.py).
NOISE_HEADER = re.compile(
    r"^(s\.? ?no\.?|sl\.? ?(no\.?|#)?|sr\.? ?no\.?|serial( no\.?)?|#|column \d+|action|actions|print)$",
    re.IGNORECASE,
)


def row_signature(cells):
    """Fingerprint of a row's values (serial number and button columns left out).
    The ERP keeps it on each record; a row with a known fingerprint is already saved, unchanged."""
    items = sorted(
        (_squash(h), _squash(v)) for h, v in (cells or {}).items() if not NOISE_HEADER.match(_squash(h))
    )
    return hashlib.sha1(json.dumps(items, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def newest_first(rows):
    """True when the table lists newer dates first, so the rows below a saved one are older."""
    header = date_column(rows)
    if not header:
        return False
    dates = []
    for r in rows:
        m = DATE_CELL.match(str(r.get(header) or "").strip())
        if m:
            dates.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    return len(dates) > 1 and dates[0] > dates[-1]


def known_rows_for(known_rows, url, table_match=""):
    """Fingerprints of rows already in the ERP for the table read (section by page and
    Table Match), or None when the section reads every row ("Read Only New Rows" off)."""
    url = (url or "").lower()
    fallback = None
    for item in known_rows or []:
        match = (item.get("page_match") or "").strip().lower()
        if not match or match not in url:
            continue
        item_table = re.sub(r"[^a-z0-9]", "", (item.get("table_match") or "").lower())
        if item_table and item_table == table_match:
            return set(item.get("sigs") or [])
        if not item_table and fallback is None:
            fallback = set(item.get("sigs") or [])
    return fallback


def _int(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _squash(text):
    return re.sub(r"\s+", " ", text or "").strip()


def page_signature(text):
    return hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()


class PortalLoggedOut(Exception):
    """The portal answered with its login page: the user's session has ended."""


def looks_like_login(html, url=""):
    """True for the portal's login page (password box plus a login/captcha form)."""
    text = (html or "")[:200000].lower()
    has_password = bool(re.search(r"<input[^>]+type=[\"']?password", text))
    return has_password and ("login" in (url or "").lower() or "captcha" in text or "login" in text)


# ============================================================
# PORTAL SESSION
# ============================================================


class PortalSession:
    def __init__(self, config, base_folder):
        self.token = secrets.token_urlsafe(24)
        self.site = config.get("site") or ""
        self.login_url = config["login_url"]
        self.download_receipts = bool(config.get("download_receipts"))
        self.detail_links = config.get("detail_links") or []
        self.receipt_links = config.get("receipt_links") or []
        self.grid_matches = config.get("grid_matches") or []
        self.click_triggers = config.get("click_triggers") or []
        # Pages read as soon as they open, without a Search click (e.g. WINGS e_tec).
        self.open_reads = config.get("open_reads") or []
        # Rows already in the ERP, per section: only new or changed rows are read (see _read_all_pages).
        self.known_rows = config.get("known_rows") or []
        self._skipped_known = 0
        self._opened_key = ""
        # The logged-in mill (dashboard or page), sent with every result (see JS_FIND_MILL_ID).
        self.mill_labels, self.mill_keys = mill_label_keys(
            config.get("mill_id_labels") or "Mill ID, Mill Code, Miller Code, Miller ID"
        )
        self.mill_xpath = (config.get("mill_id_xpath") or "").strip()
        self.mill_id = ""
        self._landing_url, self._mill_tries = "", 0
        self.toasts = []  # messages to show in Chrome; shown by the agent's own thread
        self._only_table = None
        self.result_ids = []
        # "Rows to Save" on the ERP form (0 = all): stop paging once enough newest rows are read.
        self.row_limit = _int(config.get("row_limit"))
        # Close Session asked to keep what was read: stop reading and hand over the rows so far.
        self.finish_event = threading.Event()
        self._stopped_at_limit = False
        self._grid_header = None
        self._detail_table_id = ""
        # Table read on a row's document page before it is printed (e.g. the DC lots
        # of DCRO View DC, grdDepotFCIbody): a Detail Table ID with no Detail Link Text.
        self._page_table_id = ""
        self._page_table = None

        self.download_dir = os.path.join(base_folder, "Portal_Downloads", uuid.uuid4().hex[:12])
        # Pages where an Action button gave no document, kept to see what the portal showed.
        # Next to the installed exe: a one-file exe's own folder is deleted when it exits.
        keep_folder = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else base_folder
        self.debug_dir = os.path.join(keep_folder, "Portal_Debug")
        self._session_lost = False
        os.makedirs(self.download_dir, exist_ok=True)

        self.state = "starting"
        self.message = "Opening Chrome..."
        self.results = {}
        self.latest_result_id = None
        self.extract_requested = False
        self._read_click = ""
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.driver = None
        self.thread = None

    # ---------------- public ----------------

    def start(self):
        options = Options()
        options.add_argument("--start-maximized")
        # A page's own Print button (window.print) saves a PDF in the download
        # folder with no dialog, e.g. the DCRO Transit Challan in its print format.
        # This Chrome uses a fresh profile, so "Save as PDF" is always the printer.
        options.add_argument("--kiosk-printing")
        print_to_pdf = {
            "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
            "selectedDestinationId": "Save as PDF",
            "isCssBackgroundEnabled": True,
            "version": 2,
        }
        options.add_experimental_option(
            "prefs",
            {
                "printing.print_preview_sticky_settings.appState": json.dumps(print_to_pdf),
                "savefile.default_directory": self.download_dir,
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
                # Without this Chrome blocks every receipt after the first one
                # ("site tried to download multiple files").
                "profile.default_content_setting_values.automatic_downloads": 1,
            },
        )
        # close_fds: stop chromedriver inheriting (and blocking) port 8765 on Windows.
        self.driver = webdriver.Chrome(options=options, service=Service(popen_kw={"close_fds": True}))
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def status(self):
        with self.lock:
            latest = self.results.get(self.latest_result_id) if self.latest_result_id else None
            return {
                "state": self.state,
                "message": self.message,
                "site": self.site,
                "result_id": self.latest_result_id or "",
                # Every result in order: one Search can give several (one per table of the page).
                "result_ids": list(self.result_ids),
                "mill_id": self.mill_id,
                "rows": len(latest["rows"]) if latest else 0,
                "pages": latest["pages"] if latest else 0,
            }

    def request_extract(self):
        self.extract_requested = True

    def set_row_limit(self, limit):
        self.row_limit = _int(limit)

    def notify(self, message, color="green"):
        """Show a message in the portal page (called by the ERP after a save)."""
        if message:
            with self.lock:
                self.toasts.append((message, color))

    def _show_toasts(self):
        with self.lock:
            toasts, self.toasts = self.toasts, []
        for message, color in toasts:
            try:
                self.driver.execute_script(JS_TOAST, message, color)
            except Exception:
                pass

    def request_finish(self):
        """Stop the read in progress; the rows read so far become the result."""
        self.finish_event.set()

    def get_result(self, result_id, offset=0, limit=50):
        with self.lock:
            result = self.results.get(result_id)
        if not result:
            return None
        chunk = result["rows"][offset : offset + limit]
        return {
            "result_id": result_id,
            "columns": result["columns"],
            "pages": result["pages"],
            "page_url": result["page"].get("url", ""),
            "page_title": result["page"].get("title", ""),
            "page_heading": result["page"].get("heading", ""),
            "table_id": result["page"].get("table_id", ""),
            "table_title": result["page"].get("table_title", ""),
            "table_ids": result["page"].get("table_ids", ""),
            "active_tab": result["page"].get("active_tab", ""),
            "mill_id": result.get("mill_id", ""),
            # Search filters on the page ([{label, id, value}]); the ERP keeps the ones it needs (KMS Year, Depot).
            "page_filters": result["page"].get("filters") or [],
            "total": len(result["rows"]),
            "offset": offset,
            "rows": [
                {
                    "cells": row["cells"],
                    "has_receipt": bool(row.get("receipt_path")),
                    # Several documents per row: [{label, has_file, error}]; fetched with /portal/receipt?doc=N.
                    "documents": [
                        {"label": d["label"], "has_file": bool(d.get("path")), "error": d.get("error") or ""}
                        for d in row.get("documents") or []
                    ],
                    "receipt_error": row.get("receipt_error") or "",
                    "receipt_source": row.get("receipt_source") or "",
                    "details": row.get("details"),
                    "details_footer": row.get("details_footer") or [],
                    "detail_error": row.get("detail_error") or "",
                    # Fingerprint (kept by the ERP) and place on the portal (rows already saved are not sent).
                    "row_sig": row.get("row_sig") or "",
                    "position": row.get("position") or 0,
                }
                for row in chunk
            ],
        }

    def get_receipt(self, result_id, row_index, doc_index=None):
        """The row's receipt, or with ``doc_index`` its document N (see "documents")."""
        with self.lock:
            result = self.results.get(result_id)
        if not result or not (0 <= row_index < len(result["rows"])):
            return None
        row = result["rows"][row_index]
        source = row.get("receipt_source") or ""
        path = row.get("receipt_path")
        if doc_index is not None:
            docs = row.get("documents") or []
            if not (0 <= doc_index < len(docs)):
                return None
            path, source = docs[doc_index].get("path"), docs[doc_index].get("source") or ""
        if not path or not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            content = f.read()
        return {
            "filename": os.path.basename(path),
            "content_b64": base64.b64encode(content).decode(),
            "source_url": source,
        }

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self._quit_driver()
        shutil.rmtree(self.download_dir, ignore_errors=True)

    # ---------------- main loop ----------------

    def _set(self, state, message):
        with self.lock:
            self.state = state
            self.message = message
        print(f"[portal:{self.site}] {state}: {message}")

    def _run(self):
        try:
            self.driver.get(self.login_url)
            self._set("waiting_login", f"Please log in to {self.site} in the Chrome window.")
            self._login_page_url = self.driver.current_url
            self._last_click = self._click_marker()

            while not self.stop_event.is_set():
                try:
                    self._tick()
                except UnexpectedAlertPresentException as e:
                    # Portals often answer a Search with alert("No record found").
                    text = getattr(e, "alert_text", None) or "a pop-up message"
                    self._dismiss_alert()
                    self._set("watching", f"Portal says: {text}")
                except Exception as e:
                    if self.stop_event.is_set():
                        break
                    if not self._browser_alive():
                        self._set("closed", "Chrome was closed.")
                        return
                    self._set("watching", f"Agent warning: {str(e)[:200]}")
                    time.sleep(POLL_SECONDS)
        except Exception as e:
            if not self.stop_event.is_set():
                self._set("error", f"Agent error: {str(e)[:200]}")
        finally:
            if self.stop_event.is_set():
                self._quit_driver()

    def _tick(self):
        driver = self.driver
        if not self._browser_alive():
            self._set("closed", "Chrome was closed.")
            self.stop_event.set()
            return

        login = driver.execute_script(JS_LOGIN_STATE) or {}
        logged_in = not login.get("password") and (
            driver.current_url != self._login_page_url or login.get("logout")
        )
        if not logged_in:
            if self.state != "waiting_login":
                self._set("waiting_login", f"Please log in to {self.site} in the Chrome window.")
            time.sleep(POLL_SECONDS)
            return

        if self.state == "waiting_login":
            # The agent never opens pages itself: deep links end the portal session.
            self._wait_ready(PAGE_WAIT_SECONDS)
            self._landing_url, self._mill_tries = driver.current_url, 0
            self._read_mill_id(from_dashboard=True)
            self._say_logged_in()
        elif self.mill_xpath and not self.mill_id and driver.current_url == self._landing_url and self._mill_tries < 20:
            # The dashboard may fill in after it loads: keep looking while it is open.
            self._read_mill_id(from_dashboard=True)
            if self.mill_id:
                self._say_logged_in()

        self._show_toasts()
        click = self._click_marker()
        if click and click != self._last_click and not self.extract_requested:
            self._last_click = click
            if waits_for_own_trigger(self.click_triggers, click, driver.current_url):
                # e.g. the menu button or Show on DC Transit Challan: wait for the search box + Enter.
                self._say_waiting_for_trigger()
                return
            self._read_click = click
            self.extract_requested = True
        if self.extract_requested:
            self._last_click = click
            self.extract_requested = False
            # The click that started it ("" for Extract Now from the ERP).
            read_click, self._read_click = self._read_click, ""
            self._extract_after_search(click=read_click)
            return

        if open_read_for(self.open_reads, driver.current_url):
            key = driver.execute_script(JS_DOC_KEY)
            if key and key != self._opened_key:
                self._opened_key = key
                self._extract_after_search(trigger="Page opened")
                return

        time.sleep(POLL_SECONDS)

    def _say_waiting_for_trigger(self):
        self._set(
            "watching",
            "Not read yet. Set the filters, then use the trigger set for this page "
            "(e.g. type in the table's Search box and press Enter).",
        )

    def _say_logged_in(self):
        mill = f" Mill ID: {self.mill_id}." if self.mill_id else " Mill ID not found on the dashboard yet."
        self._set("watching", f"Logged in.{mill} Open any page from the portal menu, set filters and click Search.")

    def _click_marker(self):
        triggers = click_triggers_for(self.click_triggers, self.driver.current_url)
        return self.driver.execute_script(JS_INSTALL_CLICK_HOOK, triggers) or ""

    def _dismiss_alert(self):
        try:
            self.driver.switch_to.alert.dismiss()
        except Exception:
            pass

    def _browser_alive(self):
        try:
            return bool(self.driver.window_handles)
        except Exception:
            return False

    def _quit_driver(self):
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    # ---------------- extraction ----------------

    def _wait_ready(self, timeout):
        end = time.time() + timeout
        while time.time() < end and not self.stop_event.is_set():
            try:
                if self.driver.execute_script(JS_PAGE_READY):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _wait_for_grid(self, timeout, previous_signature=None):
        """Wait until a result table is present and stable (and different from before)."""
        end = time.time() + timeout
        last = None
        while time.time() < end and not self.stop_event.is_set():
            if self._wait_ready(5):
                text = self._find_grid()
                if text is not None:
                    signature = page_signature(text)
                    if signature != previous_signature and signature == last:
                        return signature
                    last = signature
            time.sleep(0.7)
        return None

    def _find_grid(self):
        """Mark the result table. Once its header is known, only that table counts,
        so an open detail panel is never mistaken for it."""
        if self._only_table:
            return self.driver.execute_script(JS_FIND_GRID, self._grid_header or None, [self._only_table], True)
        matches = grid_matches_for(self.grid_matches, self.driver.current_url)
        return self.driver.execute_script(JS_FIND_GRID, self._grid_header or None, matches)

    def _read_mill_id(self, from_dashboard=False):
        """Keep the mill of the session. With the site's Mill ID XPath it is read only
        from that element on the landing dashboard, then kept (other pages have other
        layouts); a Mill ID Label inside it picks the value (WINGS: "State Code").
        Without an XPath, from labels on the dashboard or the page read."""
        if self.mill_xpath:
            if not from_dashboard or self.mill_id:
                return
            try:
                found = self.driver.execute_script(JS_FIND_MILL_ID, [], self.mill_labels, self.mill_xpath) or ""
            except Exception:
                found = ""
        else:
            try:
                found = self.driver.execute_script(JS_FIND_MILL_ID, self.mill_keys, self.mill_labels, "") or ""
            except Exception:
                found = ""
        if found:
            self.mill_id = found
        elif from_dashboard:
            self._mill_tries = getattr(self, "_mill_tries", 0) + 1
            if self._mill_tries in (1, 20):
                # Kept so the site's Mill ID XPath / Labels can be checked against what the dashboard shows.
                self._save_debug_reply("dashboard", self.driver.page_source)

    def _extract_after_search(self, trigger="Search", click=""):
        self._grid_header = None
        self._only_table = None
        self._set("extracting", f"{trigger} detected. Waiting for the result table...")
        signature = self._wait_for_grid(RESULT_WAIT_SECONDS)
        if not signature:
            self._set("watching", f"No result table found after {trigger}. Click Search again on the portal page.")
            return
        if click and waits_for_own_trigger(self.click_triggers, click, self.driver.current_url):
            # The click was on the page before (e.g. the menu item); while the agent waited,
            # a page that waits for its own trigger opened and Show filled its table.
            self._say_waiting_for_trigger()
            return
        self._read_mill_id()
        self.finish_event.clear()

        # A page with several configured tables (e.g. WINGS e_tec: Booking / Delivery Status
        # and Targets / Advanced Paddy) gives one result per table; each table is read once.
        keys = grid_matches_for(self.grid_matches, self.driver.current_url)
        notes, read = [], set()
        results_before = len(self.result_ids)
        for key in keys if len(keys) > 1 else [None]:
            if self.finish_event.is_set() or self.stop_event.is_set():
                break  # Close Session: keep the tables read so far
            self._only_table, self._grid_header = key, None
            if key:
                if self._find_grid() is None:
                    continue
                uid = self.driver.execute_script(
                    "var t = document.querySelector('table[data-pde-grid=\"1\"]');"
                    "if (!t.getAttribute('data-pde-uid')) { t.setAttribute('data-pde-uid', String(Math.random())); }"
                    "return t.getAttribute('data-pde-uid');"
                )
                if uid in read:
                    continue
                read.add(uid)
                signature = self._wait_for_grid(PAGE_WAIT_SECONDS) or signature
            note = self._read_table(signature)
            if note:
                notes.append(note)
        self._only_table = None

        if not notes:
            self._set("watching", "The result table is empty. Change the filters and click Search again.")
            return
        if len(self.result_ids) == results_before:
            # Every row is already in the ERP: nothing to send.
            self._set("watching", " ".join(notes) + " Open another page or Search again.")
            toast = (" ".join(notes) + " Nothing new to save.", "green")
        else:
            self._set("ready", " ".join(notes) + " Sending to ERP...")
            toast = (" ".join(notes) + " Saving to ERP...", "blue")
        try:
            self.driver.execute_script(JS_TOAST, *toast)
        except Exception:
            pass

    def _read_table(self, signature):
        """Read the marked table (all its pages) into a new result. Returns a note, or "" when empty."""
        if self.driver.execute_script(JS_SHOW_ALL_DATATABLE):
            signature = self._wait_for_grid(PAGE_WAIT_SECONDS) or signature

        self._find_grid()
        self._grid_header = self.driver.execute_script(JS_GRID_HEADER)
        detail_text, self._detail_table_id = detail_config_for(self.detail_links, self.driver.current_url)
        self._page_table_id = "" if detail_text else self._detail_table_id

        try:
            page = self.driver.execute_script(JS_PAGE_INFO) or {}
        except Exception:
            page = {}
        table_match = table_match_for(self.grid_matches, self.driver.current_url, page)
        section_receipts, receipt_text = receipt_config_for(self.receipt_links, self.driver.current_url, table_match)
        known = known_rows_for(self.known_rows, self.driver.current_url, table_match)

        self._session_lost = False
        self.driver.execute_script(JS_SET_BUSY, True)
        try:
            columns, rows, pages = self._read_all_pages(
                signature, detail_text, self.download_receipts or section_receipts, receipt_text, section_receipts, known
            )
        finally:
            try:
                self.driver.execute_script(JS_SET_BUSY, False)
            except Exception:
                pass

        if not rows:
            if self._skipped_known:
                return f"No new rows: all {self._skipped_known} row(s) read are already in the ERP."
            return ""

        result_id = uuid.uuid4().hex[:12]
        with self.lock:
            self.results[result_id] = {
                "columns": columns, "rows": rows, "pages": pages, "page": page, "mill_id": self.mill_id,
            }
            for old in list(self.results)[:-KEEP_RESULTS]:
                self.results.pop(old, None)
            self.latest_result_id = result_id
            self.result_ids = [r for r in self.result_ids if r in self.results] + [result_id]
        receipts = sum(1 for r in rows if r.get("receipt_path")) + sum(
            1 for r in rows for d in r.get("documents") or [] if d.get("path")
        )
        details = sum(len(r.get("details") or []) for r in rows)
        detail_note = f", {details} detail row(s)" if detail_text or self._page_table_id else ""
        stop_note = (
            " Stopped early by Close Session."
            if self.finish_event.is_set()
            else (f" Stopped after the newest {self.row_limit} row(s) (Rows to Save)." if self._stopped_at_limit else "")
        )
        lost_note = (
            " The portal ended the login while saving documents; log in again and Search for the rest."
            if self._session_lost
            else ""
        )
        known_note = (
            f" {self._skipped_known} row(s) already in the ERP skipped"
            + (" (stopped at the first one: newer rows come first)." if self._stopped_at_known else ".")
            if self._skipped_known
            else ""
        )
        return f"Extracted {len(rows)} new/changed rows from {pages} page(s), {receipts} receipt(s){detail_note}.{known_note}{stop_note}{lost_note}"

    def _read_all_pages(
        self, signature, detail_text="", receipts=False, receipt_text="", receipt_required=False, known=None
    ):
        """Read every page of the marked table. With ``known`` (fingerprints of rows
        already in the ERP) only new or changed rows are kept: a known row gets no
        details or documents and is not sent. When the table lists newest dates first,
        reading stops at the first known row (all below it are older and saved)."""
        columns = None
        rows = []
        seen = {signature}
        pages = 0
        position = 0
        order_newest = None
        self._stopped_at_limit = False
        self._stopped_at_known = False
        self._skipped_known = 0

        while pages < MAX_PAGES and not self.stop_event.is_set() and not self.finish_event.is_set():
            pages += 1
            self._set("extracting", f"Reading page {pages} ({len(rows)} rows so far)...")
            self._find_grid()
            grid = self.driver.execute_script(JS_READ_GRID)
            if not grid:
                break

            headers, data = grid_to_table(grid["rows"])
            if columns is None:
                columns = headers
            page_cells = rows_to_cells(columns, data)

            for raw in data:
                for link in raw.get("links") or []:
                    col = link.get("col")
                    link["column"] = columns[col] if isinstance(col, int) and col < len(columns) else ""

            if known and order_newest is None:
                order_newest = newest_first(page_cells)
            for idx, (cells, raw) in enumerate(zip(page_cells, data)):
                if self.finish_event.is_set():
                    break
                position += 1
                row = {"cells": cells, "row_sig": row_signature(cells), "position": position}
                if known and row["row_sig"] in known:
                    self._skipped_known += 1
                    if order_newest:
                        self._stopped_at_known = True
                        break
                    continue
                if detail_text:
                    self._set(
                        "extracting",
                        f"Page {pages}: opening '{detail_text}' for row {idx + 1} of {len(page_cells)}...",
                    )
                    self._collect_details(row, raw.get("links"), detail_text, row_tokens(cells))
                if receipts and self._session_lost:
                    row["receipt_error"] = "not saved: the portal ended the login earlier in this run"
                elif receipts and len(document_steps(receipt_text)) > 1:
                    # Several documents per row (e.g. DCRO DC Transit Challan: Details > Print, AC Note Doc).
                    row["documents"] = []
                    for n, (label, print_text) in enumerate(document_steps(receipt_text), start=1):
                        if self._session_lost:
                            row["documents"].append({"label": label, "error": "not saved: the portal ended the login"})
                            continue
                        self._set(
                            "extracting",
                            f"Page {pages}: saving '{label}' of row {idx + 1} of {len(page_cells)}...",
                        )
                        got = {}
                        self._collect_receipt(
                            got, raw.get("links"), f"p{pages}_r{idx + 1}_d{n}", detail_text, label,
                            receipt_required, print_text, row_tokens(cells),
                        )
                        row["documents"].append(
                            {
                                "label": label,
                                "path": got.get("receipt_path"),
                                "source": got.get("receipt_source") or "",
                                "error": got.get("receipt_error") or "",
                            }
                        )
                elif receipts:
                    self._set(
                        "extracting",
                        f"Page {pages}: saving document of row {idx + 1} of {len(page_cells)}...",
                    )
                    label, print_text = (document_steps(receipt_text) or [("", "")])[0]
                    self._collect_receipt(
                        row, raw.get("links"), f"p{pages}_r{idx + 1}", detail_text, label,
                        receipt_required, print_text, row_tokens(cells),
                    )
                rows.append(row)

            if self.finish_event.is_set() or self._stopped_at_known:
                break
            if self.row_limit and len(rows) >= self.row_limit and not oldest_first([r["cells"] for r in rows]):
                # Newest rows come first (or no dates): the rows needed are already read.
                self._stopped_at_limit = True
                break

            # Detail and receipt clicks may have re-rendered the grid; mark it again.
            self._find_grid()
            if not self.driver.execute_script(JS_CLICK_NEXT_PAGE):
                break
            signature = self._wait_for_grid(PAGE_WAIT_SECONDS, previous_signature=signature)
            if not signature or signature in seen:
                break
            seen.add(signature)

        return columns or [], rows, pages

    # ---------------- row details (e.g. DC Monitoring -> View -> lots) ----------------

    def _click_row_link(self, link, tokens=None):
        """Click a row's button (see JS_CLICK_ROW_LINK). The grid is marked again
        first, in case a postback, UpdatePanel or Back replaced it; a DataTable
        shows all rows again so a row past the first page can be found."""
        self._find_grid()
        self.driver.execute_script(JS_SHOW_ALL_DATATABLE)
        self.driver.execute_script(JS_READ_GRID)
        label = re.sub(r"\s+", "", link.get("label") or "").lower()
        result = self.driver.execute_script(
            JS_CLICK_ROW_LINK, link["ref"], tokens or [], link.get("col"), label
        )
        return result in ("ok", "moved")

    def _collect_details(self, row, links, detail_text, tokens=None):
        link = detail_link(links, detail_text)
        if not link:
            return
        try:
            try:
                row["details"], row["details_footer"] = self._open_detail(link["ref"], self._detail_table_id)
            except (UnexpectedAlertPresentException, PortalLoggedOut):
                raise
            except Exception:
                # The button runs a script (e.g. a WINGS pop-up loaded by AJAX): click it like a user.
                row["details"], row["details_footer"] = self._click_detail(link, self._detail_table_id, tokens)
        except UnexpectedAlertPresentException as e:
            # e.g. alert("No lot found") -> the DC simply has no lots.
            self._dismiss_alert()
            row["details"] = []
            row["detail_error"] = f"portal said: {getattr(e, 'alert_text', '') or 'no data'}"[:200]
        except Exception as e:
            row["detail_error"] = str(e)[:200]
        finally:
            self._restore_main_window()

    def _button_request(self, ref):
        """Replay the HTTP request a row button would send (see JS_BUTTON_REQUEST)."""
        self._find_grid()
        self.driver.execute_script(JS_READ_GRID)
        spec = self.driver.execute_script(JS_BUTTON_REQUEST, ref)
        if not spec:
            raise Exception("could not read the button on the page")

        session = self._http_session()
        session.headers["Referer"] = self.driver.current_url
        if spec.get("get_url"):
            response = session.get(spec["get_url"], timeout=60)
        elif spec["method"] == "get":
            response = session.get(spec["action"], params=spec["fields"], timeout=60)
        else:
            response = session.post(spec["action"], data=spec["fields"], timeout=60)
        response.raise_for_status()
        return response

    def _open_detail(self, ref, table_id=""):
        """Read the detail table (e.g. the lots of a DC) behind a row's View button.

        The request is replayed over HTTP, so the Chrome page keeps its result
        table and filters for the next row. The reply is read with Chrome's own
        HTML parser (in memory), taking the table with ``table_id`` when set."""
        response = self._button_request(ref)
        html = response.text
        table = self._read_detail_html(html, table_id)  # (rows, footer rows) or None

        if table is None:
            # The reply may only open the detail page in a pop-up window.
            popup = re.search(r"window\.open\(\s*['\"]([^'\"]+)['\"]", html)
            if popup:
                session = self._http_session()
                session.headers["Referer"] = response.url
                html = session.get(urljoin(response.url, popup.group(1)), timeout=60).text
                table = self._read_detail_html(html, table_id)

        if table is None:
            alert = re.search(r"alert\(\s*['\"]([^'\"]+)['\"]", html)
            if alert:
                raise UnexpectedAlertPresentException(alert_text=alert.group(1))
            raise Exception("no detail table in the portal's reply")
        return table

    def _click_detail(self, link, table_id="", tokens=None):
        """Click a row's detail button in Chrome and read the table it shows: in a
        pop-up or panel on this page (then closed), a new window (then closed),
        or this window moving to another page (then Back to the list)."""
        driver = self.driver
        main = driver.current_window_handle
        list_url = driver.current_url
        handles = set(driver.window_handles)
        driver.execute_script(JS_MARK_TABLES)
        if not self._click_row_link(link, tokens):
            raise Exception("the detail button of this row was not found on the page (the list changed)")

        end = time.time() + DETAIL_WAIT_SECONDS
        last, steady_since = None, None
        while time.time() < end and not self.stop_event.is_set():
            time.sleep(0.7)
            opened = set(driver.window_handles) - handles
            if opened:
                try:
                    driver.switch_to.window(opened.pop())
                    self._wait_ready(PAGE_WAIT_SECONDS)
                    self._check_not_login()
                    table = self._read_detail_html(driver.page_source, table_id)
                finally:
                    self._close_windows_except(handles, main)
                if table is None:
                    raise Exception("no detail table in the window that opened")
                return table
            if driver.current_url != list_url and self._wait_ready(2):
                try:
                    self._check_not_login()
                    table = self._read_detail_html(driver.page_source, table_id)
                finally:
                    self._back_to(list_url)
                if table is None:
                    raise Exception("no detail table on the page that opened")
                return table
            found = driver.execute_script(JS_READ_NEW_TABLE, table_id or "")
            if not found:
                last, steady_since = None, None
                continue
            if found["sig"] != last:
                last, steady_since = found["sig"], time.time()
                continue
            # Same text twice: loaded. A pop-up shown again with its old text waits longer:
            # the portal may still be loading this row's data into it.
            if found["changed"] or time.time() - steady_since >= 5:
                self._close_popup()
                table = self._detail_from_rows(found["rows"])
                if table is None:
                    raise Exception("the detail table is empty")
                return table

        self._close_popup()
        raise Exception("no detail table appeared after clicking the button")

    def _close_popup(self):
        try:
            if not self.driver.execute_script(JS_CLOSE_POPUP):
                self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass

    def _read_detail_html(self, html, table_id):
        parsed = self.driver.execute_script(JS_READ_DETAIL_HTML, html, table_id or "", self._grid_header or "")
        if not parsed:
            return None
        return self._detail_from_rows(parsed["rows"])

    def _detail_from_rows(self, raw_rows):
        headers, data = grid_to_table(raw_rows)
        if not data:
            return None
        records, totals = split_total_rows(data)
        return rows_to_cells(headers, records), rows_to_cells(headers, totals)

    # ---------------- receipts ----------------

    def _collect_receipt(
        self, row, links, label, skip_label="", wanted_label="", required=False, print_text="", tokens=None
    ):
        link = pick_receipt_link(links, skip_label, wanted_label)
        if not link:
            if required:
                # The section expects a document per row: say so instead of skipping quietly.
                found = ", ".join(l.get("label") or l.get("text") or "?" for l in links or []) or "none"
                row["receipt_error"] = f"no '{wanted_label or 'print/view'}' button in the row (buttons: {found})"[:200]
            return
        row["receipt_source"] = link.get("href") or link.get("raw_href") or link.get("text")
        self._page_table = None
        try:
            # The button is clicked like a user does (e.g. the eye icon of Transit
            # Challan). Replaying it in the background made the portal end the login.
            content = self._click_for_document(link, label, print_text, tokens)
            if not content:
                raise Exception("no PDF received")
            if len(content) > MAX_RECEIPT_BYTES:
                raise Exception("PDF is larger than 10 MB")
            ext = file_extension(content) or ".pdf"
            path = os.path.join(self.download_dir, f"receipt_{label}_{uuid.uuid4().hex[:6]}{ext}")
            with open(path, "wb") as f:
                f.write(content)
            row["receipt_path"] = path
        except PortalLoggedOut as e:
            self._session_lost = True
            row["receipt_error"] = str(e)[:200]
        except Exception as e:
            row["receipt_error"] = str(e)[:200]
        finally:
            self._restore_main_window()
            self._take_page_table(row)

    def _take_page_table(self, row):
        """Put the table read on the document page (see _read_page_table) into the
        row's details, e.g. the lots (Bags, Quantity) of a DCRO View DC row."""
        if not self._page_table_id or row.get("details") is not None:
            return
        table, self._page_table = self._page_table, None
        if isinstance(table, tuple):
            row["details"], row["details_footer"] = table
        elif table:
            row["detail_error"] = table[:200]

    def _read_page_table(self):
        """Read the configured table (``_page_table_id``) of the document page now shown,
        before Print is clicked. Only that table is taken, never a guessed one."""
        if not self._page_table_id or self._page_table is not None:
            return
        columns = page_columns(self._page_table_id)
        if columns:
            # The rows may be filled a moment after the page shows the DC: wait for them.
            items, end = None, time.time() + DETAIL_WAIT_SECONDS
            try:
                while True:
                    items = self.driver.execute_script(JS_READ_PAGE_COLUMNS, [list(c) for c in columns])
                    if items or time.time() > end or self.stop_event.is_set():
                        break
                    time.sleep(0.5)
            except Exception as e:
                self._page_table = f"'{self._page_table_id}' not read: {e}"
                return
            if items is None:
                self._save_debug_reply("lots", self.driver.page_source)
                self._page_table = f"none of '{self._page_table_id}' is on the page that opened (page saved in Portal_Debug)"
            else:
                self._page_table = lots_from_column(items)
            return
        try:
            parsed = self.driver.execute_script(
                JS_READ_DETAIL_HTML, self.driver.page_source, self._page_table_id, self._grid_header or "", True
            )
            table = self._detail_from_rows(parsed["rows"]) if parsed else None
            # (rows, footer rows), or why not as text; an empty table is a DC with no lots.
            self._page_table = table or (
                ([], []) if parsed else f"no table '{self._page_table_id}' on the document page"
            )
        except Exception as e:
            self._page_table = f"table '{self._page_table_id}' not read: {e}"

    def _http_session(self):
        session = requests.Session()
        for cookie in self.driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
        session.headers["User-Agent"] = self.driver.execute_script("return navigator.userAgent")
        return session

    def _click_for_document(self, link, label="", print_text="", tokens=None):
        """Click a row's document button in the user's Chrome and catch the result:
        a downloaded file (Chrome saves it to the download folder, no tab opens),
        a new window, or this window moving to the document. A page is checked
        to belong to the row (``tokens``, see row_tokens), then saved: with
        ``print_text`` by clicking that button on it (the portal's own print
        format), else printed as shown. Then back to the list."""
        driver = self.driver
        main = driver.current_window_handle
        list_url = driver.current_url
        handles = set(driver.window_handles)
        before = set(os.listdir(self.download_dir))

        if not self._click_row_link(link, tokens):
            raise Exception("the button of this row was not found on the page (the list changed)")

        end = time.time() + RECEIPT_WAIT_SECONDS
        while time.time() < end and not self.stop_event.is_set():
            time.sleep(0.5)
            try:
                content = self._new_download(before)
                if content is not None:
                    self._wait_for_grid(PAGE_WAIT_SECONDS)
                    return content

                opened = set(driver.window_handles) - handles
                if opened:
                    driver.switch_to.window(opened.pop())
                    try:
                        self._wait_ready(RECEIPT_WAIT_SECONDS)
                        # A file opened in a tab (e.g. AC Note Doc) leaves it blank while Chrome downloads it.
                        blank = not (driver.execute_script(JS_PAGE_TEXT) or "").strip()
                        content = self._wait_download(before, max(end - time.time(), 1) if blank else 1)
                        if content is not None:
                            return content
                        self._check_not_login()
                        return self._save_page(label, print_text, tokens, before)
                    finally:
                        self._close_windows_except(handles, main)

                if driver.current_url != list_url and self._wait_ready(2):
                    try:
                        self._check_not_login()
                        return self._save_page(label, print_text, tokens, before)
                    finally:
                        self._back_to(list_url)
            except NoSuchWindowException:
                # The tab closed itself (a download); the file is picked up on the next turn.
                self._close_windows_except(handles, main)
            except UnexpectedAlertPresentException as e:
                self._dismiss_alert()
                raise Exception(f"portal said: {getattr(e, 'alert_text', '') or 'no document'}")

        self._save_debug_reply(label, driver.page_source)
        raise Exception("nothing was downloaded or opened after the click (page saved in Portal_Debug)")

    def _save_page(self, label, print_text, tokens, before):
        """Save the document page shown in the current window, once it shows this row."""
        driver = self.driver
        end = time.time() + DETAIL_WAIT_SECONDS
        while not page_matches_row(tokens, driver.execute_script(JS_PAGE_TEXT)):
            if time.time() > end:
                self._save_debug_reply(label, driver.page_source)
                raise Exception(
                    "the page that opened is not for this row, so it was not saved (page saved in Portal_Debug)"
                )
            time.sleep(0.5)
        self._read_page_table()
        if not print_text:
            return self._print_current_page()
        return self._click_print(print_text, label, before)

    def _click_print(self, print_text, label, before):
        """Click the page's own Print button and catch its PDF: saved by Chrome
        (kiosk printing, see start), or a print window / page printed here."""
        driver = self.driver
        here = driver.current_window_handle
        url = driver.current_url
        handles = set(driver.window_handles)
        if not driver.execute_script(JS_CLICK_PRINT, _key(print_text)):
            self._save_debug_reply(label, driver.page_source)
            raise Exception(f"no '{print_text}' button on the page that opened (page saved in Portal_Debug)")

        end = time.time() + RECEIPT_WAIT_SECONDS
        while time.time() < end and not self.stop_event.is_set():
            time.sleep(0.5)
            content = self._new_download(before)
            if content is not None:
                return content
            opened = set(driver.window_handles) - handles
            if opened:
                try:
                    driver.switch_to.window(opened.pop())
                    self._wait_ready(RECEIPT_WAIT_SECONDS)
                    content = self._wait_download(before, 5)
                    if content is not None:
                        return content
                    self._check_not_login()
                    return self._print_current_page()
                except NoSuchWindowException:
                    continue  # the print window closed itself after printing; its PDF comes next turn
                finally:
                    self._close_windows_except(handles, here)
            if driver.current_url != url and self._wait_ready(2):
                content = self._wait_download(before, 5)
                if content is not None:
                    return content
                self._check_not_login()
                return self._print_current_page()

        self._save_debug_reply(label, driver.page_source)
        raise Exception(f"clicked '{print_text}' but no document came out (page saved in Portal_Debug)")

    def _wait_download(self, before, seconds):
        end = time.time() + seconds
        while True:
            content = self._new_download(before)
            if content is not None or time.time() > end or self.stop_event.is_set():
                return content
            time.sleep(0.5)

    def _close_windows_except(self, keep, back_to):
        """Close the windows opened since ``keep`` was noted, then switch to ``back_to``."""
        driver = self.driver
        for handle in set(driver.window_handles) - set(keep):
            try:
                driver.switch_to.window(handle)
                driver.close()
            except Exception:
                pass
        try:
            driver.switch_to.window(back_to)
        except Exception:
            self._restore_main_window()

    def _back_to(self, list_url):
        """Go Back until the list page shows again (a Print page may add a step)."""
        for _step in range(4):
            if self.driver.current_url == list_url:
                break
            self.driver.back()
            self._wait_ready(PAGE_WAIT_SECONDS)
        self._wait_for_grid(PAGE_WAIT_SECONDS)

    def _new_download(self, before):
        """Bytes of a finished new file in the download folder, or None. Only PDF and
        image files (e.g. a scanned AC Note) are kept; other files are refused."""
        done = [
            f for f in set(os.listdir(self.download_dir)) - before
            if not f.endswith((".crdownload", ".tmp"))
        ]
        if not done:
            return None
        path = os.path.join(self.download_dir, done[0])
        # Let Chrome finish writing (a printed PDF is written in place, not as .crdownload).
        size = -1
        for _try in range(20):
            time.sleep(0.3)
            now = os.path.getsize(path)
            if now and now == size:
                break
            size = now
        with open(path, "rb") as f:
            content = f.read()
        os.remove(path)
        if not file_extension(content):
            raise Exception(f"the downloaded file is not a PDF or image ({done[0]})")
        return content

    def _check_not_login(self):
        if looks_like_login(self.driver.page_source, self.driver.current_url):
            raise PortalLoggedOut("the portal ended the login (it showed its login page)")

    def _print_current_page(self):
        pdf = self.driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
        return base64.b64decode(pdf["data"])

    def _save_debug_reply(self, label, html):
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            names = sorted(os.listdir(self.debug_dir))
            for old in names[:-9]:  # keep the last 10
                os.remove(os.path.join(self.debug_dir, old))
            path = os.path.join(self.debug_dir, f"{time.strftime('%Y%m%d_%H%M%S')}_{label or 'row'}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html or "")
        except Exception:
            pass

    def _restore_main_window(self):
        try:
            handles = self.driver.window_handles
            if self.driver.current_window_handle not in handles:
                self.driver.switch_to.window(handles[0])
        except Exception:
            try:
                self.driver.switch_to.window(self.driver.window_handles[0])
            except Exception:
                pass


# ============================================================
# SESSION REGISTRY (one portal session at a time)
# ============================================================

_current = None
_registry_lock = threading.Lock()


def start_portal_session(config, base_folder):
    global _current
    if not config.get("login_url"):
        raise ValueError("login_url is required")
    with _registry_lock:
        if _current is not None:
            _current.close()
            _current = None
        session = PortalSession(config, base_folder)
        session.start()
        _current = session
        return session


def get_portal_session(token):
    session = _current
    if session is None or not token or not secrets.compare_digest(session.token, token):
        return None
    return session


def close_portal_session(token):
    global _current
    with _registry_lock:
        session = get_portal_session(token)
        if session is None:
            return False
        session.close()
        _current = None
        return True
