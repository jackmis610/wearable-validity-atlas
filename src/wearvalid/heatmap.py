"""Pure-Python SVG heatmap (no plotting dependencies).

Rows = claims, columns = devices, cells colored by grade. Kept dependency-free
so the whole pipeline runs anywhere and the output is fully auditable text.
"""

GRADE_COLOR = {
    "A": "#1a9850",  # green  - established valid
    "B": "#a6d96a",  # light green
    "C": "#dddddd",  # grey   - insufficient
    "D": "#fdae61",  # orange - marketed, unvalidated
    "F": "#d73027",  # red    - refuted
    "N": "#4d4d4d",  # dark   - not validatable
}
CELL_W, CELL_H = 132, 40
LABEL_W, HEAD_H = 210, 84
PAD = 12


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(verdicts, claims, devices):
    dev_ids = list(devices.keys())
    claim_ids = list(claims.keys())
    by_cell = {(v.device, v.claim): v for v in verdicts}

    w = LABEL_W + CELL_W * len(dev_ids) + PAD * 2
    h = HEAD_H + CELL_H * len(claim_ids) + PAD * 2
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'font-family="-apple-system,Segoe UI,Roboto,sans-serif">' % (w, h)]
    out.append('<rect width="%d" height="%d" fill="white"/>' % (w, h))
    out.append('<text x="%d" y="26" font-size="18" font-weight="700">'
               'Wearable Validity Matrix</text>' % PAD)

    # Column headers (device labels, rotated for compactness)
    for j, d in enumerate(dev_ids):
        cx = LABEL_W + j * CELL_W + CELL_W / 2 + PAD
        out.append('<text x="%d" y="%d" font-size="12" font-weight="600" '
                   'text-anchor="middle">%s</text>'
                   % (cx, HEAD_H - 6, _esc(devices[d]["label"])))

    # Rows
    for i, claim_id in enumerate(claim_ids):
        ry = HEAD_H + i * CELL_H + PAD
        out.append('<text x="%d" y="%d" font-size="12" text-anchor="end">%s</text>'
                   % (LABEL_W + PAD - 8, ry + CELL_H / 2 + 4,
                      _esc(claims[claim_id]["label"])))
        for j, d in enumerate(dev_ids):
            x = LABEL_W + j * CELL_W + PAD
            v = by_cell.get((d, claim_id))
            grade = v.grade if v else None
            fill = GRADE_COLOR.get(grade, "#f7f7f7")
            out.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" '
                       'stroke="white" stroke-width="2"/>'
                       % (x, ry, CELL_W, CELL_H, fill))
            if grade:
                txtcol = "white" if grade in ("A", "F", "N") else "#222"
                out.append('<text x="%d" y="%d" font-size="14" font-weight="700" '
                           'text-anchor="middle" fill="%s">%s</text>'
                           % (x + CELL_W / 2, ry + CELL_H / 2 + 5, txtcol, grade))
    out.append("</svg>")
    return "\n".join(out)
