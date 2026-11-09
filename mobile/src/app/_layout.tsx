import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { useTranslation } from "react-i18next";
import { AppState } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";

import "@/i18n";

const queryClient = new QueryClient();

// React Query only knows browser focus; refetch stale data when the app returns to the foreground.
focusManager.setEventListener((setFocused) => {
  const subscription = AppState.addEventListener("change", (state) => setFocused(state === "active"));
  return () => subscription.remove();
});

export default function RootLayout() {
  const { t } = useTranslation();
  return (
    // Charts need it for press-and-hold.
    <GestureHandlerRootView style={{ flex: 1 }}>
      <QueryClientProvider client={queryClient}>
        <Stack screenOptions={{ title: t("app.title") }} />
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}
