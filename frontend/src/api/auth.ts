import { apiFetch, setToken } from "./client";
import { DEMO, demoUser } from "../demo";

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

const demoToken: Token = { access_token: "demo", token_type: "bearer" };

export async function register(input: {
  email: string;
  name: string;
  username: string;
  password: string;
}): Promise<Token> {
  if (DEMO) {
    setToken(demoToken.access_token);
    return demoToken;
  }
  const token = await apiFetch<Token>("/auth/register", {
    method: "POST",
    json: input,
    auth: false,
  });
  setToken(token.access_token);
  return token;
}

export async function login(email: string, password: string): Promise<Token> {
  if (DEMO) {
    setToken(demoToken.access_token);
    return demoToken;
  }
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
  if (DEMO) return Promise.resolve(demoUser);
  return apiFetch<User>("/auth/me");
}
