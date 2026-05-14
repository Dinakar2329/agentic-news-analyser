import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function shortId(id) {
  return id ? id.slice(0, 4) : "idle";
}

export function formatPercent(value, fallback = 0) {
  const number = Number.isFinite(Number(value)) ? Number(value) : fallback;
  return `${Math.round(number)}%`;
}

export function verdictKey(verdict) {
  return String(verdict || "UNVERIFIED")
    .trim()
    .replaceAll(" ", "_")
    .toUpperCase();
}

export function depthToNumber(depth) {
  if (typeof depth === "number") return clamp(depth, 1, 5);
  return (
    {
      Quick: 1,
      Standard: 3,
      Deep: 4,
      Exhaustive: 5,
    }[depth] || 3
  );
}

export function providerFromModel(modelId, providers = []) {
  for (const provider of providers) {
    if ((provider.models || []).some((model) => model.id === modelId)) {
      return provider.id;
    }
  }
  if (modelId?.startsWith("claude")) return "anthropic";
  if (modelId?.startsWith("gemini")) return "google";
  if (modelId?.startsWith("deepseek")) return "deepseek";
  if (modelId?.includes("llama") || modelId?.includes("gpt-oss")) return "groq";
  if (modelId?.startsWith("mistral")) return "mistral";
  return "openai";
}
