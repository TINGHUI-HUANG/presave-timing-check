"""Draw the system diagram as SVG: docs/system_diagram.svg.

    py -3.11 tools/make_diagram.py

Boxes, arrows and short labels only. Solid boxes are implemented, dashed ones recorded or
simulated, dotted ones planned. Convert to PNG with: node tools/capture.mjs --diagram
"""
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
W, H = 940, 1030
P, C, D = (20, 220), (320, 320), (700, 220)          # x and width of the three columns
STYLE = {
    "impl": 'fill="#e7f0ff" stroke="#2f5fb3" stroke-width="1.6"',
    "sim": 'fill="#fff6e0" stroke="#b7791f" stroke-width="1.6" stroke-dasharray="7 4"',
    "plan": 'fill="#f3f3f3" stroke="#6b7280" stroke-width="1.6" stroke-dasharray="2 3"',
}
STATUS = {"impl": "Implemented", "sim": "Recorded / simulated", "plan": "Planned"}
out = []


def text(x, y, s, cls="d", anchor="start"):
    out.append(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{escape(s)}</text>')


def box(col, y, h, title, detail="", status="impl", note=None, badge=None):
    x, w = col
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" {STYLE[status]}/>')
    text(x + 10, y + 21, title, "t")
    for i, line in enumerate(detail.split("\n") if detail else []):
        text(x + 10, y + 39 + 16 * i, line)
    text(x + 10, y + h - 7, note or STATUS[status], "s")
    if badge:
        bw = 9 + 7 * len(badge)
        top = y + 7 if len(badge) <= 3 else y + h - 24     # long badges sit bottom right, clear of the title
        out.append(f'<rect x="{x + w - bw - 6}" y="{top}" width="{bw}" height="18" rx="9" fill="#6f42c1"/>')
        text(x + w - bw / 2 - 6, top + 13, badge, "badge", "middle")


def arrow(points, label=None, at=None, dotted=False, anchor="middle"):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    extra = ' stroke-dasharray="3 3"' if dotted else ""
    out.append(f'<path d="{d}" class="arrow"{extra} marker-end="url(#head)"/>')
    if label:
        text(at[0], at[1], label, "lab", anchor)


def build():
    gx = 280                                  # middle of the gutter between person and checker
    cx = C[0] + C[1] / 2                      # middle of the checker column
    cr, dl = C[0] + C[1], D[0]                # checker right edge, data left edge
    pr, cl = P[0] + P[1], C[0]                # person right edge, checker left edge
    for (x, w), title in [(P, "Person · web page"), (C, "Checker · Python (app.py, checker/)"), (D, "Model and data")]:
        out.append(f'<rect x="{x}" y="12" width="{w}" height="30" rx="6" fill="#f6f8fa" stroke="#d0d7de"/>')
        text(x + w / 2, 32, title, "h", "middle")

    # Person column
    box(P, 60, 66, "Types one sentence", "or picks an example chip")
    box(P, 150, 66, "Decline or error card", "no rule is created")
    box(P, 420, 66, "Question card", "scene · why · Yes/No/Not sure · Back")
    box(P, 510, 66, "Repair card", "Add / Don't add / Edit")
    box(P, 600, 66, "Confirm or choose card", "rule · never does · Revisit · Back")
    box(P, 690, 66, "Saved card", "saved in the prototype only")

    # Checker column
    box(C, 60, 66, "1  Assemble the context", "instruction v1 + the request, nothing else")
    box(C, 150, 66, "2  Check the reply", "shape · vocabulary · conflicts · ≤3 · merge twins")
    box(C, 240, 66, "3  Simulate", "every reading in every scenario")
    box(C, 330, 66, "4  Choose the next question", "differ → ask; last kept for a bug-class probe; ≤3",
        badge="decides when to ask")
    box(C, 420, 66, "5  Apply the answer", "keep matching readings; Not sure keeps all")
    box(C, 510, 66, "6  Propose a missing rule", "repair template of the probe scenario")
    box(C, 600, 66, "7  Restate and wait", "from the rule; Back/Revisit replay kept answers")
    box(C, 690, 66, "8  Save once", "once per session, even on a retried click")

    # Model and data column
    box(D, 60, 66, "Gemini (LLM)", "1–3 readings as JSON", note="Implemented · live, needs a key", badge="AI")
    box(D, 136, 48, "Recorded replies", status="sim", note="Recorded · replayed, no key")
    box(D, 192, 48, "Lab 3 hand-written", status="sim", note="Simulated · requests A and B")
    box(D, 252, 66, "Scenario library S1–S5", "one moment each; sunset 18:00")
    box(D, 420, 66, "Session log (JSONL)", "every step; who clicked")
    box(D, 690, 50, "Saved rules (local JSON)")
    box(D, 770, 50, "Home platform", status="plan", note="Planned · Google Home, Home Assistant")

    # Request and model call
    arrow([(pr, 93), (cl, 93)], "request", (gx, 84))
    arrow([(cr, 93), (dl, 93)], "context", ((cr + dl) / 2, 84))
    bus = dl - 12
    arrow([(dl, 115), (bus, 115), (bus, 183), (cr, 183)])
    arrow([(dl, 160), (bus, 160)])
    arrow([(dl, 216), (bus, 216), (bus, 183)])
    text((cr + bus) / 2, 176, "reply", "lab", "middle")
    arrow([(cl, 183), (pr, 183)])
    text(pr + 4, 233, "out of scope, unusable or no source", "lab")
    arrow([(cx, 216), (cx, 240)])
    arrow([(dl, 285), (cr, 285)], "scenarios", ((cr + dl) / 2, 278))
    arrow([(cx, 306), (cx, 330)], "outcomes", (cx + 6, 322), anchor="start")

    # Question loop
    arrow([(cl, 375), (gx, 375), (gx, 440), (pr, 440)], "question", (gx + 6, 412), anchor="start")
    arrow([(pr, 470), (cl, 470)], "answer", (gx, 500))
    arrow([(cr, 453), (cr + 12, 453), (cr + 12, 372), (cr, 372)])
    text(cr - 6, 412, "next", "lab", "end")
    arrow([(cx, 486), (cx, 510)], "no reading matches", (cx + 6, 502), anchor="start")
    arrow([(cl, 532), (pr, 532)], "proposal", (gx, 525))
    arrow([(pr, 560), (cl, 560)], "choice", (gx, 590))
    arrow([(cr, 543), (cr + 26, 543), (cr + 26, 360), (cr, 360)])
    arrow([(cr, 346), (cr + 40, 346), (cr + 40, 633), (cr, 633)], "nothing left", (cr + 46, 596), anchor="start")
    text(cr + 46, 611, "to ask", "lab")

    # Restate, save, log
    arrow([(cl, 633), (pr, 633)], "rule", (gx, 626))
    arrow([(pr, 655), (gx, 655), (gx, 723), (cl, 723)], "Save", (gx - 6, 692), anchor="end")
    arrow([(cl, 745), (pr, 745)], "saved", (gx, 768))
    arrow([(cr, 715), (dl, 715)], "rule", ((cr + dl) / 2, 708))
    arrow([(cr, 745), (dl - 10, 745), (dl - 10, 795), (dl, 795)], dotted=True)
    arrow([(12, 640), (12, 75), (20, 75)], dotted=True)
    out.append('<text class="lab" x="8" y="400" transform="rotate(-90 8 400)" text-anchor="middle">'
               'Back, Revisit, Edit or Try again return to an earlier step</text>')

    # Offline tools
    text(20, 852, "Offline tools (outside the interaction)", "h")
    for i, (title, detail, status) in enumerate([
            ("record_readings.py", "live replies → recordings\n+ automatic criteria check", "impl"),
            ("compare.py", "scripted person · 4 strategies\n· 1–3 questions (pilot)", "impl"),
            ("Phase 3 evaluation", "published study tasks;\nuser study", "plan"),
            ("Not built", "sunset from location · rule\neditor · more devices", "plan")]):
        box((20 + 230 * i, 210), 862, 84, title, detail, status)

    # Legend
    y = 982
    for i, (status, label) in enumerate([("impl", "Implemented"), ("sim", "Recorded or simulated"), ("plan", "Planned")]):
        x = 20 + 220 * i
        out.append(f'<rect x="{x}" y="{y}" width="34" height="18" rx="4" {STYLE[status]}/>')
        text(x + 42, y + 14, label)
    out.append(f'<rect x="690" y="{y}" width="30" height="18" rx="9" fill="#6f42c1"/>')
    text(705, y + 13, "AI", "badge", "middle")
    text(728, y + 14, "model inference")
    text(20, 1020, "Steps 4–7 implement the initiative rule: ask while readings differ or a bug class applies; "
                   "then propose and wait.", "s")


def main():
    build()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img"
  aria-label="System diagram of the pre-save timing check">
<defs>
  <marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="#444c56"/></marker>
  <style>
    text {{ font-family: "Segoe UI", Arial, Helvetica, sans-serif; fill: #1f2328; }}
    .h {{ font-size: 15px; font-weight: 700; fill: #3d444d; }}
    .t {{ font-size: 15px; font-weight: 700; }}
    .d {{ font-size: 13px; }}
    .s {{ font-size: 11.5px; font-style: italic; fill: #57606a; }}
    .lab {{ font-size: 12px; fill: #3d444d; }}
    .badge {{ font-size: 11px; font-weight: 700; fill: #ffffff; }}
    .arrow {{ stroke: #444c56; stroke-width: 1.5; fill: none; }}
  </style>
</defs>
<rect width="{W}" height="{H}" fill="#ffffff"/>
{chr(10).join(out)}
</svg>
"""
    path = ROOT / "docs" / "system_diagram.svg"
    path.parent.mkdir(exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
