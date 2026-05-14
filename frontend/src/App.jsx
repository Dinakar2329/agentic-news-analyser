import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { clearToken, getMe, getModels, getToken } from "@/lib/api";
import { useAppStore } from "@/store/appStore";
import { Icon } from "@/components/icons.jsx";
import { LandingPage } from "@/components/LandingPage.jsx";
import { ChatScreen } from "@/components/ChatScreen.jsx";
import { InvestigationPage } from "@/components/InvestigationPage.jsx";
import { BYOKModal } from "@/components/BYOKModal.jsx";
import { AuthModal } from "@/components/AuthModal.jsx";
import { Moon, Sun } from "lucide-react";

export default function App() {
  const screen = useAppStore((state) => state.screen);
  const user = useAppStore((state) => state.user);
  const authOpen = useAppStore((state) => state.authOpen);
  const byokOpen = useAppStore((state) => state.byokOpen);
  const investigation = useAppStore((state) => state.investigation);
  const setScreen = useAppStore((state) => state.setScreen);
  const setUser = useAppStore((state) => state.setUser);
  const setModels = useAppStore((state) => state.setModels);
  const setAuthOpen = useAppStore((state) => state.setAuthOpen);
  const setByokOpen = useAppStore((state) => state.setByokOpen);
  const resetInvestigation = useAppStore((state) => state.resetInvestigation);
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-accent", "lime");
  }, []);

  useEffect(() => {
    const html = document.documentElement;
    html.dataset.theme = theme;
    if (theme === "dark") {
      html.classList.add("dark");
    } else {
      html.classList.remove("dark");
    }
    window.localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!getToken()) return;
    getMe()
      .then(setUser)
      .catch(() => {
        clearToken();
        setUser(null);
      });
  }, [setUser]);

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
    enabled: Boolean(user),
  });

  useEffect(() => {
    if (modelsQuery.data) {
      setModels(modelsQuery.data);
    }
  }, [modelsQuery.data, setModels]);

  const goLanding = () => setScreen("landing");
  const goChat = () => {
    resetInvestigation();
    setScreen("chat");
  };
  const startFlow = () => {
    if (!user) {
      setAuthOpen(true);
      return;
    }
    setScreen("chat");
  };
  const openBYOK = () => {
    if (!user) {
      setAuthOpen(true);
      return;
    }
    setByokOpen(true);
  };

  return (
    <div className="viewport">
      <TopNav
        screen={screen}
        user={user}
        investigation={investigation}
        onHome={goLanding}
        onOpenBYOK={openBYOK}
        onNewSession={goChat}
        onAuth={() => setAuthOpen(true)}
        onSignOut={() => {
          clearToken();
          setUser(null);
          setModels([]);
          resetInvestigation();
          setScreen("landing");
        }}
        theme={theme}
        onToggleTheme={() =>
          setTheme((current) => (current === "dark" ? "light" : "dark"))
        }
      />

      {screen === "landing" && (
        <LandingPage onCTA={startFlow} onOpenBYOK={openBYOK} />
      )}
      {screen === "chat" && (
        <ChatScreen
          onBack={goLanding}
          onOpenBYOK={openBYOK}
          onRequireAuth={() => setAuthOpen(true)}
        />
      )}
      {screen === "investigation" && <InvestigationPage onBack={goChat} />}

      {byokOpen && <BYOKModal onClose={() => setByokOpen(false)} />}
      {authOpen && (
        <AuthModal
          onClose={() => setAuthOpen(false)}
          onAuthenticated={() => {
            setScreen(screen === "landing" ? "chat" : screen);
          }}
        />
      )}
    </div>
  );
}

function TopNav({
  screen,
  user,
  investigation,
  onHome,
  onOpenBYOK,
  onNewSession,
  onAuth,
  onSignOut,
  theme,
  onToggleTheme,
}) {
  const crumb =
    screen === "landing"
      ? "home"
      : screen === "chat"
        ? "new investigation"
        : `session ${investigation.id?.slice(0, 4) || "live"}`;
  const ThemeIcon = theme === "dark" ? Moon : Sun;

  return (
    <header className="topnav">
      <button className="brand" onClick={onHome}>
        <div className="brand-mark">
          <Icon.Logo />
        </div>
        <span className="brand-name">
          Angetic<span className="dot">.</span>
        </span>
      </button>
      <div className="crumbs">
        <span className="sep">/</span>
        <span className="cur">{crumb}</span>
      </div>
      <div className="topnav-spacer" />
      <div className="topnav-actions">
        {screen === "investigation" && (
          <button className="btn btn-ghost" onClick={onNewSession}>
            <Icon.Plus /> New
          </button>
        )}
        {screen !== "investigation" && (
          <button className="btn btn-primary" onClick={onNewSession}>
            <Icon.Spark /> New investigation
          </button>
        )}
        <button
          className="btn btn-ghost"
          onClick={onToggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          <ThemeIcon size={16} />
        </button>
        {user ? (
          <button
            className="btn btn-ghost user-pill"
            onClick={onSignOut}
            title="Sign out"
          >
            <Icon.Shield /> {user.email.split("@")[0]}
          </button>
        ) : (
          <button className="btn btn-ghost" onClick={onAuth}>
            Sign in
          </button>
        )}
      </div>
    </header>
  );
}
