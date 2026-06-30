import { apiFetch, setToken } from "./client";
import { displayName, type UserBrief } from "./users";

export interface User extends UserBrief {
  // Derived display fields the UI renders. `name` is built from first/last name;
  // `username` falls back to the email local-part until the backend adds one.
  name: string;
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

export async function me(): Promise<User> {
  const u = await apiFetch<UserBrief>("/auth/me");
  return { ...u, name: displayName(u), username: u.email.split("@")[0] };
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
