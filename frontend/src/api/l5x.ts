// Raw sections of a parsed L5X file at a ref — the data behind the organizer's
// detail tables (UDT members, AOI parameters/routines, the controller-tag grid,
// the I/O module table). Mirrors GET /projects/{id}/l5x (backend/README.md,
// "L5XSection"); hand-written TS is the convention here. Field names match the
// parser models' JSON exactly. List sections arrive without the heavy per-entity
// blobs (tags: values/comments/message_config; modules: config/connections) —
// the backend excludes them by contract.
import { apiFetch } from "./client";

export interface UDTMember {
  name: string;
  data_type: string;
  dimension: number;
  radix: string | null;
  hidden: boolean;
  external_access: string | null;
  description: string | null;
}

export interface L5XDataType {
  name: string;
  family: string | null; // "StringFamily" marks string types
  udt_class: string | null;
  description: string | null;
  members: UDTMember[];
}

export interface L5XTag {
  name: string;
  scope: string;
  tag_type: string | null; // Base, Alias, Produced, Consumed
  alias_for: string | null;
  data_type: string;
  dimensions: number[] | null;
  radix: string | null;
  constant: boolean;
  external_access: string | null;
  description: string | null;
  value: string | null; // scalar value only; structured values are excluded
  motion_config: Record<string, string>; // Axis / MotionGroup parameter block
  tag_class: string | null; // "Safety" for safety tags
}

export interface L5XModulePort {
  id: number;
  type: string | null; // ICP, Ethernet, PointIO, …
  address: string | null; // IP address or slot number
  upstream: boolean;
}

export interface L5XModule {
  name: string;
  description: string | null;
  catalog_number: string | null;
  major: number | null;
  minor: number | null;
  parent_module: string | null;
  inhibited: boolean;
  major_fault: boolean;
  ekey_state: string | null; // Disabled, CompatibleModule, ExactMatch
  ports: L5XModulePort[];
}

export interface AOIParameter {
  name: string;
  data_type: string;
  dimensions: number[] | null;
  usage: string | null; // Input, Output, InOut
  radix: string | null;
  required: boolean;
  visible: boolean;
  external_access: string | null;
  description: string | null;
  default_value: string | null;
}

export interface AOILocalTag {
  name: string;
  data_type: string;
  dimensions: number[] | null;
  radix: string | null;
  description: string | null;
  default_value: string | null;
}

export interface L5XRung {
  number: number;
  type: string | null; // N=Normal, C=Comment
  comment: string | null;
  text: string | null; // raw rung text, e.g. "XIC(Tag1)OTE(Tag2);"
}

export interface L5XSTLine {
  number: number;
  level: number; // indentation level
  text: string;
}

export interface L5XAoiRoutine {
  name: string;
  type: string; // RLL, ST, FBD, SFC
  description: string | null;
  content: { rungs: L5XRung[] | null; lines: L5XSTLine[] | null };
}

export interface L5XAoi {
  name: string;
  revision: string | null;
  vendor: string | null;
  description: string | null;
  edited_by: string | null;
  edited_date: string | null;
  parameters: AOIParameter[];
  local_tags: AOILocalTag[];
  routines: L5XAoiRoutine[];
}

interface L5XSectionEnvelope<T> {
  schema_version: number;
  section: string;
  data: T;
}

// `path` is an l5x/<name> manifest path (the same value the tree endpoints
// take); `ref` is any Git ref, including a short commit sha.
async function getSection<T>(
  projectId: number,
  ref: string,
  path: string,
  section: string,
  name?: string,
): Promise<T> {
  let q =
    `?ref=${encodeURIComponent(ref)}&path=${encodeURIComponent(path)}` +
    `&section=${section}`;
  if (name) q += `&name=${encodeURIComponent(name)}`;
  const env = await apiFetch<L5XSectionEnvelope<T>>(`/projects/${projectId}/l5x${q}`);
  return env.data;
}

export function getL5xDataTypes(
  projectId: number,
  ref: string,
  path: string,
): Promise<L5XDataType[]> {
  return getSection(projectId, ref, path, "datatypes");
}

export function getL5xTags(
  projectId: number,
  ref: string,
  path: string,
): Promise<L5XTag[]> {
  return getSection(projectId, ref, path, "tags");
}

export function getL5xModules(
  projectId: number,
  ref: string,
  path: string,
): Promise<L5XModule[]> {
  return getSection(projectId, ref, path, "modules");
}

// One full AOI (parameters, local tags, routine content). The whole-AOI list is
// deliberately not offered by the backend — fetch per AOI on click (~13 KB).
export function getL5xAoi(
  projectId: number,
  ref: string,
  path: string,
  name: string,
): Promise<L5XAoi> {
  return getSection(projectId, ref, path, "aoi", name);
}
