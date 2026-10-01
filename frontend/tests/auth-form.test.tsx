import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { AuthForm } from "@/features/auth/auth-form";

const { request, push, refresh } = vi.hoisted(() => ({ request: vi.fn(), push: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/api/auth", () => ({ authRequest: request }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));
beforeEach(() => vi.clearAllMocks());

test("서버의 필드 오류를 표시하고 비밀번호를 화면에 출력하지 않는다", async () => {
  request.mockResolvedValue({ ok: false, json: async () => ({ error: { details: { email: ["이미 사용 중인 이메일입니다."] } } }) });
  render(<AuthForm register />);
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "a@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "private-password" } });
  fireEvent.submit(screen.getByRole("button", { name: "가입하기" }).closest("form")!);
  expect(await screen.findByRole("alert")).toHaveTextContent("이미 사용 중인 이메일입니다.");
  expect(screen.queryByText("private-password")).not.toBeInTheDocument();
  expect(push).not.toHaveBeenCalled();
});

test("로그인 성공 뒤 서버 계정 화면을 갱신한다", async () => {
  request.mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  render(<AuthForm />);
  fireEvent.submit(screen.getByRole("button", { name: "로그인" }).closest("form")!);
  await waitFor(() => expect(push).toHaveBeenCalledWith("/account"));
  expect(refresh).toHaveBeenCalled();
});
