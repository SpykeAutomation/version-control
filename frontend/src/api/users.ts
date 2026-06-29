// The backend identifies people by first/last name (there is no single `name`
// column) and embeds them as nested user objects on projects, pull requests,
// reviews and comments. The UI wants a single display string, so every place
// that receives one of these objects runs it through displayName().

export interface UserBrief {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
  avatar?: string;
  organization?: string | null;
}

// "First Last", falling back to the email when a name isn't set.
export function displayName(u: UserBrief): string {
  const name = [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
  return name || u.email;
}
