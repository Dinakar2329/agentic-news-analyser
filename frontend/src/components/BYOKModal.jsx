import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiErrorMessage, getModels, validateKey } from "@/lib/api";
import { useAppStore } from "@/store/appStore";
import { Icon } from "@/components/icons.jsx";

const PROVIDER_META = {
  openai: { logo: "OA", prefix: "sk-", desc: "GPT and o-series models" },
  anthropic: { logo: "AN", prefix: "sk-ant-", desc: "Claude Sonnet and Opus" },
  google: { logo: "GG", prefix: "AIza", desc: "Gemini 2.5 models" },
  mistral: { logo: "MI", prefix: "", desc: "Mistral Large" },
  groq: { logo: "GQ", prefix: "gsk_", desc: "Groq-hosted fast inference" },
  deepseek: { logo: "DS", prefix: "sk-", desc: "DeepSeek reasoning models" },
};

export function BYOKModal({ onClose }) {
  const providers = useAppStore((state) => state.models);
  const setModels = useAppStore((state) => state.setModels);
  const queryClient = useQueryClient();
  const visibleProviders = providers.length ? providers : fallbackProviders();
  const [active, setActive] = useState(visibleProviders[0]?.id || "openai");
  const [keys, setKeys] = useState({});
  const [selectedModels, setSelectedModels] = useState({});
  const [reveal, setReveal] = useState(false);
  const [keyHints, setKeyHints] = useState(() => JSON.parse(sessionStorage.getItem("veritas.key_hints") || "{}"));

  const provider = useMemo(
    () => visibleProviders.find((item) => item.id === active) || visibleProviders[0],
    [active, visibleProviders]
  );
  const meta = PROVIDER_META[provider?.id] || { logo: provider?.id?.slice(0, 2)?.toUpperCase() || "AI", prefix: "", desc: "Model provider" };
  const models = provider?.models || [];
  const selectedModel = selectedModels[active] || models[0]?.id || "";
  const apiKey = keys[active] || "";

  const mutation = useMutation({
    mutationFn: () => validateKey({ provider: active, api_key: apiKey }),
    onSuccess: async (data) => {
      const nextHints = { ...keyHints, [active]: data.key_hint };
      setKeyHints(nextHints);
      sessionStorage.setItem("veritas.key_hints", JSON.stringify(nextHints));
      const refreshed = await queryClient.fetchQuery({ queryKey: ["models"], queryFn: getModels });
      setModels(refreshed);
      setKeys((prev) => ({ ...prev, [active]: "" }));
    },
  });

  return (
    <div className="modal-veil" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <aside className="modal-side">
          <div className="ms-head">
            <div className="kicker">Settings</div>
            <div className="title">Bring your own key</div>
          </div>
          <div className="ms-nav">
            {visibleProviders.map((item) => {
              const itemMeta = PROVIDER_META[item.id] || {};
              const hasKey = item.available || keyHints[item.id];
              return (
                <button
                  key={item.id}
                  className={(active === item.id ? "active " : "") + (hasKey ? "has-key" : "")}
                  onClick={() => setActive(item.id)}
                >
                  <span className="provider-logo">{itemMeta.logo || item.id.slice(0, 2).toUpperCase()}</span>
                  <span style={{ flex: 1, textAlign: "left" }}>{item.name}</span>
                  <span className="dot" />
                </button>
              );
            })}
          </div>
          <div className="security-copy">
            <Icon.Lock /> Keys are sent once to the backend, validated, encrypted with `KEY_ENCRYPTION_SECRET`, and never logged.
          </div>
        </aside>

        <main className="modal-main">
          <div className="modal-head">
            <div className="ph-logo">{meta.logo}</div>
            <div>
              <div className="ph-name">{provider?.name || "Provider"}</div>
              <div className="ph-desc">{provider?.unavailable_reason || meta.desc}</div>
            </div>
            <div className="ph-close">
              <button className="iconbtn" onClick={onClose}>
                <Icon.Close />
              </button>
            </div>
          </div>

          <div className="modal-body">
            <div className="field">
              <div className="label">
                <span>API key</span>
                <span className="hint">{keyHints[active] ? `stored as ${keyHints[active]}` : meta.prefix ? `usually starts with ${meta.prefix}` : "provider token"}</span>
              </div>
              <div className="key-input">
                <input
                  type={reveal ? "text" : "password"}
                  placeholder={keyHints[active] ? "Paste a new key to rotate" : "Paste provider API key"}
                  value={apiKey}
                  onChange={(event) => setKeys((prev) => ({ ...prev, [active]: event.target.value }))}
                  disabled={!provider?.runtime_available}
                />
                <div className="post">
                  <button className="iconbtn" onClick={() => setReveal((value) => !value)} title={reveal ? "Hide" : "Reveal"}>
                    {reveal ? <Icon.EyeOff /> : <Icon.Eye />}
                  </button>
                </div>
              </div>
              <div className="help">
                The key is stored server-side as Fernet ciphertext. The browser keeps only the returned hint for this session.
              </div>
            </div>

            <div className="field">
              <div className="label">
                <span>Models reported by backend</span>
                <span className="hint">{provider?.available ? "ready" : "key required"}</span>
              </div>
              <div className="model-grid">
                {models.map((model) => (
                  <button
                    key={model.id}
                    className={"model-card " + (selectedModel === model.id ? "selected" : "")}
                    onClick={() => setSelectedModels((prev) => ({ ...prev, [active]: model.id }))}
                  >
                    <div className="mc-top">
                      <div>
                        <div className="mc-name">{model.label || model.id}</div>
                        <div className="mc-id">{model.id}</div>
                      </div>
                      <span className="mc-tag">{model.reasoning ? "REASONING" : "STANDARD"}</span>
                    </div>
                    <div className="mc-caps">
                      {Object.entries(provider?.capabilities || {}).map(([cap, enabled]) => (
                        <span key={cap} className={"cap " + (enabled ? "has" : "")}>
                          {cap.replaceAll("_", " ")}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {mutation.isError && <div className="inline-error">{apiErrorMessage(mutation.error)}</div>}
            {mutation.isSuccess && <div className="inline-success">Key validated and encrypted.</div>}
          </div>

          <div className="modal-foot">
            <div className="ff-status">
              <span className={provider?.available ? "status-dot good" : "status-dot"} />
              {provider?.available ? "Provider available" : provider?.runtime_available ? "No key configured" : "Runtime unavailable"}
            </div>
            <div className="ff-actions">
              <button className="btn btn-ghost" onClick={onClose}>
                Close
              </button>
              <button className="btn btn-primary" onClick={() => mutation.mutate()} disabled={!apiKey || !provider?.runtime_available || mutation.isPending}>
                {mutation.isPending ? "Validating..." : "Save and validate"}
              </button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function fallbackProviders() {
  return [
    { id: "openai", name: "OpenAI", available: false, runtime_available: true, capabilities: {}, models: [{ id: "gpt-4o", label: "GPT-4o" }] },
  ];
}
