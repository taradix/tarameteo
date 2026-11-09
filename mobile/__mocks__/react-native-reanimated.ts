// Reanimated's own mock still boots the native module and throws under jest-expo; stub what we use.
import { useEffect } from "react";

export function useAnimatedReaction<T>(prepare: () => T, react: (value: T) => void) {
  useEffect(() => react(prepare()));
}
