import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsButton } from "./Settings";

describe("settings modal", () => {
  let host: HTMLDivElement;
  let root: Root;
  let showModal: ReturnType<typeof vi.fn>;
  let showModalDescriptor: PropertyDescriptor | undefined;
  let closeDescriptor: PropertyDescriptor | undefined;

  beforeEach(() => {
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
    showModalDescriptor = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
    closeDescriptor = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
    showModal = vi.fn(function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    });
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: showModal });
    Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: vi.fn(function (this: HTMLDialogElement) {
      this.removeAttribute("open");
      this.dispatchEvent(new Event("close"));
    }) });
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
    vi.restoreAllMocks();
    if (showModalDescriptor) Object.defineProperty(HTMLDialogElement.prototype, "showModal", showModalDescriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
    if (closeDescriptor) Object.defineProperty(HTMLDialogElement.prototype, "close", closeDescriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  });

  it("opens, closes with Escape, and returns focus to the gear", async () => {
    await act(async () => root.render(createElement(SettingsButton)));
    const gear = host.querySelector<HTMLButtonElement>("[data-testid='settings-button']")!;
    await act(async () => gear.click());
    const dialog = host.querySelector("dialog")!;
    expect(showModal).toHaveBeenCalledOnce();
    expect(dialog.open).toBe(true);

    await act(async () => dialog.dispatchEvent(new Event("cancel", { bubbles: false, cancelable: true })));
    expect(dialog.open).toBe(false);
    expect(document.activeElement).toBe(gear);
  });
});
