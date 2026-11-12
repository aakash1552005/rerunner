"""Standalone HTML report generator for Rerunner cost and token savings."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path


def generate_cost_html_report(
    cassette_count: int,
    total_steps: int,
    total_http: int,
    total_tools: int,
    total_tokens: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    latency_sec: float = 0.0,
    target_label: str = "",
) -> str:
    """Generate self-contained HTML report with responsive styling and zero external CDN dependencies."""
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    target_display = html.escape(target_label) if target_label else "Repository Cassettes"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rerunner Replay Savings Report</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent-cyan: #38bdf8;
      --accent-green: #4ade80;
      --accent-yellow: #facc15;
      --accent-purple: #c084fc;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      line-height: 1.5;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 960px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 2rem;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 1.5rem;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-cyan);
      margin-bottom: 0.75rem;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    h1 {{
      font-size: 1.875rem;
      font-weight: 800;
      letter-spacing: -0.025em;
      margin-bottom: 0.5rem;
      background: linear-gradient(to right, #38bdf8, #818cf8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .subtitle {{
      color: var(--text-muted);
      font-size: 0.95rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.75rem;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .card-title {{
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.5rem;
    }}
    .card-value {{
      font-size: 1.75rem;
      font-weight: 800;
      margin-bottom: 0.25rem;
    }}
    .card-value.green {{ color: var(--accent-green); }}
    .card-value.cyan {{ color: var(--accent-cyan); }}
    .card-value.yellow {{ color: var(--accent-yellow); }}
    .card-value.purple {{ color: var(--accent-purple); }}
    .card-note {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.75rem;
      overflow: hidden;
      margin-bottom: 2rem;
    }}
    .table-header {{
      padding: 1rem 1.25rem;
      font-weight: 700;
      font-size: 1.1rem;
      border-bottom: 1px solid var(--card-border);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.9rem;
    }}
    th, td {{
      padding: 0.85rem 1.25rem;
      border-bottom: 1px solid var(--card-border);
    }}
    th {{
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      background: rgba(15, 23, 42, 0.4);
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .text-right {{
      text-align: right;
    }}
    .highlight {{
      font-weight: 700;
      color: var(--accent-green);
    }}
    footer {{
      text-align: center;
      color: var(--text-muted);
      font-size: 0.85rem;
      padding-top: 1rem;
      border-top: 1px solid var(--card-border);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <span class="badge">Rerunner Analytics</span>
      <h1>⚡ CI Replay Savings & Efficiency Report</h1>
      <p class="subtitle">Target: <strong>{target_display}</strong> &bull; Generated: {now_utc}</p>
    </header>

    <div class="grid">
      <div class="card">
        <div class="card-title">Estimated Cost Avoided</div>
        <div class="card-value green">${estimated_cost_usd:.4f}</div>
        <div class="card-note">Offline Replay: $0.00 USD</div>
      </div>
      <div class="card">
        <div class="card-title">Tokens Avoided</div>
        <div class="card-value cyan">{total_tokens:,}</div>
        <div class="card-note">Prompt: {prompt_tokens:,} | Compl: {completion_tokens:,}</div>
      </div>
      <div class="card">
        <div class="card-title">CI Latency Saved</div>
        <div class="card-value yellow">~{latency_sec:.1f}s</div>
        <div class="card-note">Replay duration: &lt; 1s</div>
      </div>
      <div class="card">
        <div class="card-title">Execution Steps</div>
        <div class="card-value purple">{total_steps:,}</div>
        <div class="card-note">{cassette_count} cassette file(s) analyzed</div>
      </div>
    </div>

    <div class="table-container">
      <div class="table-header">Detailed Replay vs Live API Comparison</div>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th class="text-right">Offline Replay</th>
            <th class="text-right">Live API Estimate</th>
            <th class="text-right">Savings / Benefit</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Cassette Files</td>
            <td class="text-right">{cassette_count}</td>
            <td class="text-right">-</td>
            <td class="text-right">Recorded Trajectories</td>
          </tr>
          <tr>
            <td>Execution Steps Replayed</td>
            <td class="text-right">{total_steps:,}</td>
            <td class="text-right">{total_steps:,}</td>
            <td class="text-right highlight">100% Deterministic</td>
          </tr>
          <tr>
            <td>HTTP Model Invocations</td>
            <td class="text-right">{total_http:,}</td>
            <td class="text-right">{total_http:,}</td>
            <td class="text-right highlight">0 Flaky Network Calls</td>
          </tr>
          <tr>
            <td>Tool Interceptions Stubbed</td>
            <td class="text-right">{total_tools:,}</td>
            <td class="text-right">{total_tools:,}</td>
            <td class="text-right highlight">0 Live Side-Effects</td>
          </tr>
          <tr>
            <td>Prompt Tokens Saved</td>
            <td class="text-right">{prompt_tokens:,}</td>
            <td class="text-right">{prompt_tokens:,}</td>
            <td class="text-right highlight">Quota Protected</td>
          </tr>
          <tr>
            <td>Completion Tokens Saved</td>
            <td class="text-right">{completion_tokens:,}</td>
            <td class="text-right">{completion_tokens:,}</td>
            <td class="text-right highlight">Quota Protected</td>
          </tr>
          <tr>
            <td>Total Tokens Replayed</td>
            <td class="text-right">{total_tokens:,}</td>
            <td class="text-right">{total_tokens:,}</td>
            <td class="text-right highlight">100% Token Savings</td>
          </tr>
          <tr>
            <td>Estimated API Cost</td>
            <td class="text-right">$0.00</td>
            <td class="text-right">~${estimated_cost_usd:.4f}</td>
            <td class="text-right highlight">Saved ~${estimated_cost_usd:.4f}</td>
          </tr>
          <tr>
            <td>CI Execution Duration</td>
            <td class="text-right">&lt; 1s</td>
            <td class="text-right">~{latency_sec:.1f}s</td>
            <td class="text-right highlight">~{latency_sec:.1f}s Faster</td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer>
      Report generated by <a href="https://github.com/aakash1552005/rerunner" style="color: var(--accent-cyan); text-decoration: none;">Rerunner</a> &bull; Deterministic flight recorder & replay engine for AI agents
    </footer>
  </div>
</body>
</html>
"""


def export_cost_html_report(
    output_path: Path | str,
    cassette_count: int,
    total_steps: int,
    total_http: int,
    total_tools: int,
    total_tokens: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    latency_sec: float = 0.0,
    target_label: str = "",
) -> Path:
    """Generate and write a standalone HTML savings report to output_path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_cost_html_report(
        cassette_count=cassette_count,
        total_steps=total_steps,
        total_http=total_http,
        total_tools=total_tools,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost_usd,
        latency_sec=latency_sec,
        target_label=target_label,
    )
    path.write_text(content, encoding="utf-8")
    return path


def generate_trace_html_report(cassette_path: Path | str) -> str:
    """Render a zero-CDN interactive HTML flight trace timeline for a cassette."""
    import json
    from rerunner.cassette import Cassette
    from rerunner.cassette_ops import extract_entry_info, verify_cassette_report

    cassette = Cassette.load(cassette_path, verify_integrity=False)
    report = verify_cassette_report(cassette_path, strict_security=False)
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    integrity_badge = (
        '<span class="pill ok">SHA-256 Verified</span>'
        if report["integrity_valid"]
        else '<span class="pill err">Integrity Failed</span>'
    )
    leak_count = len(report["leaks"])
    security_badge = (
        '<span class="pill ok">0 Secret/PII Leaks</span>'
        if leak_count == 0
        else f'<span class="pill err">{leak_count} Potential Leaks</span>'
    )

    step_cards: list[str] = []
    for entry in cassette.entries:
        info = extract_entry_info(entry)
        kind = "http" if entry.entry_type == "http" else "tool"
        is_error = info["status"] == "Error" or (
            info["status"].isdigit() and int(info["status"]) >= 400
        )
        status_cls = "err" if is_error else "ok"
        tokens_label = f"{info['tokens']:,} tok" if info["tokens"] else "-"

        if entry.entry_type == "http" and entry.request and entry.response:
            req_preview = html.escape(entry.request.body[:2000])
            resp_preview = html.escape(entry.response.body[:2000])
            chunk_info = (
                f"SSE Chunks: {len(entry.response.chunks)}"
                if entry.response.is_streaming
                else "Buffered"
            )
            detail_html = (
                f'<div class="detail-grid">'
                f"<div><h4>Request ({html.escape(chunk_info)})</h4><pre>{req_preview or '(empty)'}</pre></div>"
                f"<div><h4>Response ({html.escape(info['status'])})</h4><pre>{resp_preview or '(empty)'}</pre></div>"
                f"</div>"
            )
        else:
            args_json = html.escape(
                json.dumps(
                    {
                        "args": entry.side_effect_args,
                        "kwargs": entry.side_effect_kwargs,
                        "result": entry.side_effect_result,
                        "exception": entry.side_effect_exception,
                    },
                    indent=2,
                    default=str,
                )[:3000]
            )
            detail_html = f'<div class="detail-grid"><div><h4>Tool Execution</h4><pre>{args_json}</pre></div></div>'

        step_cards.append(
            f'<details class="step-card" data-kind="{kind}" data-err="{"1" if is_error else "0"}" '
            f'data-text="{html.escape(info["target"].lower())}">'
            f"<summary>"
            f'<span class="step-num">#{info["step"]}</span>'
            f'<span class="kind {kind}">{html.escape(info["type"])}</span>'
            f'<span class="target">{html.escape(info["target"])}</span>'
            f'<span class="pill {status_cls}">{html.escape(info["status"])}</span>'
            f'<span class="meta">{html.escape(tokens_label)} · {html.escape(info["latency"])}</span>'
            f"</summary>"
            f"{detail_html}"
            f"</details>"
        )

    cards_markup = "\n".join(step_cards) if step_cards else "<p>No recorded steps.</p>"
    title_path = html.escape(str(cassette_path))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rerunner Flight Trace — {title_path}</title>
  <style>
    :root {{ --bg:#0b1120; --surface:#111827; --border:#1f2937; --text:#f8fafc; --muted:#94a3b8; --cyan:#38bdf8; --green:#22c55e; --red:#ef4444; --amber:#f59e0b; }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); padding:2rem 1rem; line-height:1.5; }}
    .wrap {{ max-width:1040px; margin:0 auto; }}
    header {{ border-bottom:1px solid var(--border); padding-bottom:1rem; margin-bottom:1.25rem; }}
    h1 {{ font-size:1.5rem; color:var(--cyan); margin-bottom:0.35rem; }}
    .badges {{ display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:0.6rem; align-items:center; }}
    .pill {{ font-size:0.75rem; font-weight:700; padding:0.2rem 0.55rem; border-radius:999px; border:1px solid var(--border); background:var(--surface); }}
    .pill.ok {{ color:var(--green); border-color:rgba(34,197,94,0.35); }}
    .pill.err {{ color:var(--red); border-color:rgba(239,68,68,0.4); }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:0.5rem; margin-bottom:1rem; }}
    .toolbar input {{ flex:1; min-width:220px; background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:0.5rem; padding:0.45rem 0.75rem; }}
    .btn {{ background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:0.5rem; padding:0.45rem 0.8rem; cursor:pointer; font-size:0.85rem; }}
    .btn.active {{ border-color:var(--cyan); color:var(--cyan); }}
    .step-card {{ background:var(--surface); border:1px solid var(--border); border-radius:0.65rem; margin-bottom:0.6rem; padding:0.7rem 0.9rem; }}
    summary {{ display:flex; gap:0.6rem; align-items:center; cursor:pointer; list-style:none; }}
    .step-num {{ font-weight:700; color:var(--muted); min-width:2.5rem; }}
    .kind {{ font-size:0.75rem; font-weight:700; padding:0.12rem 0.45rem; border-radius:0.35rem; background:#1e293b; color:var(--cyan); }}
    .kind.tool {{ color:var(--amber); }}
    .target {{ flex:1; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:0.85rem; overflow-wrap:anywhere; }}
    .meta {{ color:var(--muted); font-size:0.8rem; white-space:nowrap; }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:0.8rem; margin-top:0.75rem; padding-top:0.75rem; border-top:1px solid var(--border); }}
    h4 {{ font-size:0.78rem; color:var(--muted); text-transform:uppercase; margin-bottom:0.35rem; }}
    pre {{ background:#020617; border:1px solid var(--border); border-radius:0.5rem; padding:0.65rem; font-size:0.78rem; overflow-x:auto; white-space:pre-wrap; word-break:break-word; max-height:280px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Rerunner Flight Trace</h1>
      <div style="color:var(--muted);font-size:0.9rem;">{title_path} · Generated {now_utc}</div>
      <div class="badges">
        <span class="pill">{report["total_steps"]} Steps ({report["http_steps"]} HTTP / {report["side_effect_steps"]} Tool)</span>
        <span class="pill">~{report["estimated_tokens_saved"]:,} Tokens Saved (${report["estimated_cost_saved_usd"]:.4f})</span>
        {integrity_badge}
        {security_badge}
      </div>
    </header>
    <div class="toolbar">
      <input id="q" type="search" placeholder="Filter by URL, method, or tool name..." oninput="filterSteps()">
      <button class="btn active" onclick="setKind('all', this)">All</button>
      <button class="btn" onclick="setKind('http', this)">HTTP</button>
      <button class="btn" onclick="setKind('tool', this)">Tool</button>
      <button class="btn" onclick="setKind('err', this)">Errors</button>
    </div>
    <main id="steps">{cards_markup}</main>
  </div>
  <script>
    let activeKind = 'all';
    function setKind(kind, btn) {{
      activeKind = kind;
      document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterSteps();
    }}
    function filterSteps() {{
      const q = (document.getElementById('q').value || '').toLowerCase();
      document.querySelectorAll('.step-card').forEach(el => {{
        const matchesText = !q || el.dataset.text.includes(q);
        const matchesKind = activeKind === 'all'
          || (activeKind === 'err' && el.dataset.err === '1')
          || el.dataset.kind === activeKind;
        el.style.display = (matchesText && matchesKind) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>
"""


def export_trace_html_report(cassette_path: Path | str, output_path: Path | str) -> Path:
    """Write a standalone interactive HTML flight trace viewer to ``output_path``."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_trace_html_report(cassette_path), encoding="utf-8")
    return out
