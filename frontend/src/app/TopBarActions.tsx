import { createContext, useContext, useEffect, type ReactNode } from "react";

// Lets a page put buttons in the shared top bar without rendering its own
// TopBar. AppLayout owns the actions and exposes this setter; a page registers
// its buttons while it is mounted and clears them when it leaves.
const SetTopBarActions = createContext<(node: ReactNode) => void>(() => {});

export const TopBarActionsProvider = SetTopBarActions.Provider;

// Show the given buttons in the top bar for as long as the page is mounted.
// Page actions are static, so this registers once on mount and clears on
// unmount.
export function useTopBarActions(node: ReactNode) {
  const setActions = useContext(SetTopBarActions);
  useEffect(() => {
    setActions(node);
    return () => setActions(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
