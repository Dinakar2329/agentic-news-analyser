import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { createInvestigation, apiErrorMessage } from "@/lib/api";
import { depthToNumber, providerFromModel } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";
import { Icon } from "@/components/icons.jsx";
import { Particles } from "@/components/Particles.jsx";

const SUGGESTIONS = [
  { tag: "FINANCE", text: "JPMorgan files lawsuit against Tesla for $162M over a 2014 stock warrant dispute" },
  { tag: "TWEET", text: "Major US bank just collapsed overnight and FDIC is stepping in" },
  { tag: "POLITICS", text: "EU passes law banning all gas-powered cars by 2030" },
  { tag: "HEALTH", text: "New study claims daily coffee reduces dementia risk by 65%" },
];

export function ChatScreen({ onBack, onOpenBYOK, onRequireAuth }) {
  const user = useAppStore((state) => state.user);
  const providers = useAppStore((state) => state.models);
  const startInvestigation = useAppStore((state) => state.startInvestigation);
  const [text, setText] = useState("");
  const [agents, setAgents] = useState(3);
  const [model, setModel] = useState("");
  const [depth, setDepth] = useState("Standard");
  const [tradeoff, setTradeoff] = useState(60);
  const textareaRef = useRef(null);

  const selectableModels = useMemo(() => flattenModels(providers), [providers]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!model && selectableModels.length) {
      const preferred = selectableModels.find((item) => item.available) || selectableModels[0];
      setModel(preferred.id);
    }
  }, [model, selectableModels]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!user) {
        onRequireAuth?.();
        throw new Error("Sign in before starting an investigation.");
      }
      const claim = text.trim();
      if (!claim) throw new Error("Enter a claim to investigate.");
      const selectedModel = model || selectableModels[0]?.id || "gpt-4o";
      return createInvestigation({
        claim,
        agent_count: agents,
        provider: providerFromModel(selectedModel, providers),
        model: selectedModel,
        search_depth: depthToNumber(depth),
        speed_accuracy: tradeoff,
      });
    },
    onSuccess: (data) => {
      startInvestigation({ id: data.id, claim: data.claim });
    },
  });

  const handleSubmit = () => mutation.mutate();

  return (
    <div className="chat-screen" data-screen-label="02 Chat">
      <div className="grid-bg" />
      <Particles count={12} />

      <div className="center">
        <div className="composer-shell fade-in">
          <div className="title-row">
            <div className="kicker">New Investigation</div>
            <h1>What should we verify?</h1>
            <p>Paste a claim, tweet, headline, or article excerpt. Proper nouns and dates improve source matching.</p>
          </div>

          <div className="composer">
            <textarea
              ref={textareaRef}
              className="composer-textarea"
              placeholder="e.g. JPMorgan files lawsuit against Tesla for $162M over a 2014 stock warrant dispute..."
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) handleSubmit();
              }}
            />
            <div className="composer-controls">
              <div className="left">
                <ModelMenu value={model} models={selectableModels} onChange={setModel} onOpenBYOK={onOpenBYOK} />
                <AgentStepper value={agents} onChange={setAgents} />
                <DepthMenu value={depth} onChange={setDepth} />
                <SliderControl label="Speed to Accuracy" value={tradeoff} onChange={setTradeoff} />
              </div>
              <div className="right">
                <span className="muted mono shortcut">CTRL ENTER</span>
                <button className="send-btn" onClick={handleSubmit} title="Run investigation" disabled={mutation.isPending}>
                  {mutation.isPending ? <Icon.Zap /> : <Icon.Send />}
                </button>
              </div>
            </div>
          </div>

          {mutation.isError && <div className="inline-error composer-error">{apiErrorMessage(mutation.error)}</div>}

          <div className="suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button key={suggestion.tag} className="suggestion" onClick={() => setText(suggestion.text)}>
                <span className="tag">{suggestion.tag}</span>
                <span>{suggestion.text}</span>
              </button>
            ))}
          </div>

          <div className="chat-footer-row">
            <span>
              &lt;-{" "}
              <button className="btn-ghost mono" onClick={onBack}>
                BACK TO HOME
              </button>
            </span>
            <span>{user ? `SIGNED IN AS ${user.email}` : "SIGN IN REQUIRED TO RUN BACKEND JOBS"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function flattenModels(providers) {
  return providers
    .filter((provider) => provider.runtime_available !== false)
    .flatMap((provider) =>
      (provider.models || []).map((model) => ({
        ...model,
        providerId: provider.id,
        providerName: provider.name,
        available: provider.available,
      }))
    )
    .sort((a, b) => Number(b.available) - Number(a.available));
}

function ModelMenu({ value, models, onChange, onOpenBYOK }) {
  const [open, setOpen] = useState(false);
  const selected = models.find((item) => item.id === value) || models[0] || { id: "gpt-4o", label: "GPT-4o", providerName: "OpenAI" };

  return (
    <div style={{ position: "relative" }}>
      <button className="control-pill" onClick={() => setOpen((current) => !current)}>
        <Icon.Spark style={{ color: "var(--accent)" }} />
        <span className="label">MODEL</span>
        <span className="val">{selected.label || selected.id}</span>
        <span style={{ color: "var(--text-4)" }}>v</span>
      </button>
      {open && (
        <div className="menu-popover model-menu-popover">
          {models.map((item) => (
            <button
              key={`${item.providerId}-${item.id}`}
              onClick={() => {
                if (!item.available) return;
                onChange(item.id);
                setOpen(false);
              }}
              className={item.id === value ? "selected" : ""}
              disabled={!item.available}
            >
              <span style={{ flex: 1, textAlign: "left" }}>{item.label || item.id}</span>
              <span className="mono provider-code">{item.providerName}</span>
              {!item.available && <span className="mono" style={{ marginLeft: 8 }}>key required</span>}
              {item.id === value && item.available && <Icon.Check />}
            </button>
          ))}
          <div className="menu-separator" />
          <button
            onClick={() => {
              setOpen(false);
              onOpenBYOK();
            }}
            className="accent-action"
          >
            <Icon.Key /> Manage API keys
          </button>
        </div>
      )}
    </div>
  );
}

function AgentStepper({ value, onChange }) {
  return (
    <div className="stepper" title="Number of investigative agents">
      <button onClick={() => onChange(Math.max(1, value - 1))} aria-label="Decrease">
        <Icon.Minus />
      </button>
      <div className="v">
        <span style={{ color: "var(--text-4)", marginRight: 6, fontSize: 10 }}>AGENTS</span>
        {value}
      </div>
      <button onClick={() => onChange(Math.min(4, value + 1))} aria-label="Increase">
        <Icon.Plus />
      </button>
    </div>
  );
}

function DepthMenu({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const options = ["Quick", "Standard", "Deep", "Exhaustive"];

  return (
    <div style={{ position: "relative" }}>
      <button className="control-pill" onClick={() => setOpen((current) => !current)}>
        <Icon.Search />
        <span className="label">DEPTH</span>
        <span className="val">{value}</span>
        <span style={{ color: "var(--text-4)" }}>v</span>
      </button>
      {open && (
        <div className="menu-popover depth-menu-popover">
          {options.map((option) => (
            <button
              key={option}
              onClick={() => {
                onChange(option);
                setOpen(false);
              }}
              className={option === value ? "selected" : ""}
            >
              <span style={{ flex: 1, textAlign: "left" }}>{option}</span>
              {option === value && <Icon.Check />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SliderControl({ label, value, onChange }) {
  const text = value < 35 ? "Speed" : value > 65 ? "Accuracy" : "Balanced";

  return (
    <div className="slider-row" style={{ minWidth: 200 }}>
      <div className="top">
        <span className="label">{label}</span>
        <span className="val">
          {text} {value}
        </span>
      </div>
      <input type="range" min="0" max="100" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </div>
  );
}
