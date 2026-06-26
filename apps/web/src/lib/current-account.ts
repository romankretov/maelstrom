import { useEffect, useState } from "react";

const STORAGE_KEY = "maelstrom:current-account";

function read(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Tracks the user's preferred trading account across pages. Pages that
 * default to "an account" (portfolio, run-live form) read this so the
 * switcher in the sidebar stays in sync.
 *
 * Persisted to localStorage so a reload doesn't lose the selection.
 */
export function useCurrentAccount(): {
  accountId: string | null;
  setAccountId: (id: string | null) => void;
} {
  const [accountId, setIdLocal] = useState<string | null>(read);
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === STORAGE_KEY) setIdLocal(e.newValue);
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  return {
    accountId,
    setAccountId: (id) => {
      setIdLocal(id);
      try {
        if (id === null) localStorage.removeItem(STORAGE_KEY);
        else localStorage.setItem(STORAGE_KEY, id);
        // Manually fire so same-tab listeners update too.
        window.dispatchEvent(
          new StorageEvent("storage", { key: STORAGE_KEY, newValue: id ?? null }),
        );
      } catch {
        /* localStorage blocked */
      }
    },
  };
}
