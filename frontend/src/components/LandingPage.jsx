import { motion } from "framer-motion";
import { Icon } from "@/components/icons.jsx";
import { Particles } from "@/components/Particles.jsx";

export function LandingPage({ onCTA, onOpenBYOK }) {
  return (
    <div className="landing" data-screen-label="01 Landing">
      <div className="grid-bg" />
      <Particles count={18} />

      <div className="landing-inner">
        <motion.section
          className="hero"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="eyebrow">
            <span className="badge">v0.4 beta</span>
            <span>Multi-agent investigative AI, live now</span>
          </div>
          <h1>
            Verify viral news, <em>before</em> it goes viral.
          </h1>
          <p className="sub">
            Veritas dispatches specialist agents to cross-check claims against primary sources,
            news reports, and contradiction searches in real time.
          </p>
          <div className="cta-row">
            <button className="btn btn-primary btn-lg" onClick={onCTA}>
              Start Investigating
              <Icon.Arrow />
            </button>
            <button className="btn btn-lg" onClick={onOpenBYOK}>
              <Icon.Key />
              Connect your model
            </button>
          </div>
          <div className="meta-row">
            <span>
              <span className="led" /> 1-4 agents
            </span>
            <span>
              <Icon.Bolt /> WebSocket streamed
            </span>
            <span>
              <Icon.Shield /> Source-cited verdicts
            </span>
          </div>
        </motion.section>

        <ArchPreview />

        <header className="section-head">
          <div className="kicker">Capabilities</div>
          <h2>The investigative loop, parallelized.</h2>
          <p className="lead">Six pieces of the real backend pipeline exposed as a premium tool.</p>
        </header>
        <FeatureGrid />

        <header className="section-head">
          <div className="kicker">Workflow</div>
          <h2>From claim to verdict in four moves.</h2>
        </header>
        <WorkflowStrip />

        <section className="cta-section">
          <h2>
            Stop guessing. Start <em style={{ color: "var(--accent)", fontStyle: "italic" }}>knowing</em>.
          </h2>
          <p>Paste any headline, tweet, article, or rumor. Watch a transparent investigation play out.</p>
          <button className="btn btn-primary btn-lg" onClick={onCTA}>
            Open the investigator
            <Icon.Arrow />
          </button>
        </section>

        <footer className="foot">
          <span>VERITAS 2026 multi-agent runtime</span>
          <span>React, WebSocket, React Flow, TanStack Query</span>
        </footer>
      </div>
    </div>
  );
}

function ArchPreview() {
  return (
    <div className="arch-preview">
      <div className="arch-chrome">
        <span className="dotz">
          <span />
          <span />
          <span />
        </span>
        <span style={{ marginLeft: 8 }}>veritas live investigation graph</span>
        <span style={{ marginLeft: "auto" }}>READY</span>
      </div>
      <div className="arch-body">
        <MiniGraph />
      </div>
    </div>
  );
}

function MiniGraph() {
  const edges = [
    ["M 180,160 C 280,160 280,80 380,80", "0.7s"],
    ["M 180,160 C 280,160 280,160 380,160", "1.1s"],
    ["M 180,160 C 280,160 280,240 380,240", "0.9s"],
    ["M 460,80 C 560,80 560,50 660,50", "1.2s"],
    ["M 460,80 C 560,80 560,110 660,110", "1.4s"],
    ["M 460,160 C 560,160 560,160 660,160", "1.3s"],
    ["M 460,240 C 560,240 560,210 660,210", "1.5s"],
    ["M 460,240 C 560,240 560,270 660,270", "1.6s"],
  ];

  return (
    <svg viewBox="0 0 900 320" width="100%" height="320" style={{ display: "block" }} aria-hidden="true">
      <defs>
        <radialGradient id="mini-orb" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.9" />
          <stop offset="60%" stopColor="var(--accent)" stopOpacity="0.2" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {edges.map(([d, duration], index) => (
        <g key={index}>
          <path d={d} className="edge" />
          <path d={d} className="edge active" style={{ animationDuration: duration }} />
        </g>
      ))}

      <g transform="translate(140, 160)">
        <circle r="44" fill="url(#mini-orb)" />
        <rect x="-50" y="-22" width="100" height="44" rx="10" fill="var(--surface)" stroke="var(--border-strong)" />
        <text x="0" y="-2" textAnchor="middle" fill="var(--text)" fontSize="11" fontWeight="600">
          Orchestrator
        </text>
        <text x="0" y="13" textAnchor="middle" fill="var(--accent)" fontSize="9" fontFamily="var(--font-mono)">
          CONFIDENCE 78%
        </text>
      </g>

      {[
        ["Official", 80, "A1"],
        ["Newswire", 160, "A2"],
        ["Contradict", 240, "A3"],
      ].map(([name, y, code]) => (
        <g key={code} transform={`translate(420, ${y})`}>
          <rect x="-44" y="-16" width="88" height="32" rx="6" fill="var(--surface)" stroke="var(--border-strong)" />
          <circle cx="-28" cy="0" r="9" fill="var(--surface-3)" />
          <text x="-28" y="3" textAnchor="middle" fill="var(--text)" fontSize="9" fontFamily="var(--font-mono)" fontWeight="600">
            {code}
          </text>
          <text x="-10" y="3" fill="var(--text)" fontSize="10" fontWeight="500">
            {name}
          </text>
        </g>
      ))}

      {[
        ["SEC", 50],
        ["COURT", 110],
        ["REUT", 160],
        ["FACT", 210],
        ["WIRE", 270],
      ].map(([host, y]) => (
        <g key={host} transform={`translate(700, ${y})`}>
          <rect x="-32" y="-12" width="64" height="24" rx="5" fill="var(--surface-2)" stroke="var(--border)" />
          <text x="0" y="3" textAnchor="middle" fill="var(--text-2)" fontSize="9" fontFamily="var(--font-mono)">
            {host}
          </text>
        </g>
      ))}
    </svg>
  );
}

function FeatureGrid() {
  const features = [
    { icon: <Icon.Network />, title: "Parallel agents", body: "Specialist agents fan out to official, trusted, contradiction, and context searches." },
    { icon: <Icon.Brain />, title: "Live reasoning", body: "Every source discovery, score update, and verdict event streams from the backend." },
    { icon: <Icon.Shield />, title: "Primary-source first", body: "Official sources and filings receive higher scoring weight than social reposts." },
    { icon: <Icon.Globe />, title: "Adversarial sweep", body: "Dedicated queries look for denials, corrections, fact checks, and counter-evidence." },
    { icon: <Icon.Bolt />, title: "BYOK runtime", body: "Connect OpenAI, Anthropic, Gemini, Groq, DeepSeek, or other configured providers." },
    { icon: <Icon.Eye />, title: "Auditable verdicts", body: "Confidence, truth probability, bias, source quality, and full citations remain visible." },
  ];

  return (
    <div className="feature-grid">
      {features.map((feature, index) => (
        <div className="feature-card" key={feature.title}>
          <div className="num">{String(index + 1).padStart(2, "0")}</div>
          <div className="icon">{feature.icon}</div>
          <h3>{feature.title}</h3>
          <p>{feature.body}</p>
        </div>
      ))}
    </div>
  );
}

function WorkflowStrip() {
  const steps = [
    { number: "01", title: "Submit", body: "Paste a tweet, headline, claim, or article body." },
    { number: "02", title: "Dispatch", body: "The backend creates a queued investigation job." },
    { number: "03", title: "Investigate", body: "Agents search, extract, score, and classify sources." },
    { number: "04", title: "Verdict", body: "A confidence-weighted synthesis streams back over WebSocket." },
  ];

  return (
    <div className="workflow">
      {steps.map((step, index) => (
        <div className="wf-step" key={step.number}>
          <div className="step-num">STEP {step.number}</div>
          <h4>{step.title}</h4>
          <p>{step.body}</p>
          <div className="glyph">
            <WorkflowGlyph index={index} />
          </div>
        </div>
      ))}
    </div>
  );
}

function WorkflowGlyph({ index }) {
  if (index === 0) {
    return (
      <div style={{ flex: 1, height: 32, borderRadius: 6, border: "1px solid var(--border-soft)", background: "var(--surface-2)", padding: "6px 8px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-3)" }}>
        &gt; "JPMorgan files lawsuit"<span className="cursor" style={{ height: "0.8em" }} />
      </div>
    );
  }
  if (index === 1) {
    return (
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        {[0, 1, 2, 3].map((item) => (
          <span key={item} style={{ width: 18, height: 18, borderRadius: 4, background: "var(--surface-2)", border: "1px solid var(--border-soft)", display: "grid", placeItems: "center", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--accent)" }}>
            A{item + 1}
          </span>
        ))}
      </div>
    );
  }
  if (index === 2) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 3 }}>
        {[80, 55, 72].map((width) => (
          <span key={width} style={{ height: 3, background: "var(--surface-3)", borderRadius: 99, overflow: "hidden" }}>
            <span style={{ display: "block", height: "100%", width: `${width}%`, background: "var(--accent)", boxShadow: "0 0 6px var(--accent-glow)" }} />
          </span>
        ))}
      </div>
    );
  }
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px", borderRadius: 99, background: "var(--accent-soft)", color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 10, border: "1px solid var(--accent-dim)" }}>
      <Icon.Check /> MOSTLY TRUE 78%
    </div>
  );
}
