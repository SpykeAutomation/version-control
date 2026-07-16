// Per-user "don't show this again" flags for onboarding hints, kept in
// localStorage. Keyed by user id so two accounts sharing a browser don't
// inherit each other's dismissals. Deliberately NOT backend state: a
// dismissed hint reappearing once on a new device is acceptable, and the
// same ids can migrate into backend user prefs later without UX change.
import { useCallback, useState } from "react";
import { useAuth } from "../auth/AuthContext";

function storageKey(userId: number | undefined): string {
  return `spyke_ui_${userId ?? "anon"}`;
}

function readDismissed(key: string): Record<string, true> {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed?.dismissed ?? {};
  } catch {
    return {};
  }
}

export function useDismissal(id: string): {
  dismissed: boolean;
  dismiss: () => void;
} {
  const { user } = useAuth();
  const key = storageKey(user?.id);
  const [dismissed, setDismissed] = useState(() =>
    Boolean(readDismissed(key)[id]),
  );
  const dismiss = useCallback(() => {
    const cur = readDismissed(key);
    cur[id] = true;
    try {
      localStorage.setItem(key, JSON.stringify({ dismissed: cur }));
    } catch {
      // Storage blocked/full: still hide it for this session.
    }
    setDismissed(true);
  }, [key, id]);
  return { dismissed, dismiss };
}
