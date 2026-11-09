import { focusManager } from "@tanstack/react-query";
import { AppState } from "react-native";

import "./app/_layout";

test("React Query focus follows the app foreground state", () => {
  // react-native's jest setup mocks AppState.addEventListener.
  const [[, listener]] = jest.mocked(AppState.addEventListener).mock.calls;

  listener("background");
  expect(focusManager.isFocused()).toBe(false);
  listener("active");
  expect(focusManager.isFocused()).toBe(true);
});
