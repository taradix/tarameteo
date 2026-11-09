import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { useTranslation } from "react-i18next";

import "@/i18n";

const queryClient = new QueryClient();

export default function RootLayout() {
  const { t } = useTranslation();
  return (
    <QueryClientProvider client={queryClient}>
      <Stack screenOptions={{ title: t("app.title") }} />
    </QueryClientProvider>
  );
}
