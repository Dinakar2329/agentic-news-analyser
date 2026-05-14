import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiErrorMessage, login, register } from "@/lib/api";
import { useAppStore } from "@/store/appStore";
import { Icon } from "@/components/icons.jsx";

export function AuthModal({ onClose, onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("student@example.com");
  const [password, setPassword] = useState("angetic-demo-2026");
  const setUser = useAppStore((state) => state.setUser);

  const mutation = useMutation({
    mutationFn: () =>
      mode === "login"
        ? login({ email, password })
        : register({ email, password }),
    onSuccess: (data) => {
      setUser(data.user);
      onAuthenticated?.(data.user);
      onClose();
    },
  });

  const submit = (event) => {
    event.preventDefault();
    mutation.mutate();
  };

  return (
    <div className="modal-veil" onClick={onClose}>
      <form
        className="auth-modal"
        onSubmit={submit}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div className="ph-logo">
            <Icon.Logo />
          </div>
          <div>
            <div className="ph-name">
              {mode === "login" ? "Sign in" : "Create account"}
            </div>
            <div className="ph-desc">
              Required by the FastAPI backend before storing keys or starting
              jobs.
            </div>
          </div>
          <div className="ph-close">
            <button type="button" className="iconbtn" onClick={onClose}>
              <Icon.Close />
            </button>
          </div>
        </div>

        <div className="modal-body" style={{ gap: 14 }}>
          <label className="field">
            <div className="label">
              <span>Email</span>
            </div>
            <div className="key-input">
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
          </label>
          <label className="field">
            <div className="label">
              <span>Password</span>
              <span className="hint">minimum 8 characters</span>
            </div>
            <div className="key-input">
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
              />
            </div>
          </label>

          {mutation.isError && (
            <div className="inline-error">
              {apiErrorMessage(mutation.error)}
            </div>
          )}

          <div className="help">
            Local dev tip: create a throwaway project account here. The backend
            stores only the password hash.
          </div>
        </div>

        <div className="modal-foot">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setMode(mode === "login" ? "register" : "login")}
          >
            {mode === "login" ? "Create account" : "Use existing account"}
          </button>
          <div className="ff-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={mutation.isPending}
            >
              {mutation.isPending
                ? "Connecting..."
                : mode === "login"
                  ? "Sign in"
                  : "Register"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
