import axios from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || API_BASE_URL.replace(/^http/, "ws");

const TOKEN_KEY = "veritas.access_token";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export async function register(payload) {
  const { data } = await api.post("/auth/register", payload);
  setToken(data.access_token);
  return data;
}

export async function login(payload) {
  const { data } = await api.post("/auth/login", payload);
  setToken(data.access_token);
  return data;
}

export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

export async function getModels() {
  const { data } = await api.get("/models");
  return data.providers || [];
}

export async function validateKey(payload) {
  const { data } = await api.post("/validate-key", payload);
  return data;
}

export async function createInvestigation(payload) {
  const { data } = await api.post("/investigate", payload);
  return data;
}

export async function getInvestigation(id) {
  const { data } = await api.get(`/investigations/${id}`);
  return data;
}

export function investigationWsUrl(id) {
  const token = encodeURIComponent(getToken() || "");
  return `${WS_BASE_URL}/ws/investigation/${id}?token=${token}`;
}

export function apiErrorMessage(error) {
  return error?.response?.data?.detail || error?.message || "Request failed";
}
