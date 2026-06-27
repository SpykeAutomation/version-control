import { apiFetch, setToken } from "./client";

export interface User {
  id: number;
  email: string;
  name: string;
  // Optional until the backend adds a real username column; the UI falls back
  // to a value derived from the email when this is absent.
  username?: string;
}

interface Token {
  access_token: string;
  token_type: string;
}

export async function register(input: {
  email: string;
  name: string;
  username: string;
  password: string;
}): Promise<Token> {
  const token = await apiFetch<Token>("/auth/register", {
    method: "POST",
    json: input,
    auth: false,
  });
  setToken(token.access_token);
  return token;
}

export async function login(email: string, password: string): Promise<Token> {
  // /auth/login is form-encoded with username=email.
  const form = new URLSearchParams({ username: email, password });
  const token = await apiFetch<Token>("/auth/login", {
    method: "POST",
    form,
    auth: false,
  });
  setToken(token.access_token);
  return token;
}

export function me(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

// Approve a CLI device sign-in. The CLI prints a short user code and polls the
// backend for a token; a 200 here releases that token. Throws ApiError on 400
// (invalid/expired code) or 409 (already approved).
export function approveDevice(userCode: string): Promise<void> {
  return apiFetch<void>("/auth/device/approve", {
    method: "POST",
    json: { user_code: userCode },
  });
}
