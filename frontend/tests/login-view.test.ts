import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginView from "@/views/LoginView.vue";

const { statusMock } = vi.hoisted(() => ({ statusMock: vi.fn() }));

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
}));

vi.mock("@/api/auth", () => ({
  authApi: {
    status: statusMock,
    setup: vi.fn(),
    register: vi.fn(),
    login: vi.fn(),
  },
}));

describe("LoginView", () => {
  beforeEach(() => {
    statusMock.mockReset();
  });

  it("does not prefill the administrator in normal login mode", async () => {
    statusMock.mockResolvedValue({
      authenticated: false,
      needsSetup: false,
      defaultUserId: "default",
      user: null,
    });

    const wrapper = mount(LoginView);
    await flushPromises();

    expect(wrapper.get(".login-brand img").attributes("src")).toContain("smartcore-mark-blue.png");
    expect((wrapper.get("input[autocomplete='username']").element as HTMLInputElement).value).toBe("");
  });

  it("still shows the fixed administrator ID during initial setup", async () => {
    statusMock.mockResolvedValue({
      authenticated: false,
      needsSetup: true,
      defaultUserId: "default",
      user: null,
    });

    const wrapper = mount(LoginView);
    await flushPromises();
    const input = wrapper.get("input[autocomplete='username']").element as HTMLInputElement;

    expect(input.value).toBe("default");
    expect(input.readOnly).toBe(true);
  });
});
