import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SensorPicker } from "./SensorPicker";
import { queryWrapper, stubFetch } from "../test/utils";

describe("SensorPicker", () => {
  it("adds the suggestion picked with the arrow keys", async () => {
    stubFetch({
      "/api/sensors": {
        sensors: [
          { name: "jdd-carre", kind: "timeseries" },
          { name: "jdd-gazebo", kind: "timeseries" },
        ],
      },
    });
    const onChange = vi.fn();
    render(<SensorPicker selected={[]} hidden={[]} onChange={onChange} onHiddenChange={vi.fn()} />, {
      wrapper: queryWrapper(),
    });

    await userEvent.type(screen.getByRole("combobox"), "jdd");
    await screen.findByRole("option", { name: "jdd-gazebo" });
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowUp}{Enter}");
    // Down stops at the last suggestion, so Up lands on the first.
    expect(onChange).toHaveBeenCalledExactlyOnceWith(["jdd-carre"]);
  });
});
